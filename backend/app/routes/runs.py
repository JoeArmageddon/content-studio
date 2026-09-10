from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Channel, Run
from app.graph.channel_pipeline import pipeline
from app.services.run_persistence import channel_to_dict, finalize_run

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def list_runs(channel_key: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Run)
    if channel_key:
        channel = db.query(Channel).filter(Channel.key == channel_key).first()
        query = query.filter(Run.channel_id == channel.id if channel else -1)
    runs = query.order_by(Run.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "channel_id": r.channel_id,
            "status": r.status,
            "stage_log": r.stage_log,
            "error": r.error,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
        }
        for r in runs
    ]


@router.post("/trigger/{channel_key}")
def trigger_run(channel_key: str, db: Session = Depends(get_db)):
    """
    Synchronously runs the full per-video LangGraph pipeline for one channel
    and persists Run/Story/Video rows. Useful as a manual "run one now"
    dashboard action once real agents land; the scheduler drives the normal
    daily cadence.
    """
    channel = db.query(Channel).filter(Channel.key == channel_key).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_key}' not found")

    run = Run(channel_id=channel.id, status="running", stage_log=[])
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        final_state = pipeline.invoke(
            {"run_id": run.id, "channel": channel_to_dict(channel), "stage_log": []}
        )
        finalize_run(db, run, channel, final_state)

        return {
            "run_id": run.id,
            "status": run.status,
            "stage_log": run.stage_log,
            "story_title": (final_state.get("story") or {}).get("title"),
            "video_path": final_state.get("video_path"),
        }
    except Exception as exc:  # noqa: BLE001 — surfaced to the caller for now
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Pipeline run failed: {exc}") from exc

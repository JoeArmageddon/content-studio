"""
Feedback/Performance Agent — Milestone 8.

Not part of the per-video LangGraph run — runs on a slower cadence (daily,
via the scheduler — see scheduler.py's _schedule_insights_job). Pulls
YouTube Analytics for the channel's own uploaded videos, matches the
top-viewed ones back to our own Video rows to recover their titles (the
Analytics API gives video IDs and numbers, not the title we wrote), and
writes a "what's working" summary into the shared Insight store — the
internal counterpart to the Competitor-Scan Agent, read by the same
app.services.insights module.
"""
from typing import Any

from app.core.db import SessionLocal
from app.core.models import Insight, Video
from app.services import youtube_client

_TOP_N = 5


def run(channel: dict[str, Any]) -> dict[str, Any]:
    key = channel.get("key", "unknown")
    channel_id = channel.get("id")

    try:
        analytics = youtube_client.get_channel_analytics(key)
    except Exception as exc:  # noqa: BLE001 — a failed pull shouldn't block anything downstream
        print(f"WARNING: feedback analytics failed for '{key}': {exc}")
        return {"channel_key": key, "source": "own_analytics", "findings": {}}

    videos = analytics.get("videos", [])
    top = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:_TOP_N]
    top_video_ids = [v.get("video") for v in top if v.get("video")]

    top_titles: list[str] = []
    if channel_id and top_video_ids:
        db = SessionLocal()
        try:
            rows = (
                db.query(Video)
                .filter(Video.channel_id == channel_id, Video.youtube_video_id.in_(top_video_ids))
                .all()
            )
            by_id = {r.youtube_video_id: r.title for r in rows}
            top_titles = [by_id[vid] for vid in top_video_ids if by_id.get(vid)]
        finally:
            db.close()

    findings = {
        "top_titles": top_titles,
        "top_video_ids": top_video_ids,
        "sample_size": len(videos),
    }

    if channel_id:
        db = SessionLocal()
        try:
            db.add(Insight(channel_id=channel_id, source="own_analytics", query=None, findings=findings))
            db.commit()
        finally:
            db.close()

    return {"channel_key": key, "source": "own_analytics", "findings": findings}

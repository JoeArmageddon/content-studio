"""
Shared "a pipeline run finished, write the results" logic — used by both the
manual trigger endpoint (routes/runs.py) and the scheduler (scheduler.py) so
the two don't drift out of sync.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.models import Channel, Run, Story, Video


def channel_to_dict(channel: Channel) -> dict:
    return {
        "id": channel.id,
        "key": channel.key,
        "name": channel.name,
        "niche": channel.niche,
        "subreddits": channel.subreddits,
        "voices": channel.voices,
        "background_queries": channel.background_queries,
        "persona": channel.persona,
        "daily_cap": channel.daily_cap,
    }


def finalize_run(db: Session, run: Run, channel: Channel, final_state: dict) -> None:
    run.stage_log = final_state.get("stage_log", [])
    stages = final_state.get("stage_log", [])
    if final_state.get("published"):
        run.status = "done"
    elif final_state.get("dry_run"):
        run.status = "dry_run"
    elif "publish_blocked_daily_cap" in stages:
        run.status = "skipped"  # not a failure: the channel just hit its daily cap
    else:
        run.status = "failed"
    if run.status in ("failed", "skipped") and not run.error:
        # Keep the reason (e.g. "not authorized", "YouTube upload failed: …") instead of losing it.
        notes = final_state.get("compliance_notes") or []
        run.error = final_state.get("error") or (notes[-1] if notes else None) or f"Stopped after: {stages[-1] if stages else 'start'}"
    run.finished_at = datetime.now(timezone.utc)

    story_data = final_state.get("story")
    if story_data:
        db.add(
            Story(
                channel_id=channel.id,
                source=story_data.get("source", "stub"),
                source_id=story_data.get("source_id"),
                title=story_data.get("title"),
                content=story_data.get("content"),
                score=story_data.get("score", 0),
                # Only mark it consumed if the run actually produced a published
                # video — a failed/blocked run shouldn't burn the story forever.
                used=bool(final_state.get("published")),
            )
        )

    published = bool(final_state.get("published"))
    metadata = final_state.get("metadata") or {}
    db.add(
        Video(
            run_id=run.id,
            channel_id=channel.id,
            title=metadata.get("title"),
            description=metadata.get("description"),
            tags=metadata.get("tags", []),
            voice_used=final_state.get("voice_used"),
            background_clip=final_state.get("background_clip"),
            file_path=final_state.get("video_path"),
            status="published" if published else "draft",
            youtube_video_id=final_state.get("youtube_video_id"),
            story_title=(story_data or {}).get("title"),
            story_url=(f"https://www.reddit.com/comments/{story_data['source_id']}" if (story_data or {}).get("source_id") else None),
            subreddit=(story_data or {}).get("subreddit"),
            # Needed by the Publisher Agent's daily-cap check (counts today's
            # published videos) — was missing entirely before Milestone 6,
            # which would have silently broken that check.
            published_at=datetime.now(timezone.utc) if published else None,
        )
    )
    db.commit()

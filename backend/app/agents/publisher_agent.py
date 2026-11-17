"""
Publisher Agent — Milestone 6.

Enforces the reduced daily upload cap per channel (channel.daily_cap — the
concrete shadowban fix, well below the ~7-10/day that likely triggered it
on StoriqueOS) by counting today's already-published videos before
uploading, and performs the actual YouTube upload via
app.services.youtube_client (OAuth per channel — see that module and
backend/scripts/authorize_youtube_channel.py). Degrades gracefully
(published=False, clear note) if compliance blocked it, the daily cap is
already hit, there's no video to publish, or the channel hasn't been
OAuth-authorized yet — same pattern as every other credential-gated agent.
"""
from datetime import datetime, timezone

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import Video
from app.graph.state import PipelineState
from app.services import youtube_client


def _today_published_count(db, channel_id: int) -> int:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(Video)
        .filter(
            Video.channel_id == channel_id,
            Video.status == "published",
            Video.published_at >= today_start,
        )
        .count()
    )


def run(state: PipelineState) -> PipelineState:
    if not state.get("compliance_ok"):
        state["published"] = False
        state.setdefault("stage_log", []).append("publish_blocked_compliance")
        return state

    video_path = state.get("video_path")
    if not video_path:
        state["published"] = False
        state.setdefault("stage_log", []).append("publish_skipped_no_video")
        return state

    if settings.dry_run:
        state["published"] = False
        state["dry_run"] = True
        state.setdefault("compliance_notes", []).append(f"DRY RUN: video built at {video_path}, not uploaded.")
        state.setdefault("stage_log", []).append("publish_skipped_dry_run")
        return state

    channel = state.get("channel", {})
    channel_id = channel.get("id")
    key = channel.get("key", "unknown")
    daily_cap = channel.get("daily_cap", 3)

    if channel_id:
        db = SessionLocal()
        try:
            count_today = _today_published_count(db, channel_id)
        finally:
            db.close()

        if count_today >= daily_cap:
            state["published"] = False
            state.setdefault("compliance_notes", []).append(
                f"Blocked: channel '{key}' already published {count_today}/{daily_cap} videos today."
            )
            state.setdefault("stage_log", []).append("publish_blocked_daily_cap")
            return state

    metadata = state.get("metadata") or {}
    try:
        state["youtube_video_id"] = youtube_client.upload_video(video_path, metadata, key)
        state["published"] = True
    except youtube_client.NotAuthorized as exc:
        state["published"] = False
        state["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 — publish failure shouldn't crash the run
        state["published"] = False
        state["error"] = f"YouTube upload failed: {exc}"

    state.setdefault("stage_log", []).append("publish")
    return state

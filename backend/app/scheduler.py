"""
APScheduler wiring — owns the calendar (when a channel's pipeline runs),
while LangGraph (app.graph.channel_pipeline) owns what happens inside one
run. Disabled by default (SCHEDULER_ENABLED=false) so local dev/testing
never fires real runs by accident.

Each active channel gets `daily_cap` runs per day, spaced evenly starting at
settings.scheduler_start_hour — the daily_cap value itself is the shadowban
fix (kept low; see channels.yaml), spacing is a secondary safeguard on top.

Per-channel offset — caught during Milestone 7 (rolling out all 10
channels): every channel currently shares the same daily_cap and start
hour, so without an offset their computed job times would be IDENTICAL
across channels — all 10 channels' pipelines firing at the exact same
moment, several times a day. That would mean 10 simultaneous Reddit RSS
requests (worse than the rate-limit pressure already documented in
reddit_client.py), 10 concurrent SQLite writers, and 10 concurrent Kokoro
loads. A deterministic per-channel offset (hashed from the channel key)
spreads them out instead.
"""
import hashlib
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.agents import competitor_scan_agent, feedback_agent
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import Channel, Run
from app.graph.channel_pipeline import pipeline
from app.services.run_persistence import channel_to_dict, finalize_run

_scheduler: Optional[BackgroundScheduler] = None
_INSIGHTS_JOB_HOUR = 3  # UTC — well before scheduler_start_hour's content runs


def _run_channel_job(channel_key: str) -> None:
    db = SessionLocal()
    try:
        channel = db.query(Channel).filter(Channel.key == channel_key).first()
        if not channel or not channel.active:
            return

        run = Run(channel_id=channel.id, status="running", stage_log=[])
        db.add(run)
        db.commit()
        db.refresh(run)

        final_state = pipeline.invoke(
            {"run_id": run.id, "channel": channel_to_dict(channel), "stage_log": []}
        )
        finalize_run(db, run, channel, final_state)
    except Exception as exc:  # noqa: BLE001 — scheduler jobs must not crash the process
        print(f"WARNING: scheduled run failed for channel '{channel_key}': {exc}")
    finally:
        db.close()


def _run_insights_job(channel_key: str) -> None:
    """Daily Feedback + Competitor-Scan for one channel — not part of the
    per-video pipeline (see feedback_agent.py / competitor_scan_agent.py
    docstrings). Both write into the shared Insight store that
    Curation/Hook/Scriptwriter/Metadata read from on their next run."""
    db = SessionLocal()
    try:
        channel = db.query(Channel).filter(Channel.key == channel_key).first()
        if not channel or not channel.active:
            return
        channel_dict = channel_to_dict(channel)
    finally:
        db.close()

    try:
        feedback_agent.run(channel_dict)
    except Exception as exc:  # noqa: BLE001 — one agent failing shouldn't skip the other
        print(f"WARNING: feedback job failed for channel '{channel_key}': {exc}")

    try:
        competitor_scan_agent.run(channel_dict)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: competitor-scan job failed for channel '{channel_key}': {exc}")


def _channel_offset_minutes(channel_key: str, spread_minutes: int = 50) -> int:
    """Deterministic 0..spread_minutes offset per channel, so channels that
    share the same daily_cap/start_hour don't all fire at once."""
    digest = int(hashlib.md5(channel_key.encode()).hexdigest(), 16)
    return digest % spread_minutes


def _schedule_channel(scheduler: BackgroundScheduler, channel: Channel) -> None:
    cap = max(channel.daily_cap, 1)
    window_hours = 16  # spread runs across a ~16h waking-audience window
    step = window_hours / cap
    offset_minutes = _channel_offset_minutes(channel.key)

    for i in range(cap):
        slot_hours = settings.scheduler_start_hour + i * step
        total_minutes = int(slot_hours * 60) + offset_minutes
        hour = (total_minutes // 60) % 24
        minute = total_minutes % 60
        scheduler.add_job(
            _run_channel_job,
            trigger=CronTrigger(hour=hour, minute=minute),
            args=[channel.key],
            id=f"channel_{channel.key}_{i}",
            replace_existing=True,
        )


def _schedule_insights_job(scheduler: BackgroundScheduler, channel: Channel) -> None:
    offset_minutes = _channel_offset_minutes(channel.key)
    total_minutes = _INSIGHTS_JOB_HOUR * 60 + offset_minutes
    scheduler.add_job(
        _run_insights_job,
        trigger=CronTrigger(hour=(total_minutes // 60) % 24, minute=total_minutes % 60),
        args=[channel.key],
        id=f"insights_{channel.key}",
        replace_existing=True,
    )


def start_scheduler() -> None:
    global _scheduler
    if not settings.scheduler_enabled or _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    db = SessionLocal()
    try:
        for channel in db.query(Channel).filter(Channel.active.is_(True)).all():
            _schedule_channel(_scheduler, channel)
            _schedule_insights_job(_scheduler, channel)
    finally:
        db.close()
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None

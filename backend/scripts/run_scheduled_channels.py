"""
Entrypoint for the GitHub Actions pipeline runner — replaces the in-process
APScheduler (app/scheduler.py) that a locally-run always-on server would
use. GitHub Actions' own cron trigger decides *when* this runs; this script
decides *which* channels actually get a run this time, then directly
reuses app.scheduler.run_channel_job() (no logic duplicated).

Usage:
    python scripts/run_scheduled_channels.py                 # all active channels not yet at today's daily_cap
    python scripts/run_scheduled_channels.py --channel aita  # just one — used for workflow_dispatch (manual /
                                                               # dashboard "trigger run now"), does NOT pre-filter
                                                               # by daily_cap (the real safety net is inside
                                                               # publisher_agent, which still applies either way —
                                                               # see its _today_published_count check)
    python scripts/run_scheduled_channels.py --insights       # daily Feedback + Competitor-Scan for all active channels
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import app.*` works

from app.agents.publisher_agent import _today_published_count  # noqa: E402
from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.models import Channel  # noqa: E402
from app.scheduler import run_channel_job, run_insights_job  # noqa: E402
from app.services.channel_seed import seed_channels  # noqa: E402


def _due_channel_keys() -> list[str]:
    db = SessionLocal()
    try:
        channels = db.query(Channel).filter(Channel.active.is_(True)).all()
        return [c.key for c in channels if _today_published_count(db, c.id) < c.daily_cap]
    finally:
        db.close()


def _active_channel_keys() -> list[str]:
    db = SessionLocal()
    try:
        return [c.key for c in db.query(Channel).filter(Channel.active.is_(True)).all()]
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default=None, help="Run just this one channel's content pipeline")
    parser.add_argument(
        "--insights", action="store_true", help="Run Feedback + Competitor-Scan for all active channels instead"
    )
    args = parser.parse_args()

    init_db()
    seed_channels()  # apply channels.yaml (voices etc.) — the DB keeps active/daily_cap

    if args.insights:
        for key in _active_channel_keys():
            print(f"=== Insights: '{key}' ===")
            run_insights_job(key)
        return

    keys = [args.channel] if args.channel else _due_channel_keys()
    if not keys:
        print("No channels due for a run right now.")
        return

    for key in keys:
        print(f"=== Running channel '{key}' ===")
        run_channel_job(key, force=bool(args.channel))  # an explicit --channel is a manual run: ignore the pause


if __name__ == "__main__":
    main()

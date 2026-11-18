"""
Syncs channels.yaml into the DB. Shared by the FastAPI app's startup and the
GitHub Actions runner (scripts/run_scheduled_channels.py) — the runner used to
skip this, so config changes (e.g. the voice) never reached scheduled runs.

Split of ownership:
  - channels.yaml owns CONTENT config: name, niche, subreddits, voices,
    background_queries, persona. Always re-applied.
  - The DB owns OPERATIONAL state: `active` and `daily_cap`, which the
    dashboard edits. They're only taken from the yaml when a channel is first
    created, so pausing a channel in the dashboard sticks.
"""
from pathlib import Path

import yaml

from app.core.db import SessionLocal
from app.core.models import Channel

CHANNELS_YAML = Path(__file__).resolve().parents[1] / "config" / "channels.yaml"


def seed_channels() -> None:
    with open(CHANNELS_YAML) as f:
        defs = yaml.safe_load(f)["channels"]

    db = SessionLocal()
    try:
        for d in defs:
            channel = db.query(Channel).filter(Channel.key == d["key"]).first()
            if channel is None:
                channel = Channel(key=d["key"], daily_cap=d.get("daily_cap", 3), active=d.get("active", True))
                db.add(channel)
            channel.name = d["name"]
            channel.niche = d["niche"]
            channel.subreddits = d.get("subreddits", [])
            channel.voices = d.get("voices", [])
            channel.background_queries = d.get("background_queries", [])
            channel.persona = d.get("persona", {})
        db.commit()
    finally:
        db.close()

"""
Competitor/Trend Scanning Agent — Milestone 6 (brought forward from 8, since
Metadata now depends on it).

Searches YouTube (Data API, free, public-data only — no auth needed) for
other creators' videos in the channel's niche, and writes what's currently
working market-wide into the shared Insight store (app.core.models.Insight)
that Metadata reads from. Not part of the per-video LangGraph run — the
architecture doc scopes this to a slower cadence (e.g. daily via the
scheduler); for now it's invoked lazily by the Metadata Agent when no
recent scan exists for a channel (see metadata_agent.py) rather than on its
own schedule — proper periodic scheduling is still Milestone 8's job
alongside the dashboard.
"""
import re
from collections import Counter
from typing import Any

from app.core.db import SessionLocal
from app.core.models import Insight
from app.services import youtube_client

_TOP_N_TITLES = 5
_TOP_N_HASHTAGS = 10


def run(channel: dict[str, Any]) -> dict[str, Any]:
    key = channel.get("key", "unknown")
    query = channel.get("niche") or key

    try:
        videos = youtube_client.search_competitor_videos(query)
    except Exception as exc:  # noqa: BLE001 — a failed scan shouldn't block Metadata
        print(f"WARNING: competitor scan failed for '{key}': {exc}")
        return {"channel_key": key, "source": "competitor_scan", "findings": {}}

    top_by_views = sorted(videos, key=lambda v: v["view_count"], reverse=True)[:_TOP_N_TITLES]
    hashtags: list[str] = []
    for v in videos:
        hashtags.extend(re.findall(r"#\w+", v.get("description", "")))
    top_hashtags = [tag for tag, _ in Counter(hashtags).most_common(_TOP_N_HASHTAGS)]

    findings = {
        "top_titles": [v["title"] for v in top_by_views],
        "top_hashtags": top_hashtags,
        "sample_size": len(videos),
    }

    channel_id = channel.get("id")
    if channel_id:
        db = SessionLocal()
        try:
            db.add(Insight(channel_id=channel_id, source="competitor_scan", query=query, findings=findings))
            db.commit()
        finally:
            db.close()

    return {"channel_key": key, "source": "competitor_scan", "findings": findings}

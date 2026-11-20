"""
Shared read access to the Insight store — Milestone 8.

Both Competitor-Scan (source="competitor_scan", since Milestone 6) and
Feedback (source="own_analytics", this milestone) write to the same table;
this module is the one place Curation/Hook/Scriptwriter/Metadata read from,
so all four agents see a consistent "what's working" picture instead of
each reimplementing the query.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.db import SessionLocal
from app.core.models import Insight
from app.services import lang_filter

_DEFAULT_MAX_AGE_DAYS = 7
_DEFAULT_LIMIT = 5


def get_recent(
    channel_id: Optional[int],
    source: Optional[str] = None,
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    limit: int = _DEFAULT_LIMIT,
) -> list[Insight]:
    if not channel_id:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    db = SessionLocal()
    try:
        query = db.query(Insight).filter(Insight.channel_id == channel_id, Insight.created_at >= cutoff)
        if source:
            query = query.filter(Insight.source == source)
        return query.order_by(Insight.created_at.desc()).limit(limit).all()
    finally:
        db.close()


def top_titles(channel_id: Optional[int], max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> list[str]:
    """Pooled top_titles from every recent insight (both sources) — used by
    Curation's keyword-overlap boost."""
    titles: list[str] = []
    for insight in get_recent(channel_id, max_age_days=max_age_days):
        titles.extend((insight.findings or {}).get("top_titles", []))
    # English-only, also for rows stored before the scan was made English-only.
    return [t for t in titles if t and lang_filter.looks_english(t)]


def summarize_for_prompt(channel_id: Optional[int], max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> str:
    """A short text block for LLM prompts (Hook/Scriptwriter/Metadata) —
    empty string if there's nothing recent, so callers can just concatenate
    it into a prompt unconditionally."""
    lines = []
    for insight in get_recent(channel_id, max_age_days=max_age_days):
        findings = insight.findings or {}
        if insight.source == "competitor_scan":
            titles = [t for t in findings.get("top_titles", []) if lang_filter.looks_english(t)]
            tags = [h for h in findings.get("top_hashtags", []) if lang_filter.hashtag_ok(h)]
            if titles:
                lines.append(f"Titles doing well for other creators in this niche right now: {titles}")
            if tags:
                lines.append(f"Hashtags commonly used in this niche right now: {tags}")
        elif insight.source == "own_analytics":
            if findings.get("top_titles"):
                lines.append(f"Your own best-performing recent videos on this channel: {findings['top_titles']}")
    return "\n".join(lines)

"""
Pulls live YouTube numbers into the DB so the dashboard (which only reads the
DB) can show them: per-channel subscribers / total views, and per-video
views / likes / comments for every video we've published.

Uses each channel's own OAuth token (youtube_tokens table) — read-only calls
(channels.list, videos.list), ~3 quota units per channel per run.

Usage (from backend/):
    python scripts/sync_youtube_stats.py
    python scripts/sync_youtube_stats.py --channel aita
Run on a schedule by .github/workflows/stats.yml.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import app.*` works

from googleapiclient.discovery import build  # noqa: E402

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.models import Channel, Video  # noqa: E402
from app.services.youtube_client import NotAuthorized, get_credentials  # noqa: E402


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def sync_channel(db, channel: Channel) -> str:
    try:
        creds = get_credentials(channel.key)
    except NotAuthorized:
        return "not authorized"
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    now = datetime.now(timezone.utc)

    items = yt.channels().list(part="snippet,statistics", mine=True).execute().get("items", [])
    if not items:
        return "no channel returned"
    ch = items[0]
    stats = ch.get("statistics", {})
    channel.yt_channel_id = ch["id"]
    channel.yt_title = ch.get("snippet", {}).get("title")
    channel.subscribers = None if stats.get("hiddenSubscriberCount") else _int(stats.get("subscriberCount"))
    channel.total_views = _int(stats.get("viewCount"))
    channel.yt_video_count = _int(stats.get("videoCount"))
    channel.stats_updated_at = now

    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel.id, Video.youtube_video_id.isnot(None))
        .all()
    )
    by_id = {v.youtube_video_id: v for v in videos}
    ids = list(by_id)
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="statistics", id=",".join(ids[i : i + 50])).execute()
        for item in resp.get("items", []):
            v, st = by_id[item["id"]], item.get("statistics", {})
            v.views, v.likes, v.comments = _int(st.get("viewCount")), _int(st.get("likeCount")), _int(st.get("commentCount"))
            v.stats_updated_at = now
    db.commit()
    return f"{channel.subscribers} subs, {channel.total_views} views, {len(ids)} videos"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default=None)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        q = db.query(Channel)
        if args.channel:
            q = q.filter(Channel.key == args.channel)
        for channel in q.order_by(Channel.id).all():
            try:
                print(f"{channel.key}: {sync_channel(db, channel)}")
            except Exception as exc:  # noqa: BLE001 — one channel failing shouldn't stop the rest
                db.rollback()
                print(f"{channel.key}: FAILED {str(exc)[:200]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

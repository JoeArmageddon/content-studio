"""
YouTube client — Milestones 6 & 8.

  - search_competitor_videos(): public search (Data API key only, no OAuth)
    for the Competitor-Scan Agent — other creators' videos in a niche,
    their view/like/comment counts and titles/hashtags. NOT verified live —
    no YouTube Data API key was available while building this.
  - upload_video(): OAuth-per-channel upload. Needs a token already created
    by scripts/authorize_youtube_channel.py — that script opens a browser
    for interactive consent and is meant to be run by the user directly,
    not automated (see the app's own rules on OAuth consent). NOT verified
    live — no OAuth client/channel has been authorized yet.
  - get_channel_analytics(): own-channel stats (views per recent video) for
    the Feedback Agent — uses the YouTube Analytics API v2, which needs the
    yt-analytics.readonly OAuth scope (added to
    scripts/authorize_youtube_channel.py's SCOPES this milestone — a
    channel authorized before this change needs re-authorizing to pick up
    the new scope). NOT verified live — no OAuth-authorized channel with
    analytics history was available while building this.

Token storage: the `youtube_tokens` DB table (app.core.models.YouTubeToken),
not a local file — added when going live on GitHub Actions, since those runs
are ephemeral with no persistent disk between runs. This also just works
for local dev against the default local SQLite DB, so there's one storage
path, not two.
"""
import json
from typing import Any

import requests

from app.core.db import SessionLocal
from app.core.models import YouTubeToken
from app.core.config import settings

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class NotAuthorized(RuntimeError):
    """No OAuth token exists yet for this channel."""


def save_credentials(channel_key: str, creds) -> None:
    db = SessionLocal()
    try:
        row = db.query(YouTubeToken).filter(YouTubeToken.channel_key == channel_key).first()
        if row is None:
            row = YouTubeToken(channel_key=channel_key)
            db.add(row)
        row.token_json = creds.to_json()
        db.commit()
    finally:
        db.close()


def get_credentials(channel_key: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    db = SessionLocal()
    try:
        row = db.query(YouTubeToken).filter(YouTubeToken.channel_key == channel_key).first()
    finally:
        db.close()

    if row is None:
        raise NotAuthorized(
            f"No YouTube authorization for channel '{channel_key}'. Run: "
            f"python scripts/authorize_youtube_channel.py {channel_key}"
        )

    creds = Credentials.from_authorized_user_info(json.loads(row.token_json))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(channel_key, creds)
    return creds


def upload_video(video_path: str, metadata: dict[str, Any], channel_key: str) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_credentials(channel_key)  # raises NotAuthorized if missing
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": (metadata.get("title") or "Untitled")[:100],
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
            "categoryId": "24",  # Entertainment
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return response["id"]


def get_channel_analytics(channel_key: str, days: int = 30) -> dict[str, Any]:
    from datetime import date, timedelta

    from googleapiclient.discovery import build

    creds = get_credentials(channel_key)  # raises NotAuthorized if missing
    youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    response = (
        youtube_analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,likes,comments,averageViewDuration,estimatedMinutesWatched",
            dimensions="video",
            sort="-views",
            maxResults=25,
        )
        .execute()
    )

    columns = [c["name"] for c in response.get("columnHeaders", [])]
    videos = [dict(zip(columns, row)) for row in response.get("rows", [])]
    return {"videos": videos, "period_days": days}


def search_competitor_videos(niche_query: str, max_results: int = 10) -> list[dict[str, Any]]:
    if not settings.youtube_data_api_key:
        raise RuntimeError("YOUTUBE_DATA_API_KEY not set")

    search_resp = requests.get(
        _SEARCH_URL,
        params={
            "key": settings.youtube_data_api_key,
            "q": niche_query,
            "part": "snippet",
            "type": "video",
            "order": "viewCount",
            "maxResults": max_results,
        },
        timeout=15,
    )
    search_resp.raise_for_status()
    video_ids = [
        item["id"]["videoId"]
        for item in search_resp.json().get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    if not video_ids:
        return []

    stats_resp = requests.get(
        _VIDEOS_URL,
        params={
            "key": settings.youtube_data_api_key,
            "id": ",".join(video_ids),
            "part": "snippet,statistics",
        },
        timeout=15,
    )
    stats_resp.raise_for_status()

    results = []
    for item in stats_resp.json().get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        results.append(
            {
                "video_id": item["id"],
                "title": snippet.get("title"),
                "description": snippet.get("description", ""),
                "tags": snippet.get("tags", []),
                "channel_title": snippet.get("channelTitle"),
                "view_count": int(stats.get("viewCount", 0) or 0),
                "like_count": int(stats.get("likeCount", 0) or 0),
                "comment_count": int(stats.get("commentCount", 0) or 0),
            }
        )
    return results

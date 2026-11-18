"""
DB models: Channel, Story, Run, Video.

Kept deliberately simple in Milestone 1 — columns get richer as later
milestones need them (e.g. Story gets an embedding_id once the dedupe
vector store lands in Milestone 2).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.db import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True, nullable=False)  # e.g. "aita"
    name = Column(String, nullable=False)
    niche = Column(String, nullable=False)
    subreddits = Column(JSON, default=list)
    voices = Column(JSON, default=list)  # pool of Kokoro voice ids — Voice Agent rotates across these
    background_queries = Column(JSON, default=list)  # stock-footage search terms for this channel's theme
    persona = Column(JSON, default=dict)  # {handle, avatar_emoji} — story-card overlay identity
    daily_cap = Column(Integer, default=3)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    # Live YouTube channel stats — filled by scripts/sync_youtube_stats.py, read by the dashboard.
    yt_channel_id = Column(String, nullable=True)
    yt_title = Column(String, nullable=True)
    subscribers = Column(Integer, nullable=True)
    total_views = Column(Integer, nullable=True)
    yt_video_count = Column(Integer, nullable=True)
    stats_updated_at = Column(DateTime(timezone=True), nullable=True)

    runs = relationship("Run", back_populates="channel")
    stories = relationship("Story", back_populates="channel")
    videos = relationship("Video", back_populates="channel")


class Story(Base):
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    source = Column(String, default="stub")  # "reddit" | "web" | "stub"
    source_id = Column(String, nullable=True)  # e.g. reddit post id, for dedupe
    title = Column(String)
    content = Column(Text)
    score = Column(Integer, default=0)  # virality score from Curation Agent
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    channel = relationship("Channel", back_populates="stories")


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    status = Column(String, default="pending")  # pending | running | done | failed
    stage_log = Column(JSON, default=list)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=_utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    channel = relationship("Channel", back_populates="runs")
    video = relationship("Video", back_populates="run", uselist=False)


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    voice_used = Column(String, nullable=True)  # which voice from the channel's pool this run picked
    background_clip = Column(String, nullable=True)  # local path — Compliance checks this against recent videos
    file_path = Column(String, nullable=True)
    status = Column(String, default="draft")  # draft | queued | published | failed
    youtube_video_id = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    # What the dashboard shows: the source story + live YouTube numbers (sync_youtube_stats.py).
    story_title = Column(String, nullable=True)
    story_url = Column(String, nullable=True)
    subreddit = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    views = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)
    stats_updated_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("Run", back_populates="video")
    channel = relationship("Channel", back_populates="videos")


class Insight(Base):
    """Shared 'what's working' store — Milestone 6 (Competitor-Scan Agent
    writes to it now) and Milestone 8 (Feedback Agent also writes to it,
    same table, source='own_analytics'). Curation/Hook/Scriptwriter/
    Metadata agents read recent rows for a channel before generating."""

    __tablename__ = "insights"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    source = Column(String, nullable=False)  # "competitor_scan" | "own_analytics"
    query = Column(String, nullable=True)
    findings = Column(JSON, default=list)  # list of {title, views, likes, comments, tags, ...}
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class YouTubeToken(Base):
    """OAuth token storage — added for the GitHub-Actions-based deploy
    (going live) since Actions runs are ephemeral and have no persistent
    local disk between runs, unlike the local-file storage
    (data/youtube_tokens/<key>.json) scripts/authorize_youtube_channel.py
    originally wrote to. That script now writes here instead when pointed
    at a real DATABASE_URL; app.services.youtube_client reads/refreshes
    from here. One row per channel."""

    __tablename__ = "youtube_tokens"

    channel_key = Column(String, primary_key=True)
    token_json = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class FootageLibrary(Base):
    """One row per channel: what background clips are published for it.
    Written by scripts/publish_background_library.py, read by the dashboard
    (the clips themselves live in a GitHub Release, which the dashboard
    can't open)."""

    __tablename__ = "footage_library"

    channel_key = Column(String, primary_key=True)
    clip_count = Column(Integer, default=0)
    clips = Column(JSON, default=list)  # [{title, uploader, url, resolution, license, query}]
    quality = Column(String, nullable=True)  # "1080p" | "legacy-720p"
    size_mb = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

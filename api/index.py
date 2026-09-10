"""
Content Studio's thin dashboard API — deployed to Vercel, deliberately a
DIFFERENT (much smaller) app than the pipeline runner in backend/app/main.py.

Self-contained on purpose: Vercel's monorepo "services" build isolates each
service to its own `root` directory, so this does NOT import from
backend/app (that cross-directory import isn't reliably available at
Vercel's build time, and backend/app/graph pulls in Kokoro/ffmpeg/praw/etc.
anyway, which don't belong in a serverless function). Below is a lean,
read-only copy of just the SQLAlchemy models the dashboard actually needs
(Channel, Run, Video, Insight) — schema kept identical to
backend/app/core/models.py by convention; if that schema changes, mirror
the change here too.

Runs/trigger works differently here than the full app: instead of running
the pipeline inline (a serverless function has ~10s to respond on the free
plan — nowhere near enough for a real run), it dispatches
.github/workflows/pipeline.yml via the GitHub Actions API and returns
immediately. The dashboard already polls for the real result once that
run finishes.
"""
import os
from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dashboard.db")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")  # "owner/repo"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=1, max_overflow=0)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)


class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    niche = Column(String, nullable=False)
    subreddits = Column(JSON, default=list)
    voices = Column(JSON, default=list)
    background_queries = Column(JSON, default=list)
    persona = Column(JSON, default=dict)
    daily_cap = Column(Integer, default=3)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class Run(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    status = Column(String, default="pending")
    stage_log = Column(JSON, default=list)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=_utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    voice_used = Column(String, nullable=True)
    background_clip = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    status = Column(String, default="draft")
    youtube_video_id = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class Insight(Base):
    __tablename__ = "insights"
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    source = Column(String, nullable=False)
    query = Column(String, nullable=True)
    findings = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="Content Studio Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/channels")
def list_channels(db: Session = Depends(get_db)):
    channels = db.query(Channel).all()
    return [
        {
            "id": c.id, "key": c.key, "name": c.name, "niche": c.niche,
            "subreddits": c.subreddits, "voices": c.voices,
            "background_queries": c.background_queries, "persona": c.persona,
            "daily_cap": c.daily_cap, "active": c.active,
        }
        for c in channels
    ]


@app.get("/api/channels/{key}")
def get_channel(key: str, db: Session = Depends(get_db)):
    c = db.query(Channel).filter(Channel.key == key).first()
    if not c:
        raise HTTPException(status_code=404, detail=f"Channel '{key}' not found")
    return {
        "id": c.id, "key": c.key, "name": c.name, "niche": c.niche,
        "subreddits": c.subreddits, "voices": c.voices,
        "background_queries": c.background_queries, "persona": c.persona,
        "daily_cap": c.daily_cap, "active": c.active,
    }


@app.get("/api/runs")
def list_runs(channel_key: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Run)
    if channel_key:
        channel = db.query(Channel).filter(Channel.key == channel_key).first()
        query = query.filter(Run.channel_id == channel.id if channel else -1)
    runs = query.order_by(Run.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "channel_id": r.channel_id, "status": r.status,
            "stage_log": r.stage_log, "error": r.error,
            "started_at": r.started_at, "finished_at": r.finished_at,
        }
        for r in runs
    ]


@app.post("/api/runs/trigger/{channel_key}")
def trigger_run(channel_key: str, db: Session = Depends(get_db)):
    """Dispatches the GitHub Actions pipeline workflow for one channel —
    does NOT run anything inline. See module docstring."""
    channel = db.query(Channel).filter(Channel.key == channel_key).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_key}' not found")
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN/GITHUB_REPO not configured on this deployment")

    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/pipeline.yml/dispatches",
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"ref": "main", "inputs": {"channel_key": channel_key}},
        timeout=10,
    )
    if resp.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"GitHub dispatch failed ({resp.status_code}): {resp.text[:300]}")

    return {"status": "dispatched", "channel_key": channel_key}


@app.get("/api/videos")
def list_videos(channel_key: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Video)
    if channel_key:
        channel = db.query(Channel).filter(Channel.key == channel_key).first()
        query = query.filter(Video.channel_id == channel.id if channel else -1)
    videos = query.order_by(Video.id.desc()).limit(limit).all()
    return [
        {
            "id": v.id, "run_id": v.run_id, "channel_id": v.channel_id,
            "title": v.title, "description": v.description, "tags": v.tags,
            "voice_used": v.voice_used, "status": v.status,
            "youtube_video_id": v.youtube_video_id,
            "published_at": v.published_at, "created_at": v.created_at,
        }
        for v in videos
    ]


@app.get("/api/insights/{channel_key}")
def get_channel_insights(channel_key: str, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.key == channel_key).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_key}' not found")
    recent = (
        db.query(Insight)
        .filter(Insight.channel_id == channel.id)
        .order_by(Insight.created_at.desc())
        .limit(10)
        .all()
    )
    return [
        {"id": i.id, "source": i.source, "query": i.query, "findings": i.findings, "created_at": i.created_at}
        for i in recent
    ]

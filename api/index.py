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
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dashboard.db")
# SQLAlchemy's bare "postgresql://" scheme defaults to psycopg2, but we
# install psycopg3 (psycopg[binary], requirements.txt) — normalize so
# DATABASE_URL doesn't need the exact dialect suffix (Supabase's own UI
# gives the bare scheme). Same fix as backend/app/core/db.py.
if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")  # "owner/repo"

# Supabase's pooled connection is pgbouncer (transaction mode): psycopg3's
# auto-prepared statements fail intermittently there, so turn them off.
_connect_args = {} if DATABASE_URL.startswith("sqlite") else {"prepare_threshold": None}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=1, max_overflow=0, connect_args=_connect_args)
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
    yt_channel_id = Column(String, nullable=True)
    yt_title = Column(String, nullable=True)
    subscribers = Column(Integer, nullable=True)
    total_views = Column(Integer, nullable=True)
    yt_video_count = Column(Integer, nullable=True)
    stats_updated_at = Column(DateTime(timezone=True), nullable=True)


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
    story_title = Column(String, nullable=True)
    story_url = Column(String, nullable=True)
    subreddit = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    views = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)
    stats_updated_at = Column(DateTime(timezone=True), nullable=True)


class Story(Base):
    __tablename__ = "stories"
    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    source = Column(String)
    source_id = Column(String, nullable=True)
    title = Column(String)
    content = Column(Text)
    score = Column(Integer, default=0)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class YouTubeToken(Base):
    # Only the non-secret columns are mapped on purpose: the dashboard just
    # needs to know "is this channel authorized", never the token itself.
    __tablename__ = "youtube_tokens"
    channel_key = Column(String, primary_key=True)
    updated_at = Column(DateTime(timezone=True))


class FootageLibrary(Base):
    __tablename__ = "footage_library"
    channel_key = Column(String, primary_key=True)
    clip_count = Column(Integer, default=0)
    clips = Column(JSON, default=list)
    quality = Column(String, nullable=True)
    size_mb = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True))


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


# ---------------------------------------------------------------- helpers

# Health stats and "last run failed" alerts ignore anything before this moment:
# the first day was setup (unauthorized channels, early bugs) and would otherwise
# drag the success rate down forever. Override with HEALTH_SINCE (ISO timestamp).
HEALTH_SINCE = datetime.fromisoformat(os.environ.get("HEALTH_SINCE", "2026-11-18T08:30:00+00:00"))
CRON_HOURS_UTC = [8, 13, 18]  # keep in sync with .github/workflows/pipeline.yml
STATS_CRON = "every 3 hours (:15)"


# "Today" is the owner's day (IST), not the UTC day: a UTC day starts at 05:30 am IST, which split
# the two morning passes into different days and made the dashboard under-count "published today".
# Must match backend/app/agents/publisher_agent.py (the daily cap uses the same boundary).
# --- English-only filter (mirror of backend/app/services/lang_filter.py; this API is self-contained) ---
# Older insight rows were stored before the filter existed, so apply it again when reading them.
_STRONG = {
    "hindi", "hinglish", "urdu", "kahani", "kahaniya", "bhoot", "bhootiya", "chudail", "pyaar", "dosti",
    "bhabhi", "jaadu", "shaadi", "gaon", "ghar", "bhai", "didi", "yaar", "zindagi", "desi", "bollywood",
    "dikh", "dikha", "gaye", "gayi", "bhule", "munne", "mujhe", "tumhare", "bahut", "bohot", "sabse", "kaise",
    "kyun", "kyu", "lekin", "magar", "sachchi", "pehli", "bachpan", "dukh", "maa", "papa", "mummy", "beta", "beti",
    "shivamsingh", "varunbundela", "itna", "chalta", "pyaaz", "moye", "paavi",
}
_WEAK = {
    "ki", "ke", "ka", "ko", "mein", "se", "wali", "wala", "hai", "hain", "aur", "yeh", "kya", "ek", "tha", "thi",
    "nahi", "raat", "ne", "mai", "mere", "mera", "meri", "jana", "na", "ye", "wo", "woh", "gaya", "hua", "hui",
    "raha", "rahi", "apna", "apni", "tum", "hum", "kar", "karo", "sach", "baad", "log",
}
_WORD = re.compile(r"[a-z]+")


def _looks_english(text) -> bool:
    if not text:
        return False
    letters = [ch for ch in text if unicodedata.category(ch).startswith("L")]
    if not letters:
        return False
    if sum(1 for ch in letters if "LATIN" not in unicodedata.name(ch, "")) / len(letters) > 0.2:
        return False
    words = _WORD.findall(text.lower())
    if any(w in _STRONG for w in words):
        return False
    return sum(1 for w in words if w in _WEAK) < 2


def _hashtag_ok(tag: str) -> bool:
    body = tag.lstrip("#").replace("_", " ")
    return bool(body) and body.isascii() and not any(w in _STRONG for w in _WORD.findall(body.lower()))


DAY_TZ = timezone(timedelta(hours=5, minutes=30))


def _day_start(now: Optional[datetime] = None) -> datetime:
    """Start of the current IST day, as an aware UTC instant."""
    local = (now or _utcnow()).astimezone(DAY_TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _utc_midnight(now: Optional[datetime] = None) -> datetime:
    now = now or _utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _next_runs(n: int = 4) -> list[str]:
    now, out, day = _utcnow(), [], _utc_midnight()
    while len(out) < n:
        for h in CRON_HOURS_UTC:
            t = day + timedelta(hours=h)
            if t > now:
                out.append(t.isoformat())
        day += timedelta(days=1)
    return out[:n]


def _gh_headers():
    return {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}


def _gh_ready() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_REPO)


def _channel_map(db: Session) -> dict[int, Channel]:
    return {c.id: c for c in db.query(Channel).all()}


def _video_dict(v: Video, ch: Optional[Channel]) -> dict:
    return {
        "id": v.id, "run_id": v.run_id, "channel_id": v.channel_id,
        "channel_key": ch.key if ch else None, "channel_name": ch.name if ch else None,
        "title": v.title, "description": v.description, "tags": v.tags,
        "voice_used": v.voice_used, "status": v.status,
        "youtube_video_id": v.youtube_video_id,
        "youtube_url": f"https://www.youtube.com/shorts/{v.youtube_video_id}" if v.youtube_video_id else None,
        "thumbnail": f"https://i.ytimg.com/vi/{v.youtube_video_id}/hqdefault.jpg" if v.youtube_video_id else None,
        "story_title": v.story_title, "story_url": v.story_url, "subreddit": v.subreddit,
        "views": v.views, "likes": v.likes, "comments": v.comments,
        "stats_updated_at": v.stats_updated_at,
        "published_at": v.published_at, "created_at": v.created_at,
    }


def _run_dict(r: Run, ch: Optional[Channel], video: Optional[Video] = None) -> dict:
    fin, st = _aware(r.finished_at), _aware(r.started_at)
    return {
        "id": r.id, "channel_id": r.channel_id,
        "channel_key": ch.key if ch else None, "channel_name": ch.name if ch else None,
        "status": r.status, "stage_log": r.stage_log, "error": r.error,
        "started_at": r.started_at, "finished_at": r.finished_at,
        "duration_seconds": int((fin - st).total_seconds()) if fin and st else None,
        "video_title": video.title if video else None,
        "youtube_video_id": video.youtube_video_id if video else None,
    }


def _channel_dict(c: Channel, db: Session, *, authorized: set, libs: dict, today_counts: dict, agg: dict) -> dict:
    a = agg.get(c.id, {})
    lib = libs.get(c.key)
    return {
        "id": c.id, "key": c.key, "name": c.name, "niche": c.niche,
        "subreddits": c.subreddits, "voices": c.voices,
        "background_queries": c.background_queries, "persona": c.persona,
        "daily_cap": c.daily_cap, "active": c.active,
        "authorized": c.key in authorized,
        "yt_channel_id": c.yt_channel_id, "yt_title": c.yt_title,
        "youtube_url": f"https://www.youtube.com/channel/{c.yt_channel_id}" if c.yt_channel_id else None,
        "subscribers": c.subscribers, "total_views": c.total_views, "yt_video_count": c.yt_video_count,
        "stats_updated_at": c.stats_updated_at,
        "published_today": today_counts.get(c.id, 0),
        "published_total": a.get("published", 0),
        "views": a.get("views", 0), "likes": a.get("likes", 0),
        "last_published_at": a.get("last_published"),
        "runs_7d_done": a.get("done7", 0), "runs_7d_failed": a.get("failed7", 0),
        "last_run_status": a.get("last_status"), "last_run_error": a.get("last_error"),
        "last_run_at": a.get("last_run_at"),
        "footage_clips": lib.clip_count if lib else 0,
        "footage_quality": lib.quality if lib else None,
    }


def _aggregates(db: Session) -> tuple[set, dict, dict, dict]:
    authorized = {r[0] for r in db.query(YouTubeToken.channel_key).all()}
    libs = {l.channel_key: l for l in db.query(FootageLibrary).all()}
    day = _day_start()
    today_counts = {
        cid: n for cid, n in db.query(Video.channel_id, func.count(Video.id))
        .filter(Video.status == "published", Video.published_at >= day).group_by(Video.channel_id)
    }
    agg: dict[int, dict] = {}
    for cid, n, views, likes, last in db.query(
        Video.channel_id, func.count(Video.id), func.coalesce(func.sum(Video.views), 0),
        func.coalesce(func.sum(Video.likes), 0), func.max(Video.published_at),
    ).filter(Video.status == "published").group_by(Video.channel_id):
        agg[cid] = {"published": n, "views": int(views), "likes": int(likes), "last_published": last}
    week = max(HEALTH_SINCE, _utcnow() - timedelta(days=7))
    for cid, status, n in db.query(Run.channel_id, Run.status, func.count(Run.id)).filter(
        Run.started_at >= week, Run.status.in_(["done", "dry_run", "failed"])
    ).group_by(Run.channel_id, Run.status):
        key = "failed7" if status == "failed" else "done7"
        agg.setdefault(cid, {})[key] = agg.get(cid, {}).get(key, 0) + n
    for cid in {r[0] for r in db.query(Run.channel_id).distinct()}:
        last = db.query(Run).filter(Run.channel_id == cid).order_by(Run.id.desc()).first()
        d = agg.setdefault(cid, {})
        d["last_status"], d["last_error"], d["last_run_at"] = last.status, last.error, last.started_at
    return authorized, libs, today_counts, agg


# ---------------------------------------------------------------- routes

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/channels")
def list_channels(db: Session = Depends(get_db)):
    authorized, libs, today_counts, agg = _aggregates(db)
    return [
        _channel_dict(c, db, authorized=authorized, libs=libs, today_counts=today_counts, agg=agg)
        for c in db.query(Channel).order_by(Channel.id).all()
    ]


@app.get("/api/channels/{key}")
def get_channel(key: str, db: Session = Depends(get_db)):
    c = db.query(Channel).filter(Channel.key == key).first()
    if not c:
        raise HTTPException(status_code=404, detail=f"Channel '{key}' not found")
    authorized, libs, today_counts, agg = _aggregates(db)
    return _channel_dict(c, db, authorized=authorized, libs=libs, today_counts=today_counts, agg=agg)


class ChannelPatch(BaseModel):
    active: Optional[bool] = None
    daily_cap: Optional[int] = None


@app.patch("/api/channels/{key}")
def patch_channel(key: str, body: ChannelPatch, db: Session = Depends(get_db)):
    c = db.query(Channel).filter(Channel.key == key).first()
    if not c:
        raise HTTPException(status_code=404, detail=f"Channel '{key}' not found")
    if body.active is not None:
        c.active = body.active
    if body.daily_cap is not None:
        if not 1 <= body.daily_cap <= 10:
            raise HTTPException(status_code=400, detail="daily_cap must be between 1 and 10")
        c.daily_cap = body.daily_cap
    db.commit()
    return {"key": c.key, "active": c.active, "daily_cap": c.daily_cap}


@app.get("/api/runs")
def list_runs(
    channel_key: Optional[str] = None, status: Optional[str] = None,
    limit: int = 50, offset: int = 0, db: Session = Depends(get_db),
):
    q = db.query(Run)
    if channel_key:
        ch = db.query(Channel).filter(Channel.key == channel_key).first()
        q = q.filter(Run.channel_id == (ch.id if ch else -1))
    if status:
        q = q.filter(Run.status == status)
    runs = q.order_by(Run.id.desc()).offset(offset).limit(min(limit, 200)).all()
    chans = _channel_map(db)
    vids = {v.run_id: v for v in db.query(Video).filter(Video.run_id.in_([r.id for r in runs])).all()} if runs else {}
    return [_run_dict(r, chans.get(r.channel_id), vids.get(r.id)) for r in runs]


@app.post("/api/runs/trigger/{channel_key}")
def trigger_run(channel_key: str, dry_run: bool = False, db: Session = Depends(get_db)):
    """Dispatches the GitHub Actions pipeline workflow for one channel —
    does NOT run anything inline. See module docstring."""
    channel = db.query(Channel).filter(Channel.key == channel_key).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_key}' not found")
    if not _gh_ready():
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN/GITHUB_REPO not configured on this deployment")

    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/pipeline.yml/dispatches",
        headers=_gh_headers(),
        json={"ref": "main", "inputs": {"channel_key": channel_key, "dry_run": "true" if dry_run else "false"}},
        timeout=10,
    )
    if resp.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"GitHub dispatch failed ({resp.status_code}): {resp.text[:300]}")
    return {"status": "dispatched", "channel_key": channel_key, "dry_run": dry_run}


@app.post("/api/stats/sync")
def trigger_stats_sync():
    if not _gh_ready():
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN/GITHUB_REPO not configured on this deployment")
    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/stats.yml/dispatches",
        headers=_gh_headers(), json={"ref": "main"}, timeout=10,
    )
    if resp.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"GitHub dispatch failed ({resp.status_code}): {resp.text[:300]}")
    return {"status": "dispatched"}


@app.get("/api/videos")
def list_videos(
    channel_key: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None,
    limit: int = 60, offset: int = 0, db: Session = Depends(get_db),
):
    query = db.query(Video)
    if channel_key:
        ch = db.query(Channel).filter(Channel.key == channel_key).first()
        query = query.filter(Video.channel_id == (ch.id if ch else -1))
    if status:
        query = query.filter(Video.status == status)
    if q:
        query = query.filter(Video.title.ilike(f"%{q}%"))
    videos = query.order_by(Video.id.desc()).offset(offset).limit(min(limit, 200)).all()
    chans = _channel_map(db)
    return [_video_dict(v, chans.get(v.channel_id)) for v in videos]


@app.get("/api/stories")
def list_stories(channel_key: Optional[str] = None, limit: int = 40, db: Session = Depends(get_db)):
    query = db.query(Story)
    if channel_key:
        ch = db.query(Channel).filter(Channel.key == channel_key).first()
        query = query.filter(Story.channel_id == (ch.id if ch else -1))
    chans = _channel_map(db)
    return [
        {
            "id": s.id, "channel_key": chans[s.channel_id].key if s.channel_id in chans else None,
            "title": s.title, "source": s.source, "source_id": s.source_id, "score": s.score,
            "used": s.used, "created_at": s.created_at,
            "url": f"https://www.reddit.com/comments/{s.source_id}" if s.source == "reddit" and s.source_id else None,
            "preview": (s.content or "")[:280],
        }
        for s in query.order_by(Story.id.desc()).limit(min(limit, 200)).all()
    ]


@app.get("/api/library")
def get_library(db: Session = Depends(get_db)):
    libs = {l.channel_key: l for l in db.query(FootageLibrary).all()}
    out = []
    for c in db.query(Channel).order_by(Channel.id).all():
        l = libs.get(c.key)
        out.append({
            "channel_key": c.key, "channel_name": c.name,
            "clip_count": l.clip_count if l else 0, "quality": l.quality if l else None,
            "size_mb": l.size_mb if l else None, "clips": (l.clips if l else []) or [],
            "updated_at": l.updated_at if l else None,
        })
    return out


@app.get("/api/activity")
def activity(days: int = 14, db: Session = Depends(get_db)):
    """Per-day publishing activity (IST days) with a per-channel breakdown, for the interactive chart."""
    days = max(7, min(int(days), 60))
    start = _day_start() - timedelta(days=days - 1)
    start_local = start.astimezone(DAY_TZ)
    chans = db.query(Channel).order_by(Channel.id).all()
    by_id = {c.id: c for c in chans}
    out = {
        (start_local + timedelta(days=i)).date().isoformat(): {"published": 0, "failed": 0, "views": 0, "by_channel": {}, "failed_by_channel": {}}
        for i in range(days)
    }
    for pub, ch_id, views in db.query(Video.published_at, Video.channel_id, Video.views).filter(Video.status == "published", Video.published_at >= start):
        k = _aware(pub).astimezone(DAY_TZ).date().isoformat()
        if k in out and ch_id in by_id:
            d = out[k]
            key = by_id[ch_id].key
            d["published"] += 1
            d["views"] += views or 0
            d["by_channel"][key] = d["by_channel"].get(key, 0) + 1
    # Failures from before go-live were setup noise; the success-rate stat ignores them too.
    for st, ch_id in db.query(Run.started_at, Run.channel_id).filter(Run.status == "failed", Run.started_at >= max(start, HEALTH_SINCE)):
        k = _aware(st).astimezone(DAY_TZ).date().isoformat()
        if k in out and ch_id in by_id:
            d = out[k]
            key = by_id[ch_id].key
            d["failed"] += 1
            d["failed_by_channel"][key] = d["failed_by_channel"].get(key, 0) + 1
    return {
        "days": days,
        "channels": [{"key": c.key, "name": c.name} for c in chans],
        "series": [{"date": d, **v} for d, v in out.items()],
    }


@app.get("/api/overview")
def overview(db: Session = Depends(get_db)):
    now = _utcnow()
    authorized, libs, today_counts, agg = _aggregates(db)
    channels = db.query(Channel).order_by(Channel.id).all()
    cdicts = [_channel_dict(c, db, authorized=authorized, libs=libs, today_counts=today_counts, agg=agg) for c in channels]

    # 14-day activity chart
    start = _day_start() - timedelta(days=13)
    start_local = start.astimezone(DAY_TZ)
    days = {(start_local + timedelta(days=i)).date().isoformat(): {"published": 0, "failed": 0} for i in range(14)}
    for pub in db.query(Video.published_at).filter(Video.status == "published", Video.published_at >= start):
        k = _aware(pub[0]).astimezone(DAY_TZ).date().isoformat()
        if k in days:
            days[k]["published"] += 1
    for st in db.query(Run.started_at).filter(Run.status == "failed", Run.started_at >= start):
        k = _aware(st[0]).astimezone(DAY_TZ).date().isoformat()
        if k in days:
            days[k]["failed"] += 1

    since = max(HEALTH_SINCE, now - timedelta(days=7))
    # A finished dry run means the pipeline worked end to end, so it counts as healthy.
    done7 = db.query(func.count(Run.id)).filter(Run.status.in_(["done", "dry_run"]), Run.started_at >= since).scalar() or 0
    failed7 = db.query(func.count(Run.id)).filter(Run.status == "failed", Run.started_at >= since).scalar() or 0
    failed24 = db.query(func.count(Run.id)).filter(Run.status == "failed", Run.started_at >= max(HEALTH_SINCE, now - timedelta(hours=24))).scalar() or 0
    last_run = db.query(Run).order_by(Run.id.desc()).first()
    chans = {c.id: c for c in channels}

    alerts = []
    for c in cdicts:
        if not c["authorized"]:
            alerts.append({"level": "error", "title": f"{c['name']} isn't authorized for YouTube", "detail": "Uploads will fail until it's authorized.", "channel_key": c["key"]})
        if not c["active"]:
            why = " Its footage is still the old 720p set." if c["footage_quality"] == "legacy-720p" else ""
            alerts.append({"level": "warn", "title": f"{c['name']} is paused", "detail": "Not part of scheduled runs." + why, "channel_key": c["key"]})
        elif c["last_run_status"] == "failed" and c["last_run_at"] and _aware(c["last_run_at"]) >= HEALTH_SINCE:
            alerts.append({"level": "error", "title": f"{c['name']}: last run failed", "detail": (c["last_run_error"] or "No reason was recorded (run predates error capture).")[:220], "channel_key": c["key"]})
        elif c["active"] and c["last_published_at"] and now - _aware(c["last_published_at"]) > timedelta(hours=48):
            alerts.append({"level": "warn", "title": f"{c['name']}: nothing posted in 48h", "detail": "Active, but no recent upload.", "channel_key": c["key"]})
        if c["footage_quality"] == "legacy-720p" and c["active"]:
            alerts.append({"level": "warn", "title": f"{c['name']} still uses 720p footage", "detail": "Rebuild its background library.", "channel_key": c["key"]})
    stamps = [_aware(c["stats_updated_at"]) for c in cdicts if c["stats_updated_at"]]
    if not stamps:
        alerts.append({"level": "info", "title": "YouTube stats haven't synced yet", "detail": "Runs every 3 hours from GitHub Actions (or use Sync now on the System page)."})
    elif now - max(stamps) > timedelta(hours=8):
        alerts.append({"level": "warn", "title": "YouTube stats are stale", "detail": f"Last sync {max(stamps).isoformat()}."})
    if not _gh_ready():
        alerts.append({"level": "warn", "title": "GitHub integration not configured", "detail": "Set GITHUB_TOKEN and GITHUB_REPO on Vercel to enable Trigger / Sync / workflow history."})

    recent_runs = db.query(Run).order_by(Run.id.desc()).limit(8).all()
    vids = {v.run_id: v for v in db.query(Video).filter(Video.run_id.in_([r.id for r in recent_runs])).all()} if recent_runs else {}
    top = db.query(Video).filter(Video.status == "published").order_by(func.coalesce(Video.views, 0).desc(), Video.id.desc()).limit(5).all()

    return {
        "now": now,
        "totals": {
            "channels": len(cdicts), "active": sum(1 for c in cdicts if c["active"]),
            "published": sum(c["published_total"] for c in cdicts),
            "views": sum(c["views"] for c in cdicts),
            "likes": sum(c["likes"] for c in cdicts),
            "subscribers": sum(c["subscribers"] or 0 for c in cdicts),
            "authorized": sum(1 for c in cdicts if c["authorized"]),
            "hd_footage": sum(1 for c in cdicts if c["footage_quality"] == "1080p"),
        },
        "today": {
            "published": sum(c["published_today"] for c in cdicts),
            "capacity": sum(c["daily_cap"] for c in cdicts if c["active"]),
            "channels": [
                {"key": c["key"], "name": c["name"], "published": c["published_today"], "cap": c["daily_cap"], "active": c["active"]}
                for c in cdicts
            ],
        },
        "activity": [{"date": d, **v} for d, v in days.items()],
        "health": {
            "success_rate_7d": round(100 * done7 / (done7 + failed7)) if (done7 + failed7) else None,
            "done_7d": done7, "failed_7d": failed7, "failed_24h": failed24,
            "since": max(HEALTH_SINCE, now - timedelta(days=7)),
            "last_run": _run_dict(last_run, chans.get(last_run.channel_id)) if last_run else None,
            "next_runs": _next_runs(),
            "stats_updated_at": max(stamps) if stamps else None,
        },
        "alerts": alerts,
        "recent_runs": [_run_dict(r, chans.get(r.channel_id), vids.get(r.id)) for r in recent_runs],
        "top_videos": [_video_dict(v, chans.get(v.channel_id)) for v in top],
    }


@app.get("/api/actions")
def list_actions(limit: int = 20):
    """Recent GitHub Actions runs (pipeline + stats workflows)."""
    if not _gh_ready():
        return {"configured": False, "runs": []}
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs",
        headers=_gh_headers(), params={"per_page": min(limit, 50)}, timeout=10,
    )
    if resp.status_code >= 300:
        return {"configured": True, "error": f"GitHub returned {resp.status_code}", "runs": []}
    runs = []
    for r in resp.json().get("workflow_runs", []):
        start = r.get("run_started_at") or r.get("created_at")
        end = r.get("updated_at")
        dur = None
        if start and end and r.get("status") == "completed":
            dur = int((datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds())
        runs.append({
            "id": r["id"], "workflow": r.get("name"), "event": r.get("event"),
            "status": r.get("status"), "conclusion": r.get("conclusion"),
            "created_at": r.get("created_at"), "duration_seconds": dur,
            "url": r.get("html_url"), "title": r.get("display_title"),
        })
    return {"configured": True, "runs": runs, "repo": GITHUB_REPO}


@app.get("/api/system")
def system(db: Session = Depends(get_db)):
    stamps = [_aware(c.stats_updated_at) for c in db.query(Channel).all() if c.stats_updated_at]
    gh = {"configured": _gh_ready(), "repo": GITHUB_REPO}
    if _gh_ready():
        try:
            r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}", headers=_gh_headers(), timeout=8)
            gh["ok"], gh["status"] = r.status_code == 200, r.status_code
        except requests.RequestException as exc:
            gh["ok"], gh["status"] = False, str(exc)[:120]
    return {
        "database": {"ok": True, "rows": {
            "channels": db.query(func.count(Channel.id)).scalar(), "runs": db.query(func.count(Run.id)).scalar(),
            "videos": db.query(func.count(Video.id)).scalar(), "stories": db.query(func.count(Story.id)).scalar(),
        }},
        "github": gh,
        "schedule": {"pipeline_hours_utc": CRON_HOURS_UTC, "next_runs": _next_runs(6), "stats": STATS_CRON},
        "stats_updated_at": max(stamps) if stamps else None,
        "services": [
            {"name": "GitHub Actions", "role": "Runs the pipeline on a cron schedule"},
            {"name": "Supabase", "role": "Postgres: channels, runs, videos, tokens"},
            {"name": "Vercel", "role": "This dashboard + its API"},
            {"name": "Arctic Shift", "role": "Reddit story sourcing"},
            {"name": "Groq / Gemini", "role": "Hook, script and metadata writing"},
            {"name": "Kokoro + faster-whisper", "role": "Narration and caption timing (local models)"},
        ],
    }


@app.get("/api/insights/{channel_key}")
def get_channel_insights(channel_key: str, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.key == channel_key).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_key}' not found")
    recent = (
        db.query(Insight).filter(Insight.channel_id == channel.id)
        .order_by(Insight.created_at.desc()).limit(10).all()
    )
    return [
        {"id": i.id, "source": i.source, "query": i.query, "findings": i.findings, "created_at": i.created_at}
        for i in recent
    ]


@app.get("/api/learning")
def learning(db: Session = Depends(get_db)):
    """Status of the learning loop: Competitor-Scan + Feedback insights per channel, and whether
    they are fresh enough (<= 7 days, same cut-off the pipeline prompts use) to be feeding the agents."""
    now = _utcnow()
    fresh_cut = now - timedelta(days=7)
    channels = db.query(Channel).order_by(Channel.id).all()
    rows = db.query(Insight).filter(Insight.created_at >= now - timedelta(days=14)).order_by(Insight.created_at.desc()).all()

    perf = {
        cid: (n, int(v or 0), best)
        for cid, n, v, best in db.query(
            Video.channel_id, func.count(Video.id), func.sum(Video.views), func.max(Video.views)
        ).filter(Video.status == "published").group_by(Video.channel_id)
    }
    out = []
    for c in channels:
        mine = [r for r in rows if r.channel_id == c.id]
        comp = [r for r in mine if r.source == "competitor_scan"]
        own = [r for r in mine if r.source == "own_analytics"]
        comp_fresh = [r for r in comp if _aware(r.created_at) >= fresh_cut]

        def f(r):
            return r.findings if isinstance(r.findings, dict) else {}

        titles, tags = [], {}
        for r in comp_fresh:
            for t in f(r).get("top_titles", []):
                if t not in titles and _looks_english(t):
                    titles.append(t)
            for h in f(r).get("top_hashtags", []):
                if not _hashtag_ok(h):
                    continue
                tags[h.lower()] = tags.get(h.lower(), 0) + 1
        own_latest = f(own[0]) if own else {}
        n, views, best = perf.get(c.id, (0, 0, 0))
        top_video = None
        if best:
            v = (
                db.query(Video).filter(Video.channel_id == c.id, Video.status == "published", Video.views == best)
                .order_by(Video.published_at.desc()).first()
            )
            if v:
                top_video = {"title": v.title, "views": v.views, "id": v.youtube_video_id}
        out.append({
            "key": c.key, "name": c.name, "active": c.active,
            "competitor": {
                "last_at": comp[0].created_at if comp else None,
                "fresh": bool(comp_fresh), "scans": len(comp_fresh),
                "queries": sorted({r.query for r in comp_fresh if r.query}),
                "top_titles": titles[:8],
                "top_hashtags": [h for h, _ in sorted(tags.items(), key=lambda kv: -kv[1])[:10]],
            },
            "own": {
                "last_at": own[0].created_at if own else None,
                "fresh": bool(own) and _aware(own[0].created_at) >= fresh_cut,
                "sample_size": own_latest.get("sample_size", 0),
                "basis": own_latest.get("basis", "youtube_analytics" if own_latest.get("sample_size") else "none"),
                "top_titles": own_latest.get("top_titles", []),
            },
            "performance": {"videos": n, "views": views, "avg_views": round(views / n, 1) if n else 0, "top_video": top_video},
        })
    last_any = rows[0].created_at if rows else None
    return {
        "last_refresh": last_any,
        "stale": last_any is None or _aware(last_any) < now - timedelta(hours=36),
        "channels": out,
        "totals": {
            "competitor_fresh": sum(1 for c in out if c["competitor"]["fresh"]),
            "own_with_data": sum(1 for c in out if c["own"]["sample_size"]),
            "channels": len(out),
        },
        "feeds": [
            {"agent": "Curation", "uses": "Boosts stories whose wording overlaps with top titles (own + competitors)."},
            {"agent": "Hook", "uses": "Sees the top titles and hashtags as style examples."},
            {"agent": "Script", "uses": "Sees the same winning-titles context."},
            {"agent": "Metadata", "uses": "Writes title and hashtags informed by what is working, without copying."},
        ],
        "schedule": "Daily 03:00 UTC (GitHub may start it a few hours late)",
    }

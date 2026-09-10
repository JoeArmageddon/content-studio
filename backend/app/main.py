from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.db import SessionLocal, init_db
from app.core.models import Channel
from app.routes import channels as channels_routes
from app.routes import insights as insights_routes
from app.routes import runs as runs_routes
from app.routes import videos as videos_routes
from app.scheduler import start_scheduler, stop_scheduler

CHANNELS_YAML = Path(__file__).resolve().parent / "config" / "channels.yaml"
# Milestone 8: FastAPI serves the built dashboard too, matching the
# single-container deploy pattern (Dockerfile) — same approach StoriqueOS
# used. Guarded by os.path.exists so `npm run dev`'s separate Vite server
# stays the normal local-dev path; this only kicks in once `npm run build`
# has actually produced a dist/ folder.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _seed_channels() -> None:
    """Upserts channels.yaml into the DB — config file is the source of truth."""
    with open(CHANNELS_YAML) as f:
        defs = yaml.safe_load(f)["channels"]

    db = SessionLocal()
    try:
        for d in defs:
            channel = db.query(Channel).filter(Channel.key == d["key"]).first()
            if channel is None:
                channel = Channel(key=d["key"])
                db.add(channel)
            channel.name = d["name"]
            channel.niche = d["niche"]
            channel.subreddits = d.get("subreddits", [])
            channel.voices = d.get("voices", [])
            channel.background_queries = d.get("background_queries", [])
            channel.persona = d.get("persona", {})
            channel.daily_cap = d.get("daily_cap", 3)
            channel.active = d.get("active", True)
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_channels()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Content Studio",
    description="Multi-channel, agent-driven content pipeline — Phase 1: Storique",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(channels_routes.router, prefix="/api")
app.include_router(runs_routes.router, prefix="/api")
app.include_router(videos_routes.router, prefix="/api")
app.include_router(insights_routes.router, prefix="/api")

_FRONTEND_ASSETS = FRONTEND_DIST / "assets"
if _FRONTEND_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_ASSETS), name="frontend_assets")


@app.get("/")
def root():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"status": "Content Studio API running — frontend not built (run `npm run build` in frontend/)"}


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    """Client-side routes (e.g. /channels/aita) — serve the SPA shell and
    let React Router take over, same as StoriqueOS's frontend-serving
    pattern. Anything under /api or /assets is handled above and never
    reaches this catch-all."""
    if full_path.startswith("api/") or full_path.startswith("assets/"):
        raise HTTPException(status_code=404)
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404)

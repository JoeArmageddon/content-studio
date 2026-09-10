from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Channel

router = APIRouter(prefix="/channels", tags=["channels"])


def _serialize(channel: Channel) -> dict:
    return {
        "id": channel.id,
        "key": channel.key,
        "name": channel.name,
        "niche": channel.niche,
        "subreddits": channel.subreddits,
        "voices": channel.voices,
        "background_queries": channel.background_queries,
        "persona": channel.persona,
        "daily_cap": channel.daily_cap,
        "active": channel.active,
    }


@router.get("")
def list_channels(db: Session = Depends(get_db)):
    return [_serialize(c) for c in db.query(Channel).all()]


@router.get("/{key}")
def get_channel(key: str, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.key == key).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{key}' not found")
    return _serialize(channel)

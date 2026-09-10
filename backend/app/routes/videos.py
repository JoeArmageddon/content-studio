from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Channel, Video

router = APIRouter(prefix="/videos", tags=["videos"])


def _serialize(video: Video) -> dict:
    return {
        "id": video.id,
        "run_id": video.run_id,
        "channel_id": video.channel_id,
        "title": video.title,
        "description": video.description,
        "tags": video.tags,
        "voice_used": video.voice_used,
        "status": video.status,
        "youtube_video_id": video.youtube_video_id,
        "published_at": video.published_at,
        "created_at": video.created_at,
    }


@router.get("")
def list_videos(channel_key: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Video)
    if channel_key:
        channel = db.query(Channel).filter(Channel.key == channel_key).first()
        query = query.filter(Video.channel_id == channel.id if channel else -1)
    videos = query.order_by(Video.id.desc()).limit(limit).all()
    return [_serialize(v) for v in videos]

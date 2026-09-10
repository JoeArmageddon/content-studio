from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Channel
from app.services import insights as insights_service

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/{channel_key}")
def get_channel_insights(channel_key: str, db: Session = Depends(get_db)):
    channel = db.query(Channel).filter(Channel.key == channel_key).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_key}' not found")

    recent = insights_service.get_recent(channel.id, max_age_days=30, limit=10)
    return [
        {
            "id": i.id,
            "source": i.source,
            "query": i.query,
            "findings": i.findings,
            "created_at": i.created_at,
        }
        for i in recent
    ]

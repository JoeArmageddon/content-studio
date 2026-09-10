"""
Local dedupe check — Milestone 2.

Originally scoped in the architecture doc as sentence-transformers + FAISS;
swapped for a zero-extra-dependency stdlib approach (difflib fuzzy
title matching against already-used stories, plus an exact source_id
check) since full sentence embeddings pull in a heavy torch dependency for
little benefit at current story volume. A linear scan over the last 500
used stories is more than fast enough at this scale. Revisit with real
embeddings if fuzzy string matching starts missing paraphrased duplicates.
"""
import difflib
from typing import Optional

from sqlalchemy.orm import Session

from app.core.models import Story


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def find_duplicate(db: Session, source_id: Optional[str], title: str, threshold: float = 0.85) -> bool:
    """True if this candidate matches a story already marked used (any channel —
    a story shouldn't be reused across channels either)."""
    if source_id:
        exact = (
            db.query(Story)
            .filter(Story.source_id == source_id, Story.used.is_(True))
            .first()
        )
        if exact:
            return True

    recent = (
        db.query(Story)
        .filter(Story.used.is_(True))
        .order_by(Story.id.desc())
        .limit(500)
        .all()
    )
    return any(_similarity(title, s.title or "") >= threshold for s in recent)

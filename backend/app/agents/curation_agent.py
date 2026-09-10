"""
Curation/Ranking Agent — Milestone 2 (Milestone 8: factors in what's working).

Scores sourced candidates for virality potential (Reddit score + comment
velocity, plus a keyword-overlap bonus against recently-successful titles —
see _insight_boost) and picks the highest-scoring one that isn't a
duplicate of a story already used, anywhere (app.services.vector_store) —
so the same story never gets reused across channels or runs. This agent
only reads for ranking/dedupe; persisting the chosen story as "used"
happens once the full run's outcome is known (see routes/runs.py and
scheduler.py).
"""
from app.core.db import SessionLocal
from app.graph.state import PipelineState
from app.services import insights
from app.services.vector_store import find_duplicate

_INSIGHT_BOOST_PER_SHARED_WORD = 15
# Words too common to mean anything about topic similarity — skip them so
# the boost reflects real thematic overlap, not just shared filler words.
_STOPWORDS = {
    "a", "an", "the", "for", "to", "of", "in", "on", "at", "is", "my", "i",
    "and", "or", "but", "with", "was", "am", "aita", "tifu", "update",
}


def _virality_score(candidate: dict) -> float:
    return candidate.get("score", 0) + candidate.get("num_comments", 0) * 2


def _insight_boost(candidate_title: str, reference_titles: list[str]) -> float:
    if not reference_titles:
        return 0.0
    candidate_words = set(candidate_title.lower().split()) - _STOPWORDS
    if not candidate_words:
        return 0.0
    best_overlap = 0
    for title in reference_titles:
        title_words = set((title or "").lower().split()) - _STOPWORDS
        best_overlap = max(best_overlap, len(candidate_words & title_words))
    return best_overlap * _INSIGHT_BOOST_PER_SHARED_WORD


def run(state: PipelineState) -> PipelineState:
    candidates = state.get("candidates") or []
    channel = state.get("channel", {})
    reference_titles = insights.top_titles(channel.get("id"))

    ranked = sorted(
        candidates,
        key=lambda c: _virality_score(c) + _insight_boost(c.get("title", ""), reference_titles),
        reverse=True,
    )

    db = SessionLocal()
    try:
        chosen = None
        for candidate in ranked:
            if not find_duplicate(db, candidate.get("source_id"), candidate.get("title", "")):
                chosen = candidate
                break
    finally:
        db.close()

    if chosen:
        chosen["curated"] = True
        chosen["duplicate"] = False
        state["story"] = chosen
    else:
        state["story"] = None
        state.setdefault("compliance_notes", []).append(
            "No non-duplicate candidate found — sourced stories were empty or all already used."
        )

    state.setdefault("stage_log", []).append("curate")
    return state

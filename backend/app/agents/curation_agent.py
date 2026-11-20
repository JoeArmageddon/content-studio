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
from itertools import islice

from app.core.db import SessionLocal
from app.graph.state import PipelineState
from app.services import insights, niche_gate
from app.services.vector_store import find_duplicate

_INSIGHT_BOOST_PER_SHARED_WORD = 15
_GATE_BATCH, _GATE_BATCHES = 8, 4  # niche-fit check: up to 32 top candidates, 8 per LLM call
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
        # Lazy: duplicate checks only run for candidates we actually look at.
        fresh = (c for c in ranked if not find_duplicate(db, c.get("source_id"), c.get("title", "")))
        chosen = None
        off_niche = False
        if not niche_gate.is_gated(channel.get("key")):
            chosen = next(fresh, None)
        else:
            # Broad source subreddits: prefer a story the LLM grades as a strong niche fit (2), accept
            # the best loosely-on-theme one (1) if no strong fit turns up, never an off-niche one (0).
            seen_any = False
            loose = None
            for _ in range(_GATE_BATCHES):
                batch = list(islice(fresh, _GATE_BATCH))
                if not batch:
                    break
                seen_any = True
                scores = niche_gate.fit_scores(channel["key"], batch)
                if scores is None:  # screener unavailable: fall back to plain ranking
                    chosen = loose or batch[0]
                    break
                chosen = next((c for c, sc in zip(batch, scores) if sc == 2), None)
                if chosen:
                    break
                loose = loose or next((c for c, sc in zip(batch, scores) if sc == 1), None)
            chosen = chosen or loose
            off_niche = seen_any and chosen is None
    finally:
        db.close()

    if chosen:
        chosen["curated"] = True
        chosen["duplicate"] = False
        state["story"] = chosen
    else:
        state["story"] = None
        msg = (
            "No story to use: sourcing returned no candidates (source API error or empty) "
            if not candidates else
            "No story to use: none of the best candidates fit this channel's niche "
            if off_niche else
            "No story to use: every sourced candidate was already used "
        )
        state["error"] = msg.strip() + "."
        state.setdefault("compliance_notes", []).append(
            "No non-duplicate candidate found, sourced stories were empty or all already used."
        )

    state.setdefault("stage_log", []).append("curate")
    return state

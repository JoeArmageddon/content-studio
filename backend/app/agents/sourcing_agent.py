"""
Sourcing Agent — Milestone 2.

Pulls raw candidate stories from the channel's configured subreddits via
app.services.reddit_client (PRAW if Reddit API credentials are set, else a
zero-setup public-JSON fallback — see that module). The general web-search
pass mentioned in the architecture doc (so channels aren't 100%
Reddit-dependent) is still TODO for a later milestone.
"""
from app.graph.state import PipelineState
from app.services import reddit_client


def run(state: PipelineState) -> PipelineState:
    channel = state.get("channel", {})
    subreddits = channel.get("subreddits", [])

    try:
        candidates = reddit_client.fetch_stories(subreddits, limit=10)
    except Exception as exc:  # noqa: BLE001 — sourcing must not crash the whole run
        candidates = []
        state["error"] = f"Sourcing failed: {exc}"

    state["candidates"] = candidates
    state.setdefault("stage_log", []).append("source")
    return state

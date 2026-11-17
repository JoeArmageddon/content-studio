"""
Metadata Agent — Milestone 6 (Milestone 8: reads via the shared insights module).

Caption/hashtag generation is trend/competitor-driven, not LLM-only: reads
recent findings for this channel (via app.services.insights — both
Competitor-Scan's market data and, since Milestone 8, the Feedback Agent's
own-channel performance data) and feeds them into the LLM call that writes
the title/description/tags. If no recent competitor scan exists (or it's
gone stale), triggers one synchronously first — see
competitor_scan_agent.py's docstring for why it's invoked lazily here
rather than on its own schedule for this particular purpose.
"""
import json

from app.agents import competitor_scan_agent
from app.graph.state import PipelineState
from app.services import insights, llm_clients

_SYSTEM = (
    "You write YouTube metadata for a short-form narrated video retelling a "
    "real story. Rules:\n"
    "- Title: under 100 characters, punchy, curiosity-driven, matching this "
    "niche's conventions.\n"
    "- Description: 2-3 sentences, then a line of relevant hashtags.\n"
    "- If given examples of what's currently working for other creators or "
    "on this channel, let that inform your style and hashtag choices — but "
    "never copy a title or hashtag verbatim.\n"
    'Output strict JSON only: {"title": "...", "description": "...", "tags": ["...", ...]}'
)


def run(state: PipelineState) -> PipelineState:
    story = state.get("story") or {}
    channel = state.get("channel", {})
    channel_id = channel.get("id")
    title_fallback = story.get("title") or "Untitled"

    if not insights.get_recent(channel_id, source="competitor_scan", limit=1):
        competitor_scan_agent.run(channel)  # persists a fresh Insight row, if it succeeds

    insight_context = insights.summarize_for_prompt(channel_id)

    prompt = (
        f"Channel niche: {channel.get('niche', 'general')}\n"
        f"Story title: {story.get('title', '')}\n"
        f"Hook: {state.get('hook', '')}\n"
        f"{insight_context}\n\n"
        "Write the metadata."
    )

    try:
        raw = llm_clients.generate(prompt, system=_SYSTEM, max_tokens=300)
        parsed = json.loads(raw)
        state["metadata"] = {
            "title": (parsed.get("title") or title_fallback)[:100],
            "description": parsed.get("description", ""),
            "tags": parsed.get("tags", []),
        }
    except Exception as exc:  # noqa: BLE001 — metadata failure shouldn't crash the run
        state["metadata"] = {"title": title_fallback, "description": "", "tags": []}
        state["error"] = f"Metadata generation failed: {exc}"

    credit = state.get("background_credit")
    if credit:
        meta = state["metadata"]
        meta["description"] = f"{meta.get('description', '').rstrip()}\n\n{credit}"[:4900]

    state.setdefault("stage_log", []).append("metadata")
    return state

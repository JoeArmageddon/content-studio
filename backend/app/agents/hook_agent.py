"""
Hook Agent — Milestone 3 (Milestone 8: factors in what's working).

Focused LLM call that writes ONLY the first 3-5 seconds of narration — kept
separate from the full Scriptwriter agent since hook quality is the single
biggest retention lever and deserves its own prompt/iteration. Free-tier
LLM via app.services.llm_clients (Groq primary, Gemini fallback). Prompt
includes a short "what's working" note (own-channel + competitor findings,
via app.services.insights) when recent data exists, so hook style isn't
static over time.
"""
from app.graph.state import PipelineState
from app.services import insights, llm_clients
from app.services.content_filter import NO_DASH_RULE

_SYSTEM = (
    "You write ONLY the opening hook line for a short-form narrated video "
    "retelling a real Reddit-style story. The hook is the first 3-5 seconds "
    "of narration — its only job is to make someone stop scrolling. Rules: "
    "one or two short sentences, no more than 20 words total. Create "
    "curiosity or tension WITHOUT giving away the ending or the moral of the "
    "story. Speak in first person, as the story's narrator, in a natural "
    "spoken tone (not written/formal). Never write slurs (say 'a slur' if needed). " + NO_DASH_RULE + " Output ONLY the hook itself — no "
    "quotation marks, no hashtags, no explanation, no labels like 'Hook:'."
)


def run(state: PipelineState) -> PipelineState:
    story = state.get("story") or {}
    channel = state.get("channel", {})

    if not story.get("title") and not story.get("content"):
        state["hook"] = None
        state.setdefault("stage_log", []).append("hook_skipped_no_story")
        return state

    insight_context = insights.summarize_for_prompt(channel.get("id"))
    prompt = (
        f"Channel niche: {channel.get('niche', 'general storytelling')}\n"
        f"Story title: {story.get('title', '')}\n"
        f"Story excerpt: {story.get('content', '')[:800]}\n"
        f"{insight_context}\n\n"
        "Write the hook line."
    )

    try:
        state["hook"] = llm_clients.generate(prompt, system=_SYSTEM, max_tokens=60, temperature=1.0)
    except Exception as exc:  # noqa: BLE001 — hook failure shouldn't crash the run
        state["hook"] = None
        state["error"] = f"Hook generation failed: {exc}"

    state.setdefault("stage_log", []).append("hook")
    return state

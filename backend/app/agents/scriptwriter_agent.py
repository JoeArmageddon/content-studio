"""
Scriptwriter Agent — Milestone 3 (Milestone 8: factors in what's working).

Expands the hook + curated story into a full narration script, with
per-niche tone guidance (_TONE_HINTS below) instead of one generic prompt
for every channel — this is the concrete fix for StoriqueOS's "scripts are
weird" complaint. Free-tier LLM via app.services.llm_clients. Prompt
includes a short "what's working" note (own-channel + competitor findings,
via app.services.insights) when recent data exists.
"""
from app.graph.state import PipelineState
from app.services import insights, llm_clients

_TONE_HINTS = {
    "cheats": "Tone: betrayed, raw, seeking validation. Build tension around the moment of discovery.",
    "tifu": "Tone: self-deprecating and comedic. Escalate the consequences for comedic effect.",
    "horror": "Tone: eerie and suspenseful. Use short, tense sentences building toward a scary reveal.",
    "family": "Tone: exasperated and dramatic, framing it as you against toxic family members.",
    "confessions": "Tone: hushed and intimate, like admitting something in secret.",
    "aita": (
        "Tone: matter-of-fact but a little defensive, presenting your side fairly. "
        "End the script by directly asking the audience for judgment (e.g. 'So, AITA?')."
    ),
    "reallife_survival": "Tone: tense and high-stakes, moment-by-moment describing danger and the fight through it.",
    "workplace": "Tone: frustrated, satisfying when justice lands, relatable to anyone with a bad boss.",
    "askreddit": "Tone: conversational, like sharing a wild story a friend told you.",
    "rich_v_poor": "Tone: reflective and class-conscious, drawing a clear contrast between two different worlds.",
}

_SYSTEM_TEMPLATE = (
    "You are a scriptwriter for a narrated short-form video channel that "
    "retells real Reddit-style stories in first person. Write natural, "
    "SPOKEN-language narration — not a written essay. Rules:\n"
    "- Start the script with the exact hook line given, then continue the "
    "story in the narrator's voice.\n"
    "- Short, punchy sentences — the way someone actually narrates a video "
    "out loud, not the way someone writes an article.\n"
    "- {tone_hint}\n"
    "- Target roughly {word_target} words total (a ~{duration}s video at "
    "natural speaking pace).\n"
    "- Output ONLY the narration script, nothing else — no scene directions, "
    "no titles, no hashtags, no labels."
)

_DEFAULT_TONE_HINT = "Tone: engaging and true to the story's real emotional stakes."
_WORD_TARGET = 150
_DURATION_SECONDS = 60


def run(state: PipelineState) -> PipelineState:
    hook = state.get("hook")
    story = state.get("story") or {}
    channel = state.get("channel", {})

    if not hook or not story.get("content"):
        state["script"] = None
        state.setdefault("stage_log", []).append("script_skipped_no_input")
        return state

    tone_hint = _TONE_HINTS.get(channel.get("key"), _DEFAULT_TONE_HINT)
    system = _SYSTEM_TEMPLATE.format(
        tone_hint=tone_hint, word_target=_WORD_TARGET, duration=_DURATION_SECONDS
    )
    insight_context = insights.summarize_for_prompt(channel.get("id"))
    prompt = (
        f"Hook (start the script with this exact line): {hook}\n\n"
        f"Full story to retell:\n{story.get('content', '')[:3000]}\n"
        f"{insight_context}\n\n"
        "Write the full narration script."
    )

    try:
        state["script"] = llm_clients.generate(prompt, system=system, max_tokens=600, temperature=0.85)
    except Exception as exc:  # noqa: BLE001 — script failure shouldn't crash the run
        state["script"] = None
        state["error"] = f"Script generation failed: {exc}"

    state.setdefault("stage_log", []).append("script")
    return state

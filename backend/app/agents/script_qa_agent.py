"""
Script QA Agent — Milestone 3 (rules-based pass).

Checks pacing/length fit against the target video duration and flags
policy-risk phrasing before the script reaches the Voice Agent. Kept
rules-based (no extra LLM call) — deterministic, free, and fast; the
architecture doc explicitly allows a rules pass here instead of a second
LLM call. Extend _BANNED_PHRASES before any real/production use.
"""
from app.graph.state import PipelineState

# Placeholder starter list — extend with real slurs/policy-risk phrases
# before production use. Kept short and clearly non-exhaustive on purpose.
_BANNED_PHRASES = [
    "kill yourself",
]

_MIN_WORDS = 80
_MAX_WORDS = 220


def run(state: PipelineState) -> PipelineState:
    script = state.get("script") or ""
    notes: list[str] = []

    if not script:
        notes.append("Script is empty — upstream hook/script generation likely failed or was skipped.")
    else:
        word_count = len(script.split())
        if word_count < _MIN_WORDS:
            notes.append(f"Script is short ({word_count} words) — may run under target video length.")
        elif word_count > _MAX_WORDS:
            notes.append(f"Script is long ({word_count} words) — may run over target video length.")

        lowered = script.lower()
        for phrase in _BANNED_PHRASES:
            if phrase in lowered:
                notes.append(f"Policy-risk phrase detected: '{phrase}'")

    state["qa_notes"] = notes
    state.setdefault("stage_log", []).append("script_qa")
    return state

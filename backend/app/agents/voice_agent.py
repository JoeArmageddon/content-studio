"""
Voice Agent — Milestone 4.

Free-tier first: Kokoro (app.services.tts_client) — a local model, not a
metered API, so it's free forever, not just free-tier. Picks a random voice
from the channel's `voices` pool each run (rotating voices, not one fixed
narrator per channel) for cross-video variety; the chosen voice is recorded
in state["voice_used"] so it ends up on the Video row for later analysis
(e.g. the Feedback Agent correlating voice choice with performance).
"""
import random

from app.core.config import DATA_DIR
from app.graph.state import PipelineState
from app.services import tts_client

_FALLBACK_VOICES = ["af_jessica"]  # used only if a channel has no `voices` configured


def run(state: PipelineState) -> PipelineState:
    script = state.get("script")
    channel = state.get("channel", {})

    if not script:
        state["voice_path"] = None
        state["voice_used"] = None
        state.setdefault("stage_log", []).append("voice_skipped_no_script")
        return state

    voice = random.choice(channel.get("voices") or _FALLBACK_VOICES)
    key = channel.get("key", "unknown")
    run_id = state.get("run_id", "x")
    out_path = str(DATA_DIR / "exports" / "voice" / f"{key}_{run_id}.mp3")

    try:
        state["voice_path"] = tts_client.synthesize(script, voice, out_path)
        state["voice_used"] = voice
    except Exception as exc:  # noqa: BLE001 — voice failure shouldn't crash the run
        state["voice_path"] = None
        state["voice_used"] = None
        state["error"] = f"Voice synthesis failed: {exc}"

    state.setdefault("stage_log", []).append("voice")
    return state

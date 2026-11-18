"""
TTS client — Milestone 4 (revised: Kokoro, not Edge-TTS).

Edge-TTS's output was verified (by the user, listening directly) to still
sound robotic even with per-sentence pacing/pitch jitter and punctuation
timed pauses — the underlying voice model itself was the ceiling, not the
prosody engineering around it. Kokoro (82M params, Apache 2.0, CPU-fast,
#1 on the TTS Arena leaderboard as of writing) replaces it as the default
engine, confirmed by ear to be a real improvement. Free forever — it's a
local model, not a metered API, so it doesn't complicate the free-tier-first
budget the way a paid provider would.

Setup: two model files must exist locally (see README's Kokoro setup
section) — they're a one-time ~330MB download, not committed to git.
synthesize() raises a clear, actionable error if they're missing rather
than silently degrading to a worse engine.

Kokoro's own create() already does sentence/clause-level pause timing
internally (sentence_pause/clause_pause params) — the elaborate manual
sentence-split + concat + jitter pipeline built for Edge-TTS is gone;
turned out to be unnecessary now that the base model is actually
expressive. A light per-call speed jitter is kept for cross-video variety
(pairs with the rotating-voice-pool feature — see agents/voice_agent.py).

Concurrency (added Milestone 7, when scheduling 10 channels surfaced this):
the module-level Kokoro instance is loaded once behind a lock so two
scheduler worker threads can't double-load the ~350MB model. Concurrent
create() calls *on* that shared instance from multiple threads are not
independently verified beyond that — onnxruntime inference is generally
thread-safe, but this hasn't been stress-tested here.
"""
import os
import random
from typing import Optional

import threading

import soundfile as sf

from app.core.config import settings

_kokoro_instance = None
_kokoro_lock = threading.Lock()  # scheduler runs channel jobs on worker threads —
                                  # avoid two threads double-loading the ~350MB model


def _get_kokoro():
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance

    with _kokoro_lock:
        if _kokoro_instance is not None:  # re-check: another thread may have loaded it while we waited
            return _kokoro_instance

        if not os.path.exists(settings.kokoro_model_path) or not os.path.exists(settings.kokoro_voices_path):
            raise RuntimeError(
                "Kokoro model files not found at "
                f"{settings.kokoro_model_path} / {settings.kokoro_voices_path}. "
                "Download them once — see README's Kokoro setup section."
            )
        from kokoro_onnx import Kokoro  # imported lazily — only needed when actually synthesizing

        _kokoro_instance = Kokoro(
            model_path=settings.kokoro_model_path,
            voices_path=settings.kokoro_voices_path,
        )
    return _kokoro_instance


def list_voices() -> list[str]:
    return sorted(_get_kokoro().get_voices())


def _jitter_speed() -> float:
    # ~1.1x: the brisk, bright pacing short-form viewers are used to (CapCut-style narration)
    return round(random.uniform(1.08, 1.14), 3)


def synthesize(text: str, voice: str, out_path: str, speed: Optional[float] = None) -> str:
    if not text or not text.strip():
        raise ValueError("synthesize() called with empty/whitespace-only text")

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    kokoro = _get_kokoro()
    samples, sample_rate = kokoro.create(
        text,
        voice=voice,
        speed=speed if speed is not None else _jitter_speed(),
        lang="en-us",
    )
    sf.write(out_path, samples, sample_rate)
    return out_path

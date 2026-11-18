"""
Word-level timing for the narration, used by the rolling (karaoke-style)
subtitles and to time the story card to the real spoken hook.

faster-whisper transcribes the synthesized audio and gives per-word
timestamps; those are then matched back to the *script's own words* (via
difflib) so the captions always show the script text exactly, even where
Whisper hears something slightly different ("89-year-old" -> "89 year old").
Words Whisper missed get interpolated timings between their neighbours.

If Whisper isn't installed / fails, falls back to timings proportional to
word length across the audio — captions still roll, just less precisely.
"""
import difflib
import re
from typing import Any

_MODEL = None


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def _whisper_words(audio_path: str) -> list[dict[str, Any]]:
    global _MODEL
    from faster_whisper import WhisperModel  # lazy — heavy import

    if _MODEL is None:
        _MODEL = WhisperModel("base.en", device="cpu", compute_type="int8")
    segments, _ = _MODEL.transcribe(audio_path, word_timestamps=True, language="en", vad_filter=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            if _norm(w.word):
                words.append({"word": w.word.strip(), "start": float(w.start), "end": float(w.end)})
    return words


def _spread(tokens: list[str], start: float, end: float) -> list[tuple[float, float]]:
    """Splits [start, end] across tokens, weighted by character length."""
    end = max(end, start + 0.05 * len(tokens))
    weights = [max(len(_norm(t)), 1) for t in tokens]
    total = sum(weights)
    out, cursor = [], start
    for wgt in weights:
        dur = (end - start) * wgt / total
        out.append((cursor, cursor + dur))
        cursor += dur
    return out


def _proportional(tokens: list[str], total_duration: float) -> list[dict[str, Any]]:
    spans = _spread(tokens, 0.0, total_duration)
    return [{"word": t, "start": s, "end": e} for t, (s, e) in zip(tokens, spans)]


def align_words(audio_path: str, script: str, total_duration: float) -> list[dict[str, Any]]:
    """Returns [{word, start, end}] — one entry per whitespace-separated script token."""
    tokens = script.split()
    if not tokens:
        return []

    try:
        heard = _whisper_words(audio_path)
    except Exception as exc:  # noqa: BLE001 — degrade to proportional timing
        print(f"WARNING: word alignment unavailable ({exc}); using proportional timing")
        return _proportional(tokens, total_duration)
    if not heard:
        return _proportional(tokens, total_duration)

    a = [_norm(t) for t in tokens]
    b = [_norm(h["word"]) for h in heard]
    timings: list[tuple[float, float] | None] = [None] * len(tokens)

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                timings[i1 + k] = (heard[j1 + k]["start"], heard[j1 + k]["end"])
        elif tag == "replace":
            for k, span in enumerate(_spread(tokens[i1:i2], heard[j1]["start"], heard[j2 - 1]["end"])):
                timings[i1 + k] = span
        # "insert" (script words Whisper missed) handled below; "delete" (extra heard words) ignored.

    # Interpolate any still-missing tokens between the nearest timed neighbours.
    i = 0
    while i < len(tokens):
        if timings[i] is not None:
            i += 1
            continue
        j = i
        while j < len(tokens) and timings[j] is None:
            j += 1
        prev_end = timings[i - 1][1] if i > 0 else 0.0
        next_start = timings[j][0] if j < len(tokens) else max(total_duration, prev_end + 0.3 * (j - i))
        for k, span in enumerate(_spread(tokens[i:j], prev_end, max(next_start, prev_end + 0.05 * (j - i)))):
            timings[i + k] = span
        i = j

    # Enforce monotonic, non-overlapping timings.
    result, cursor = [], 0.0
    for tok, (s, e) in zip(tokens, timings):  # type: ignore[misc]
        s = max(s, cursor)
        e = max(e, s + 0.04)
        result.append({"word": tok, "start": s, "end": e})
        cursor = s  # allow tiny overlap of end into next start; next start never goes backwards
    return result

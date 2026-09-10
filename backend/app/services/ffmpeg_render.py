"""
Video assembly — Milestone 5 (deterministic step, not an LLM agent).

Composites: background footage (looped/cropped to vertical 1080x1920,
trimmed to the voice's duration) + voice audio + the story-card overlay
(shown only for an estimated hook duration) + burned-in sentence-level
subtitles. Uses ffmpeg (bundled via imageio-ffmpeg, confirmed built with
libass/libx264/aac — no system ffmpeg install needed).

Two known approximations, both because there's no word-level forced
alignment step in this pipeline yet (would need something like
faster-whisper — a real future improvement, not implemented here):
  - Hook-overlay duration is estimated proportionally from the hook's word
    count vs. the full script's word count, clamped to a sane [2, 6]s
    range — not the hook's *actual* spoken duration.
  - Subtitle cue timings are similarly proportional-to-word-count
    estimates per sentence, not real per-word timestamps. Good enough for
    "captions roughly track speech," not frame-accurate.
"""
import os
import re
import subprocess
from typing import Optional

import imageio_ffmpeg

from app.core.config import DATA_DIR
from app.graph.state import PipelineState

_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
_FONTS_DIR = __file__.rsplit("/services/", 1)[0] + "/assets/fonts"
_TARGET_SIZE = (1080, 1920)


def _probe_duration(path: str) -> float:
    result = subprocess.run([_FFMPEG, "-i", path], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        raise RuntimeError(f"Could not determine duration of {path}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def _estimate_hook_duration(hook: str, script: str, total_duration: float) -> float:
    hook_words = len((hook or "").split())
    script_words = max(len((script or "").split()), 1)
    fraction = hook_words / script_words
    return min(max(fraction * total_duration, 2.0), 6.0)


def _split_sentences(text: str) -> list[str]:
    parts = re.findall(r"[^.!?]+[.!?]*", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _ass_timestamp(seconds: float) -> str:
    cs = int(round(seconds * 100))  # ASS uses centiseconds
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


_ASS_HEADER_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Inter,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{outline},0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _build_ass(script: str, total_duration: float, out_path: str) -> str:
    """Builds an .ass subtitle file with an explicit PlayResX/PlayResY
    matching our actual output frame — avoids relying on libass's SRT-to-ASS
    auto-conversion, which otherwise guesses a small default script
    resolution and dramatically over-scales the rendered text (this was a
    real bug caught by actually looking at rendered frames, not just
    running the command and assuming success)."""
    sentences = _split_sentences(script)
    if not sentences:
        sentences = [script.strip()] if script.strip() else ["..."]

    word_counts = [max(len(s.split()), 1) for s in sentences]
    total_words = sum(word_counts)

    header = _ASS_HEADER_TEMPLATE.format(
        width=_TARGET_SIZE[0], height=_TARGET_SIZE[1],
        font_size=56, outline=4, margin_v=220,
    )
    events = []
    cursor = 0.0
    for sentence, words in zip(sentences, word_counts):
        duration = (words / total_words) * total_duration
        start, end = cursor, min(cursor + duration, total_duration)
        text = sentence.replace("\n", " ")
        events.append(
            f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},Default,,0,0,0,,{text}"
        )
        cursor = end

    with open(out_path, "w") as f:
        f.write(header + "\n".join(events) + "\n")
    return out_path


def _escape_for_filter(path: str) -> str:
    # ffmpeg filter arguments treat ':' and '\' specially — escape for use
    # inside a filter_complex string (Windows paths aren't a concern here,
    # but colons in the path in general need this).
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def assemble_video(state: PipelineState) -> Optional[str]:
    channel = state.get("channel", {})
    key = channel.get("key", "unknown")
    run_id = state.get("run_id", "x")

    voice_path = state.get("voice_path")
    background_clip = state.get("background_clip")
    story_card_path = state.get("story_card_path")
    script = state.get("script") or ""
    hook = state.get("hook") or ""

    if not voice_path or not background_clip:
        # Can't assemble without at least narration + background — leave it
        # to the caller to notice video_path is None, same degrade pattern
        # every other agent uses.
        return None

    out_dir = DATA_DIR / "exports" / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / f"{key}_{run_id}.mp4")
    ass_path = str(out_dir / f"{key}_{run_id}.ass")

    voice_duration = _probe_duration(voice_path)
    hook_duration = _estimate_hook_duration(hook, script, voice_duration)
    _build_ass(script, voice_duration, ass_path)

    scale_crop = f"scale={_TARGET_SIZE[0]}:{_TARGET_SIZE[1]}:force_original_aspect_ratio=increase,crop={_TARGET_SIZE[0]}:{_TARGET_SIZE[1]}"

    filter_parts = [f"[0:v]{scale_crop}[bg]"]
    video_label = "bg"

    if story_card_path and os.path.exists(story_card_path):
        filter_parts.append(
            f"[bg][2:v]overlay=0:0:enable='between(t,0,{hook_duration:.2f})'[withcard]"
        )
        video_label = "withcard"

    filter_parts.append(
        f"[{video_label}]ass={_escape_for_filter(ass_path)}:"
        f"fontsdir={_escape_for_filter(_FONTS_DIR)}[outv]"
    )

    cmd = [
        _FFMPEG, "-y",
        "-stream_loop", "-1", "-i", background_clip,
        "-i", voice_path,
    ]
    if story_card_path and os.path.exists(story_card_path):
        cmd += ["-i", story_card_path]

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]",
        "-map", "1:a",
        "-t", f"{voice_duration:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        out_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg assembly failed: {result.stderr[-2000:]}")

    return out_path

"""
Video assembly — deterministic step (not an LLM agent).

Composites: background footage (pre-cropped 1080x1920 library clip, looped
and trimmed to the voice's duration) + voice audio + the story-card overlay
(shown for the real spoken duration of the hook, with a short fade) +
rolling "karaoke" captions: 1-3 words at a time, centered, big white text
with a heavy black outline, the word being spoken highlighted yellow.

Word timings come from app.services.word_align (faster-whisper timestamps
matched back to the script's own words), so the captions follow the actual
speech rather than the word-count estimate the first version used.

Uses ffmpeg bundled via imageio-ffmpeg (libass + libx264 + aac confirmed).
"""
import os
import re
import subprocess
from typing import Optional

import imageio_ffmpeg

from app.core.config import DATA_DIR
from app.graph.state import PipelineState
from app.services.word_align import align_words

_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
_FONTS_DIR = __file__.rsplit("/services/", 1)[0] + "/assets/fonts"
_TARGET_SIZE = (1080, 1920)

_CAPTION_FONT = "Poppins ExtraBold"
_CAPTION_SIZE = 96
_CAPTION_MAX_WORDS = 3
_CAPTION_MAX_CHARS = 16
_CAPTION_Y = 985  # px from top (frame centre is 960) — matches the reference short
_YELLOW = "&H000AD6FF&"  # ASS is BGR: #FFD60A
_WHITE = "&H00FFFFFF&"


def _probe_duration(path: str) -> float:
    result = subprocess.run([_FFMPEG, "-i", path], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        raise RuntimeError(f"Could not determine duration of {path}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def _ass_timestamp(seconds: float) -> str:
    cs = int(round(max(seconds, 0.0) * 100))  # ASS uses centiseconds
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


_ASS_HEADER_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,8,4,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _chunk_words(words: list[dict]) -> list[list[dict]]:
    """Groups words into short on-screen phrases: <=3 words, <=17 chars, and
    always break after sentence/clause punctuation so phrases read naturally."""
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        candidate = " ".join(x["word"] for x in cur + [w])
        if cur and (len(cur) >= _CAPTION_MAX_WORDS or len(candidate) > _CAPTION_MAX_CHARS):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.,!?;:…][\"')\]]*$", w["word"]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def _clean(word: str) -> str:
    return word.replace("{", "").replace("}", "").replace("\\", "")


def _build_ass(words: list[dict], total_duration: float, out_path: str) -> str:
    header = _ASS_HEADER_TEMPLATE.format(
        width=_TARGET_SIZE[0], height=_TARGET_SIZE[1], font=_CAPTION_FONT, size=_CAPTION_SIZE
    )
    pos = f"{{\\an5\\pos({_TARGET_SIZE[0] // 2},{_CAPTION_Y})}}"
    events: list[str] = []
    chunks = _chunk_words(words)

    for ci, chunk in enumerate(chunks):
        next_chunk_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total_duration
        for wi, w in enumerate(chunk):
            start = w["start"]
            if wi + 1 < len(chunk):
                end = chunk[wi + 1]["start"]
            else:
                gap = next_chunk_start - w["end"]
                end = next_chunk_start if gap < 0.35 else w["end"] + 0.2
            end = min(max(end, start + 0.05), total_duration)
            if start >= total_duration:
                continue
            parts = []
            for k, cw in enumerate(chunk):
                txt = _clean(cw["word"])
                parts.append(f"{{\\1c{_YELLOW}}}{txt}{{\\1c{_WHITE}}}" if k == wi else txt)
            # quick pop on the first word of each phrase
            pop = "{\\fscx90\\fscy90\\t(0,110,\\fscx100\\fscy100)}" if wi == 0 else ""
            events.append(
                f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},Default,,0,0,0,,{pos}{pop}{' '.join(parts)}"
            )

    with open(out_path, "w") as f:
        f.write(header + "\n".join(events) + "\n")
    return out_path


def _hook_end(words: list[dict], hook: str, total_duration: float) -> float:
    """Real end-time of the spoken hook (the script opens with it), + a beat."""
    n = len((hook or "").split())
    if words and n:
        t = words[min(n, len(words)) - 1]["end"] + 0.5
    else:
        t = 4.0
    return min(max(t, 2.5), min(9.0, total_duration))


def _escape_for_filter(path: str) -> str:
    # ffmpeg filter arguments treat ':' and '\' specially.
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
    words = align_words(voice_path, script, voice_duration)
    _build_ass(words, voice_duration, ass_path)
    hook_end = _hook_end(words, hook, voice_duration)

    w, h = _TARGET_SIZE
    # Library clips are already 1080x1920; this also handles any other-shaped fallback clip.
    filter_parts = [
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps=30,setsar=1[bg]"
    ]
    video_label = "bg"

    has_card = bool(story_card_path and os.path.exists(story_card_path))
    if has_card:
        filter_parts.append(
            f"[2:v]format=rgba,fade=t=in:st=0:d=0.2:alpha=1,"
            f"fade=t=out:st={max(hook_end - 0.25, 0.3):.2f}:d=0.25:alpha=1[card]"
        )
        filter_parts.append("[bg][card]overlay=0:0:eof_action=pass[withcard]")
        video_label = "withcard"

    filter_parts.append(
        f"[{video_label}]ass={_escape_for_filter(ass_path)}:"
        f"fontsdir={_escape_for_filter(_FONTS_DIR)}[outv]"
    )
    # Light "produced voice" chain: trim rumble, even out loudness, normalise to -16 LUFS.
    filter_parts.append(
        "[1:a]highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[outa]"
    )

    cmd = [
        _FFMPEG, "-y",
        "-stream_loop", "-1", "-i", background_clip,
        "-i", voice_path,
    ]
    if has_card:
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{hook_end:.2f}", "-i", story_card_path]

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]",
        "-map", "[outa]",
        "-t", f"{voice_duration:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        "-movflags", "+faststart",
        out_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg assembly failed: {result.stderr[-2000:]}")

    return out_path

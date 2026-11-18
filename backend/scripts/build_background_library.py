"""
Build the background-footage library from YouTube Creative-Commons videos.

WHY THIS RUNS ON YOUR MACHINE, NOT IN GITHUB ACTIONS: YouTube blocks
yt-dlp downloads from datacenter IPs ("Sign in to confirm you're not a
bot"). A normal home connection works. So clips are downloaded + cropped +
compressed here once, then published as a GitHub Release
(scripts/publish_background_library.py) which the pipeline workflow
downloads at the start of each run.

QUALITY: every clip is stored as a finished 1080x1920 (9:16) H.264 file, so
the pipeline never has to upscale. To keep that sharp, sources are chosen by
their real resolution:
  - vertical sources (Shorts etc.) need >= 800px wide,
  - landscape sources are center-cropped to 9:16, so they need >= 1440p
    (the crop is ~810px wide; 4K is better still).
Anything lower is skipped — better fewer clips than blurry ones. Only the
~45s segment is downloaded (yt-dlp download_ranges), not the whole video.

Usage (from backend/):
    python scripts/build_background_library.py                    # all channels
    python scripts/build_background_library.py --channel aita     # one channel
    python scripts/build_background_library.py --channel aita --rebuild   # wipe + redo (e.g. after a quality change)

Manifest entries keep the attribution (CC BY requires crediting the
uploader) — the metadata agent appends it to the video description.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import app.*` works

import imageio_ffmpeg  # noqa: E402
import yaml  # noqa: E402

from app.core.config import BACKEND_DIR, DATA_DIR  # noqa: E402
from app.services import stock_video_clients as svc  # noqa: E402

CLIP_SECONDS = 45
MIN_SOURCE_SECONDS = 20
MAX_SOURCE_SECONDS = 3 * 3600
MIN_CROP_WIDTH = 800  # px of the final 9:16 crop before it's scaled to 1080 wide
CANDIDATES_PER_SEARCH = 25
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _pick_format(info: dict) -> dict | None:
    """Best video-only format whose 9:16 crop is >= MIN_CROP_WIDTH wide."""
    best = None
    for f in info.get("formats", []):
        w, h = f.get("width"), f.get("height")
        if not w or not h or f.get("vcodec") in (None, "none"):
            continue
        crop_w = w if w < h else h * 9 / 16
        if crop_w < MIN_CROP_WIDTH:
            continue
        # Prefer the highest crop width; among equals prefer smaller files (lower bitrate codecs download faster).
        score = (crop_w, -(f.get("tbr") or 0))
        if best is None or score > best[0]:
            best = (score, f)
    return best[1] if best else None


def _download_segment(url: str, out_prefix: Path) -> tuple[Path, dict]:
    """Downloads just the CLIP_SECONDS segment in the best acceptable format."""
    import yt_dlp
    from yt_dlp.utils import download_range_func

    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "js_runtimes": {"node": {}},  # YouTube extraction needs a JS runtime; node is what's installed
        "remote_components": ["ejs:github"],
        "ffmpeg_location": FFMPEG,
    }
    # If YouTube starts demanding sign-in ("confirm you're not a bot") from this IP, set
    # YT_COOKIES_BROWSER=chrome to reuse that browser's logged-in session.
    # Or export a cookies.txt to data/youtube_cookies.txt (gitignored) and it's picked up automatically.
    cookie_file = DATA_DIR / "youtube_cookies.txt"
    if cookie_file.exists():
        base_opts["cookiefile"] = str(cookie_file)
    elif os.environ.get("YT_COOKIES_BROWSER"):
        base_opts["cookiesfrombrowser"] = (os.environ["YT_COOKIES_BROWSER"],)
    with yt_dlp.YoutubeDL({**base_opts, "format": "bv*"}) as ydl:
        info = ydl.extract_info(url, download=False)
    duration = float(info.get("duration") or 0)
    if not (MIN_SOURCE_SECONDS <= duration <= MAX_SOURCE_SECONDS):
        raise ValueError(f"duration {duration:.0f}s outside usable range")
    fmt = _pick_format(info)
    if not fmt:
        top = max((f.get("height") or 0 for f in info.get("formats", [])), default=0)
        raise ValueError(f"resolution too low (best {top}p)")

    seg = min(CLIP_SECONDS, duration)
    start = 0.0 if duration <= CLIP_SECONDS + 10 else min(duration * 0.25, duration - CLIP_SECONDS - 5)
    opts = {
        **base_opts,
        "format": fmt["format_id"],
        "outtmpl": f"{out_prefix}.%(ext)s",
        "download_ranges": download_range_func(None, [(start, start + seg)]),
        "force_keyframes_at_cuts": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = [p for p in glob.glob(f"{out_prefix}.*") if not p.endswith(".part")]
    if not files:
        raise RuntimeError("download produced no file")
    return Path(files[0]), {"width": fmt.get("width"), "height": fmt.get("height")}


def _to_vertical_1080(raw: Path, out_path: Path) -> None:
    subprocess.run(
        [
            FFMPEG, "-y", "-i", str(raw), "-an", "-t", str(CLIP_SECONDS),
            "-vf", "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920:flags=lanczos,fps=30,setsar=1",
            "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out_path),
        ],
        check=True, capture_output=True,
    )


def build_for_channel(channel: dict, per_query: int) -> int:
    key = channel["key"]
    out_dir = DATA_DIR / "backgrounds" / key
    out_dir.mkdir(parents=True, exist_ok=True)
    have = {e.get("source_id") for e in svc.load_manifest(key)}
    tried: set[str] = set()
    added = 0

    for query in channel.get("background_queries", []):
        got = 0
        # "short" surfaces vertical Shorts (already 9:16); "medium" the longer landscape videos.
        for duration in ("short", "medium"):
            if got >= per_query:
                break
            try:
                candidates = svc.search_cc_youtube(query, max_results=CANDIDATES_PER_SEARCH, duration=duration)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{key}] search failed for '{query}' ({duration}): {exc}")
                continue
            for cand in candidates:
                if got >= per_query:
                    break
                sid = cand["source_id"]
                if sid in have or sid in tried:
                    continue
                tried.add(sid)
                name = f"youtube_cc_{sid}.mp4"
                prefix = out_dir / f"{sid}.raw"
                raw = None
                try:
                    print(f"  [{key}] '{query}' -> {cand['title'][:60]!r} ...", flush=True)
                    raw, dims = _download_segment(cand["url"], prefix)
                    _to_vertical_1080(raw, out_dir / name)
                except Exception as exc:  # noqa: BLE001 — skip this candidate, try the next
                    print(f"      skipped: {str(exc)[:140]}")
                    continue
                finally:
                    for p in glob.glob(f"{prefix}.*"):
                        Path(p).unlink(missing_ok=True)
                svc._append_manifest(
                    key,
                    {
                        "file": name,  # relative to data/backgrounds/<key>/ — resolved at use time
                        "source": "youtube_cc",
                        "source_id": sid,
                        "license": cand["license"],
                        "query": query,
                        "title": cand["title"],
                        "channel_title": cand["channel_title"],
                        "url": cand["url"],
                        "source_resolution": f"{dims['width']}x{dims['height']}",
                    },
                )
                have.add(sid)
                got += 1
                added += 1
                print(f"      ok {dims['width']}x{dims['height']} ({(out_dir / name).stat().st_size / 1e6:.1f} MB)")
    return added


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default=None)
    parser.add_argument("--per-query", type=int, default=3)
    parser.add_argument("--rebuild", action="store_true", help="delete the channel's existing clips first")
    args = parser.parse_args()

    cfg = yaml.safe_load(open(BACKEND_DIR / "app" / "config" / "channels.yaml"))["channels"]
    channels = [c for c in cfg if not args.channel or c["key"] == args.channel]
    if not channels:
        sys.exit(f"No channel '{args.channel}' in channels.yaml")

    total = 0
    for ch in channels:
        print(f"== {ch['key']} ==")
        if args.rebuild:
            shutil.rmtree(DATA_DIR / "backgrounds" / ch["key"], ignore_errors=True)
        total += build_for_channel(ch, args.per_query)
    print(f"Done: {total} new clips.")


if __name__ == "__main__":
    main()

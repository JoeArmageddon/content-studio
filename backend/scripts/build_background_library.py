"""
Build the background-footage library from YouTube Creative-Commons videos.

WHY THIS RUNS ON YOUR MACHINE, NOT IN GITHUB ACTIONS: YouTube blocks
yt-dlp downloads from datacenter IPs ("Sign in to confirm you're not a
bot" — seen on the first Actions run). A normal home connection works. So
clips are downloaded + trimmed + compressed here once, then published as a
GitHub Release (scripts/publish_background_library.py) which the pipeline
workflow downloads at the start of each run.

Usage (from backend/):
    python scripts/build_background_library.py                    # all channels, 3 clips per query
    python scripts/build_background_library.py --channel aita     # one channel
    python scripts/build_background_library.py --per-query 1 --channel aita   # quick test

Each clip: a ~45s segment taken from ~25% into the source (skips intros),
scaled to <=720px wide, audio removed (narration replaces it), H.264.
Manifest entries keep the attribution (CC BY requires crediting the
uploader) — the metadata agent appends it to the video description.
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import app.*` works

import imageio_ffmpeg  # noqa: E402
import yaml  # noqa: E402

from app.core.config import BACKEND_DIR, DATA_DIR  # noqa: E402
from app.services import stock_video_clients as svc  # noqa: E402

CLIP_SECONDS = 45
MIN_SOURCE_SECONDS = 90  # skip shorts / tiny clips — need room to take a segment from the middle
MAX_SOURCE_SECONDS = 3 * 3600


def _download_source(url: str, raw_path: Path) -> float:
    """Downloads the source (<=720p, video only) and returns its duration."""
    import yt_dlp

    opts = {
        "format": "bestvideo[height<=720][ext=mp4]/bestvideo[height<=720]/best[height<=720]",
        "outtmpl": str(raw_path),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "js_runtimes": {"node": {}},  # YouTube extraction needs a JS runtime; node is what's installed
        "remote_components": ["ejs:github"],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        duration = float(info.get("duration") or 0)
        if not (MIN_SOURCE_SECONDS <= duration <= MAX_SOURCE_SECONDS):
            raise ValueError(f"duration {duration:.0f}s outside usable range")
        ydl.download([url])
    return duration


def _trim_and_compress(raw_path: Path, out_path: Path, duration: float) -> None:
    start = max(0.0, min(duration * 0.25, duration - CLIP_SECONDS - 5))
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-ss", f"{start:.1f}", "-i", str(raw_path),
            "-t", str(CLIP_SECONDS), "-an",
            "-vf", "scale='min(720,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-movflags", "+faststart",
            str(out_path),
        ],
        check=True, capture_output=True,
    )


def build_for_channel(channel: dict, per_query: int) -> int:
    key = channel["key"]
    out_dir = DATA_DIR / "backgrounds" / key
    out_dir.mkdir(parents=True, exist_ok=True)
    have = {e.get("source_id") for e in svc.load_manifest(key)}
    added = 0

    for query in channel.get("background_queries", []):
        got = 0
        try:
            candidates = svc.search_cc_youtube(query, max_results=15)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{key}] search failed for '{query}': {exc}")
            continue
        for cand in candidates:
            if got >= per_query:
                break
            if cand["source_id"] in have:
                continue
            name = f"youtube_cc_{cand['source_id']}.mp4"
            raw = out_dir / f"{cand['source_id']}.raw.mp4"
            try:
                print(f"  [{key}] '{query}' -> {cand['title'][:60]!r} ...", flush=True)
                duration = _download_source(cand["url"], raw)
                _trim_and_compress(raw, out_dir / name, duration)
            except Exception as exc:  # noqa: BLE001 — skip this candidate, try the next
                print(f"      skipped: {str(exc)[:140]}")
                continue
            finally:
                raw.unlink(missing_ok=True)
            svc._append_manifest(
                key,
                {
                    "file": name,  # relative to data/backgrounds/<key>/ — resolved at use time
                    "source": "youtube_cc",
                    "source_id": cand["source_id"],
                    "license": cand["license"],
                    "query": query,
                    "title": cand["title"],
                    "channel_title": cand["channel_title"],
                    "url": cand["url"],
                },
            )
            have.add(cand["source_id"])
            got += 1
            added += 1
            print(f"      ok ({(out_dir / name).stat().st_size / 1e6:.1f} MB)")
    return added


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default=None)
    parser.add_argument("--per-query", type=int, default=3)
    args = parser.parse_args()

    cfg = yaml.safe_load(open(BACKEND_DIR / "app" / "config" / "channels.yaml"))["channels"]
    channels = [c for c in cfg if not args.channel or c["key"] == args.channel]
    if not channels:
        sys.exit(f"No channel '{args.channel}' in channels.yaml")

    total = 0
    for ch in channels:
        print(f"== {ch['key']} ==")
        total += build_for_channel(ch, args.per_query)
    print(f"Done: {total} new clips.")


if __name__ == "__main__":
    main()

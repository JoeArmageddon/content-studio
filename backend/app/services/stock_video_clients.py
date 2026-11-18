"""
Background-footage sourcing — Milestone 5.

Two sources, tried in order:
  (a) Pexels, then Pixabay — free stock-video APIs, unambiguous free
      license, direct downloadable URLs. Best for ASMR/cooking/nature-style
      backgrounds. Needs settings.pexels_api_key / pixabay_api_key (both
      free — https://www.pexels.com/api/ and https://pixabay.com/api/docs/).
  (b) YouTube Data API search filtered to videoLicense=creativeCommon, for
      gameplay-style footage (Minecraft/Subway-Surfers-style clips uploaded
      under CC), downloaded via yt-dlp. Needs settings.youtube_data_api_key.
      NOT verified live — no key was available while building this; the
      request shape is right but confirm it end-to-end once a key exists.

Every downloaded clip is cached under DATA_DIR/backgrounds/<channel_key>/
and logged in a manifest.json there (source, license, query, fetched_at)
for an audit trail — see cache_clip()/load_manifest().

Known limitation (noted Milestone 7, when scheduling 10 channels surfaced
concurrency concerns generally): _append_manifest()'s read-modify-write
isn't file-locked. Low practical risk — manifests are per-channel and a
single channel's own scheduled runs are spaced across the day — but two
runs for the *same* channel overlapping (e.g. a manual trigger landing
mid-scheduled-run) could race and drop a manifest entry. Worth real file
locking if that ever shows up in practice; not done here given the low
probability and low consequence (a missing audit-log line, not corruption).
"""
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from app.core.config import DATA_DIR, settings

_PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
_PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"
_YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _manifest_path(channel_key: str) -> str:
    return str(DATA_DIR / "backgrounds" / channel_key / "manifest.json")


def load_manifest(channel_key: str) -> list[dict[str, Any]]:
    path = _manifest_path(channel_key)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def resolve_clip_path(channel_key: str, file: str) -> str:
    """Manifest entries written by the library builder store a path relative
    to data/backgrounds/<channel_key>/ (so the same manifest works on your
    Mac and on a GitHub Actions runner); older entries are absolute."""
    if os.path.isabs(file):
        return file
    return str(DATA_DIR / "backgrounds" / channel_key / file)


def attribution_for(entry: dict[str, Any]) -> Optional[str]:
    """CC BY requires crediting the uploader — returned as a description line."""
    if entry.get("source") != "youtube_cc" or not entry.get("title"):
        return None
    return f'Background footage: "{entry["title"]}" by {entry.get("channel_title", "unknown")} (CC BY) {entry.get("url", "")}'.strip()


def _append_manifest(channel_key: str, entry: dict[str, Any]) -> None:
    path = _manifest_path(channel_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    manifest = load_manifest(channel_key)
    manifest.append(entry)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)


def _download(url: str, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    return out_path


def search_pexels(query: str, per_page: int = 5) -> list[dict[str, Any]]:
    if not settings.pexels_api_key:
        raise RuntimeError("PEXELS_API_KEY not set")

    resp = requests.get(
        _PEXELS_SEARCH_URL,
        headers={"Authorization": settings.pexels_api_key},
        params={"query": query, "per_page": per_page, "orientation": "portrait"},
        timeout=15,
    )
    resp.raise_for_status()
    results = []
    for video in resp.json().get("videos", []):
        # Prefer an HD-ish file, not the largest (4K) one, to keep downloads fast.
        files = sorted(video.get("video_files", []), key=lambda f: f.get("width") or 0)
        candidates = [f for f in files if (f.get("width") or 0) >= 720] or files
        if not candidates:
            continue
        results.append(
            {
                "source": "pexels",
                "license": "Pexels License (free for commercial/non-commercial use, no attribution required)",
                "url": candidates[0]["link"],
                "source_id": str(video["id"]),
                "query": query,
            }
        )
    return results


def search_pixabay(query: str, per_page: int = 5) -> list[dict[str, Any]]:
    if not settings.pixabay_api_key:
        raise RuntimeError("PIXABAY_API_KEY not set")

    resp = requests.get(
        _PIXABAY_SEARCH_URL,
        params={"key": settings.pixabay_api_key, "q": query, "per_page": per_page},
        timeout=15,
    )
    resp.raise_for_status()
    results = []
    for hit in resp.json().get("hits", []):
        videos = hit.get("videos", {})
        video_file = videos.get("medium") or videos.get("small") or videos.get("large")
        if not video_file:
            continue
        results.append(
            {
                "source": "pixabay",
                "license": "Pixabay License (free for commercial/non-commercial use, no attribution required)",
                "url": video_file["url"],
                "source_id": str(hit["id"]),
                "query": query,
            }
        )
    return results


def search_cc_youtube(query: str, max_results: int = 5, duration: str = "medium") -> list[dict[str, Any]]:
    """Metadata search only — see download_youtube_cc_clip() for the yt-dlp
    download step. NOT verified live (no API key available while building)."""
    if not settings.youtube_data_api_key:
        raise RuntimeError("YOUTUBE_DATA_API_KEY not set")

    resp = requests.get(
        _YOUTUBE_SEARCH_URL,
        params={
            "key": settings.youtube_data_api_key,
            "q": query,
            "part": "snippet",
            "type": "video",
            "videoLicense": "creativeCommon",
            "videoDuration": duration,  # "short" (<4 min, includes vertical Shorts) / "medium" / "long"
            "maxResults": max_results,
        },
        timeout=15,
    )
    resp.raise_for_status()
    results = []
    for item in resp.json().get("items", []):
        video_id = item["id"]["videoId"]
        results.append(
            {
                "source": "youtube_cc",
                "license": "YouTube Creative Commons (CC BY)",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "source_id": video_id,
                "query": query,
                "title": item["snippet"]["title"],
                "channel_title": item["snippet"]["channelTitle"],
            }
        )
    return results


def download_youtube_cc_clip(video_url: str, out_path: str, max_seconds: int = 60) -> str:
    """Downloads a CC-licensed YouTube video via yt-dlp and trims it to
    max_seconds. NOT verified live — implemented against yt-dlp's documented
    API but no YouTube Data API key was available to test the full search
    -> download path end-to-end while building this."""
    import yt_dlp  # imported lazily — only needed on this path

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    raw_path = out_path + ".raw.mp4"

    ydl_opts = {
        "format": "best[height<=1080][ext=mp4]/best[ext=mp4]/best",
        "outtmpl": raw_path,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    # Trim to max_seconds via ffmpeg (source clips are full-length videos;
    # we only want a short loopable segment).
    import imageio_ffmpeg
    import subprocess

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg, "-y", "-i", raw_path, "-t", str(max_seconds), "-c", "copy", out_path],
        check=True, capture_output=True,
    )
    os.remove(raw_path)
    return out_path


def fetch_and_cache_clip(channel_key: str, query: str) -> Optional[str]:
    """Tries Pexels, then Pixabay, then YouTube CC (in that order — see
    module docstring). Downloads the first hit, caches it, logs it in the
    manifest, and returns the local file path. Returns None if every source
    is either unconfigured or fails."""
    searches = [
        ("pexels", search_pexels),
        ("pixabay", search_pixabay),
        ("youtube_cc", search_cc_youtube),
    ]

    for source_name, search_fn in searches:
        try:
            candidates = search_fn(query)
        except Exception as exc:  # noqa: BLE001 — try the next source
            print(f"WARNING: {source_name} search failed for '{query}': {exc}")
            continue

        if not candidates:
            continue

        candidate = candidates[0]
        ext = "mp4"
        out_path = str(
            DATA_DIR / "backgrounds" / channel_key / f"{source_name}_{candidate['source_id']}.{ext}"
        )

        try:
            if source_name == "youtube_cc":
                download_youtube_cc_clip(candidate["url"], out_path)
            else:
                _download(candidate["url"], out_path)
        except Exception as exc:  # noqa: BLE001 — try the next source
            print(f"WARNING: {source_name} download failed for '{query}': {exc}")
            continue

        _append_manifest(
            channel_key,
            {
                "file": out_path,
                "source": candidate["source"],
                "license": candidate["license"],
                "query": query,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return out_path

    return None

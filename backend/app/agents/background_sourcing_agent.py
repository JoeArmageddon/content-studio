"""
Background-Sourcing Agent — Milestone 5.

Picks a background theme/query from the channel's `background_queries`
config, reuses a cached clip if enough are already on hand (avoids
re-downloading every run — see the cache-size threshold below), otherwise
fetches a new one via app.services.stock_video_clients (Pexels > Pixabay >
YouTube CC, in that order — see that module for the license/audit-trail
details). Degrades gracefully (background_clip stays None) if no source is
configured/reachable, same pattern as every other real agent so far.
"""
import random

from app.graph.state import PipelineState
from app.services import stock_video_clients

# Once a channel has this many cached clips, reuse the pool instead of
# fetching a new one every run — keeps API usage low and still gives
# plenty of visual variety across videos.
_CACHE_TARGET_SIZE = 6  # = what the library builder makes per channel (2 queries x 3 clips)


def run(state: PipelineState) -> PipelineState:
    channel = state.get("channel", {})
    key = channel.get("key", "unknown")
    queries = channel.get("background_queries") or [channel.get("niche", "background")]

    manifest = stock_video_clients.load_manifest(key)

    clip_path = None
    entry = None
    if len(manifest) >= _CACHE_TARGET_SIZE:
        entry = random.choice(manifest)
    else:
        query = random.choice(queries)
        try:
            clip_path = stock_video_clients.fetch_and_cache_clip(key, query)
        except Exception as exc:  # noqa: BLE001 — background failure shouldn't crash the run
            state["error"] = f"Background sourcing failed: {exc}"

        if not clip_path and manifest:
            # Fetch failed (e.g. no API keys configured, or YouTube blocking CI
            # IPs) but we have library clips — reuse one rather than leaving
            # the video without background footage.
            entry = random.choice(manifest)

    if entry:
        clip_path = stock_video_clients.resolve_clip_path(key, entry["file"])
        state["background_credit"] = stock_video_clients.attribution_for(entry)

    state["background_clip"] = clip_path
    state.setdefault("stage_log", []).append("background")
    return state

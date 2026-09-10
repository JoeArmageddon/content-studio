"""
Reddit sourcing client — Milestone 2 (revised after 2026 API research).

Reddit's landscape changed significantly through late 2025/2026 — see
docs/ARCHITECTURE.md's "Reddit sourcing strategy" note for the full
writeup. Short version:
  - Unauthenticated `.json` scraping is broadly restricted now (not just
    blocked for datacenter IPs, as first assumed in Milestone 2 — it's
    Reddit's general 2026 posture). Kept only as a last-resort fallback.
  - Self-service OAuth app registration (what PRAW traditionally used) is
    gated behind a manual, multi-week "Responsible Builder Policy" approval
    — even for the free non-commercial tier, which explicitly excludes
    commercial use anyway.
  - Reddit's `.rss` feeds (verified working, zero setup, no auth) survived
    both changes and are NOT part of the priced API surface. This is now
    the default free path.

Priority: PRAW (only if REDDIT_CLIENT_ID/SECRET are set — e.g. once Reddit
approves a Data API request) > RSS (default) > public JSON (last resort,
likely blocked). RSS has no upvote/comment counts, so ranking falls back to
the subreddit's own "hot" ordering (a position-based synthetic score)
rather than real engagement numbers — see _fetch_rss.

RSS rate limit — CORRECTED after Milestone 7 testing: earlier docs claimed
"~1 request per subreddit-feed per minute" based on third-party reporting.
Actually observed: a burst of ~24 requests across many *different*,
never-before-hit subreddits started 429ing almost immediately, and a fresh
subreddit still 429'd after a 20s gap while another succeeded — this
behaves like a global (likely per-IP) budget, not a clean per-feed one.
_fetch_rss now retries once after a real backoff on 429, and fetch_stories
paces itself between subreddits in the same call — both add real latency
to a multi-subreddit sourcing call (tens of seconds), which is a fine
trade for a free, zero-setup, unauthenticated source at our actual cadence
(a handful of runs/day/channel), but makes rapid manual testing slow —
that's inherent to the constraint, not a bug to fix further.
"""
import html
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional

import requests

from app.core.config import settings

_HEADERS = {"User-Agent": settings.reddit_user_agent}
_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
_RSS_RETRY_BACKOFF_SECONDS = 25
_RSS_INTER_SUBREDDIT_DELAY_SECONDS = 25

# Cheap filter for subreddit meta/mod posts that slip into "hot" — real
# story titles essentially never match these patterns.
_META_TITLE_RE = re.compile(
    r"\b(megathread|open forum|monthly thread|weekly thread|quarterly|"
    r"rules refresh|mod(?:erator)? post|announcement)\b",
    re.IGNORECASE,
)


def _clean_rss_content(raw_html: str) -> str:
    """Strips Reddit's RSS content down to just the post body text (drops
    the '<!-- SC_ON --> submitted by ... [link] [comments]' footer Reddit
    appends to every entry, and any remaining HTML markup)."""
    text = raw_html.split("<!-- SC_ON -->")[0]
    text = text.replace("<!-- SC_OFF -->", "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_rss(subreddit: str, limit: int) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/hot/.rss?limit={limit}"

    resp = requests.get(url, headers=_HEADERS, timeout=10)
    if resp.status_code == 429:
        # Observed to be a global-ish budget, not cleanly per-feed (see
        # module docstring) — one retry after a real backoff, not an
        # immediate re-request, since an immediate retry would just 429 again.
        time.sleep(_RSS_RETRY_BACKOFF_SECONDS)
        resp = requests.get(url, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    entries = root.findall("a:entry", _ATOM_NS)
    stories = []
    for i, entry in enumerate(entries):
        title = entry.findtext("a:title", default="", namespaces=_ATOM_NS)
        if not title or _META_TITLE_RE.search(title):
            continue

        raw_content = entry.findtext("a:content", default="", namespaces=_ATOM_NS)
        content = _clean_rss_content(raw_content)

        entry_id = entry.findtext("a:id", default="", namespaces=_ATOM_NS)  # e.g. "t3_1wc44z7"
        source_id = entry_id.split("_", 1)[-1] if entry_id else None

        if not content or not source_id:
            continue

        stories.append(
            {
                "source": "reddit",
                "source_id": source_id,
                "title": title,
                "content": content,
                "subreddit": subreddit,
                # No real upvote/comment counts in RSS — use "hot" feed
                # position as a synthetic ranking proxy instead.
                "score": max(0, len(entries) - i) * 10,
                "num_comments": 0,
            }
        )
    return stories


def _from_raw(raw: dict, subreddit: str) -> Optional[dict[str, Any]]:
    if not raw.get("selftext") or raw.get("over_18") or raw.get("stickied"):
        return None
    return {
        "source": "reddit",
        "source_id": raw["id"],
        "title": raw["title"],
        "content": raw["selftext"],
        "subreddit": subreddit,
        "score": raw.get("score", 0),
        "num_comments": raw.get("num_comments", 0),
    }


def _fetch_public_json(subreddit: str, limit: int) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    resp = requests.get(url, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    children = resp.json()["data"]["children"]
    stories = [_from_raw(c["data"], subreddit) for c in children]
    return [s for s in stories if s]


def _fetch_praw(subreddit: str, limit: int) -> list[dict[str, Any]]:
    import praw  # imported lazily — only needed when credentials are configured

    reddit = praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
    )
    stories = []
    for post in reddit.subreddit(subreddit).hot(limit=limit):
        s = _from_raw(
            {
                "id": post.id,
                "title": post.title,
                "selftext": post.selftext,
                "over_18": post.over_18,
                "stickied": post.stickied,
                "score": post.score,
                "num_comments": post.num_comments,
            },
            subreddit,
        )
        if s:
            stories.append(s)
    return stories


def fetch_stories(subreddits: list[str], limit: int = 10) -> list[dict[str, Any]]:
    use_praw = bool(settings.reddit_client_id and settings.reddit_client_secret)

    all_stories: list[dict[str, Any]] = []
    for i, subreddit in enumerate(subreddits):
        if i > 0 and not use_praw:
            # RSS's rate limit behaves like a global-ish budget (see module
            # docstring) — pace requests within this call rather than
            # bursting them, so later subreddits don't just 429 immediately.
            time.sleep(_RSS_INTER_SUBREDDIT_DELAY_SECONDS)

        fetchers = [_fetch_praw] if use_praw else [_fetch_rss, _fetch_public_json]
        fetched = False
        for fetcher in fetchers:
            try:
                all_stories.extend(fetcher(subreddit, limit))
                fetched = True
                break
            except Exception as exc:  # noqa: BLE001 — try the next fetcher
                print(f"WARNING: {fetcher.__name__} failed for r/{subreddit}: {exc}")
        if not fetched:
            print(f"WARNING: all sourcing methods failed for r/{subreddit}")

    return all_stories

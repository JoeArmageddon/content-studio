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


_ARCTIC_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
_ARCTIC_WINDOW_DAYS = 7  # posts older than ~a day carry settled scores; a week keeps small subs viable
_ARCTIC_MIN_AGE_HOURS = 20  # skip the last ~day: scores there are still ingest-time values (~1)


def _fetch_arctic_shift(subreddit: str, limit: int) -> list[dict[str, Any]]:
    """Reddit archive mirror (arctic-shift) — free, no key, and NOT blocked
    from datacenter IPs (Reddit's own endpoints 403/404 GitHub Actions
    runners; discovered on the first real Actions run). Gives REAL scores,
    unlike RSS's position proxy, so curation ranks by actual engagement.
    Trade-off: it's a third-party archive, so posts are 20h+ old by the time
    their score is trustworthy — fine for evergreen story content."""
    now = time.time()
    fmt = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t))  # noqa: E731
    resp = requests.get(
        _ARCTIC_URL,
        params={
            "subreddit": subreddit,
            "after": fmt(now - _ARCTIC_WINDOW_DAYS * 86400),
            "before": fmt(now - _ARCTIC_MIN_AGE_HOURS * 3600),
            "limit": 100,
            "sort": "desc",
        },
        headers=_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    stories = []
    for raw in resp.json().get("data", []):
        body = (raw.get("selftext") or "").strip()
        if body in ("", "[removed]", "[deleted]") or _META_TITLE_RE.search(raw.get("title", "")):
            continue
        s = _from_raw(raw, subreddit)
        if s:
            stories.append(s)
    stories.sort(key=lambda x: x["score"], reverse=True)
    return stories[:limit]


# --- Question-only subreddits (AskReddit) -------------------------------------
# These have NO post body — the "story" is the thread itself: the question plus
# its best top-level answers. Reddit's own endpoints are blocked from CI, so the
# answers come from the same arctic-shift archive as everything else.
_THREAD_SUBREDDITS = {"askreddit"}
_ARCTIC_COMMENTS_URL = "https://arctic-shift.photon-reddit.com/api/comments/search"
_ANSWER_MIN_WORDS, _ANSWER_MAX_WORDS, _ANSWERS_PER_THREAD, _THREADS_TO_SCAN = 14, 130, 4, 8
_URL_RE = re.compile(r"https?://|www\.", re.I)


def _usable_answer(c: dict) -> bool:
    body = (c.get("body") or "").strip()
    n = len(body.split())
    return (
        c.get("parent_id", "").startswith("t3_")  # top-level answers only
        and body not in ("[removed]", "[deleted]")
        and c.get("author") not in ("AutoModerator", "[deleted]")
        and _ANSWER_MIN_WORDS <= n <= _ANSWER_MAX_WORDS
        and not _URL_RE.search(body)
    )


def _fetch_arctic_threads(subreddit: str, limit: int) -> list[dict[str, Any]]:
    now = time.time()
    fmt = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t))  # noqa: E731
    resp = requests.get(
        _ARCTIC_URL,
        params={
            "subreddit": subreddit,
            "after": fmt(now - _ARCTIC_WINDOW_DAYS * 86400),
            "before": fmt(now - _ARCTIC_MIN_AGE_HOURS * 3600),
            "limit": 100,
            "sort": "desc",
        },
        headers=_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    posts = [
        p for p in resp.json().get("data", [])
        if not p.get("over_18") and not p.get("stickied")
        and not _META_TITLE_RE.search(p.get("title", "")) and (p.get("title") or "").strip().endswith("?")
    ]
    # Archive scores for fresh posts are unsettled — comment count is the reliable engagement signal.
    posts.sort(key=lambda p: p.get("num_comments", 0), reverse=True)

    stories: list[dict[str, Any]] = []
    for post in posts[:_THREADS_TO_SCAN]:
        try:
            cr = requests.get(
                _ARCTIC_COMMENTS_URL,
                params={"link_id": post["id"], "limit": 100, "sort": "desc"},
                headers=_HEADERS, timeout=30,
            )
            cr.raise_for_status()
            comments = cr.json().get("data", [])
        except Exception as exc:  # noqa: BLE001 — skip this thread, try the next
            print(f"WARNING: comments fetch failed for {post['id']}: {exc}")
            continue
        answers = sorted((c for c in comments if _usable_answer(c)), key=lambda c: c.get("score", 0), reverse=True)
        if len(answers) < 3:
            continue  # not enough substance for a ~45s short
        picked = answers[:_ANSWERS_PER_THREAD]
        body = "\n\n".join(f"Answer {i}: {a['body'].strip()}" for i, a in enumerate(picked, 1))
        stories.append(
            {
                "source": "reddit",
                "source_id": post["id"],
                "title": post["title"].strip(),
                "content": f"Question asked on r/{subreddit}: {post['title'].strip()}\n\n{body}",
                "subreddit": subreddit,
                "score": post.get("num_comments", 0) * 5 + sum(a.get("score", 0) for a in picked),
                "num_comments": post.get("num_comments", 0),
            }
        )
    stories.sort(key=lambda x: x["score"], reverse=True)
    return stories[:limit]


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
    # Order: PRAW (if approved creds) > arctic-shift (real scores, works from
    # CI) > RSS (position-proxy scores, blocked from datacenter IPs) > public JSON.
    fetchers = [_fetch_praw] if use_praw else [_fetch_arctic_shift, _fetch_rss, _fetch_public_json]

    all_stories: list[dict[str, Any]] = []
    rss_calls_made = False
    for subreddit in subreddits:
        fetched = False
        # Question-only subs have no post body for the normal fetchers to find.
        sub_fetchers = [_fetch_arctic_threads] if subreddit.lower() in _THREAD_SUBREDDITS else fetchers
        for fetcher in sub_fetchers:
            if fetcher is _fetch_rss:
                if rss_calls_made:
                    # RSS's rate limit behaves like a global-ish budget (see
                    # module docstring) — pace RSS requests only.
                    time.sleep(_RSS_INTER_SUBREDDIT_DELAY_SECONDS)
                rss_calls_made = True
            try:
                result = fetcher(subreddit, limit)
                if not result:
                    raise RuntimeError("returned no usable posts")
                all_stories.extend(result)
                fetched = True
                break
            except Exception as exc:  # noqa: BLE001 — try the next fetcher
                print(f"WARNING: {fetcher.__name__} failed for r/{subreddit}: {exc}")
        if not fetched:
            print(f"WARNING: all sourcing methods failed for r/{subreddit}")

    return all_stories

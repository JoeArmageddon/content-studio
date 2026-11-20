"""
Niche-fit gate for channels whose source subreddits are broad.

Some channels (Real-Life Survival, Rich vs Poor) can only be sourced from
general-purpose subreddits, where most posts are questions, rants or
off-topic. Ranking by score alone lets those through, so curation asks the
LLM (one Groq call per small batch) whether each top candidate genuinely
fits the channel's niche and picks the best-ranked one that does.

Channels without an entry in _CRITERIA are never gated.
"""
import json
import re

_CRITERIA = {
    "reallife_survival": (
        "a first-person TRUE STORY about an outdoor trip or survival situation where something went wrong, "
        "got dangerous, scary or tense: getting lost, bad weather, injury, wildlife, being stranded, running "
        "out of supplies or gear failing, a close call, or a hard decision that mattered. A pure scenery or "
        "route report, a question, a gear review or an advice request is NOT a match"
    ),
    "rich_v_poor": (
        "a first-person story about money and class where the wealth gap itself is the point: rich versus "
        "poor, someone treated differently or looked down on over money, sudden wealth or sudden poverty, "
        "struggling while others around you are rich, or a clash between social classes. Generic job "
        "complaints, budgeting or investing questions, and advice posts are NOT a match"
    ),
}

_SYSTEM = (
    "You screen Reddit posts for a YouTube Shorts channel. Grade each numbered post: 2 = clearly {strict}; "
    "1 = a first-person personal story that is only loosely on theme ({loose}); 0 = anything else, such as "
    "questions, advice requests, news, memes, pure opinions, or posts unrelated to the theme. Reply with ONLY "
    "a JSON array of integers (0, 1 or 2), one per post, in order, with exactly as many items as posts."
)

_LOOSE = {
    "reallife_survival": (
        "an outdoor, hiking, camping or wilderness experience with some hardship, challenge or surprise, "
        "even if nothing life-threatening happened"
    ),
    "rich_v_poor": (
        "a personal story about money, poverty, wealth, pay or social class, including struggling "
        "financially or being treated differently over money"
    ),
}


def is_gated(channel_key: str | None) -> bool:
    return channel_key in _CRITERIA


def fit_scores(channel_key: str, candidates: list[dict]) -> list[int] | None:
    """One LLM call for the batch: 2 = strong niche fit, 1 = loosely on theme, 0 = off niche.
    Returns None if the call or its output can't be trusted, so the caller can fall back to
    un-gated ranking instead of failing the run."""
    if not candidates:
        return []
    from app.services import llm_clients

    lines = []
    for i, c in enumerate(candidates):
        body = " ".join((c.get("content") or "").split())[:350]
        lines.append(f"{i + 1}. TITLE: {c.get('title', '')}\n   START: {body}")
    try:
        raw = llm_clients.generate(
            "\n".join(lines),
            system=_SYSTEM.format(strict=_CRITERIA[channel_key], loose=_LOOSE[channel_key]),
            max_tokens=6 * len(candidates) + 20,
            temperature=0,
        )
        match = re.search(r"\[.*\]", raw, re.S)
        scores = json.loads(match.group(0)) if match else None
    except Exception as exc:  # noqa: BLE001 — never fail a run on the screener
        print(f"WARNING: niche-fit check failed, ranking without it: {exc}")
        return None
    if (
        not isinstance(scores, list)
        or len(scores) != len(candidates)
        or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 2 for x in scores)
    ):
        print("WARNING: niche-fit check returned an unusable answer, ranking without it")
        return None
    return scores

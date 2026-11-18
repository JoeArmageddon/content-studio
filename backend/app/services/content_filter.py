"""
Tones down slurs in anything that gets spoken, shown or published.

Reddit stories often quote slurs; spoken aloud or in a title they risk
limited ads / strikes on YouTube. Rather than skip such stories, the slur is
swapped for a softer phrase ("the N-word", "a slur") — the story still makes
sense. Ordinary profanity is deliberately left alone. Applied to the hook,
script and metadata (see script_qa_agent / metadata_agent), so the story
card, captions and voice-over all get the softened text.
"""
import re

# (pattern, replacement) — order matters: specific forms before generic ones.
_ART = r"(?:\b(?:a|an|the)\s+)?"  # swallow a leading article so the replacement reads naturally
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(_ART + r"\bn[i1!]+gg+(?:er|a|ah|uh)s?\b", re.I), "the N-word"),
    (re.compile(_ART + r"\bf[a@]gg?(?:ot|it)s?\b", re.I), "a slur"),
    (re.compile(_ART + r"\btr[a@]nn(?:y|ie)s?\b", re.I), "a slur"),
    (re.compile(_ART + r"\b(?:ch[i1]nks?|sp[i1]cs?|k[i1]kes?|wetbacks?|gooks?|towelheads?|sandn[i1]gg\w*)\b", re.I), "a slur"),
    (re.compile(r"\b(?:a|an)\s+retards?\b", re.I), "an idiot"),
    (re.compile(r"\bretards?\b", re.I), "idiot"),
    (re.compile(r"\bretarded\b", re.I), "idiotic"),
]


def soften(text: str | None) -> str | None:
    if not text:
        return text
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return re.sub(r"\ba (?=idiot(?:ic)?\b)", "an ", text)


def contains_slur(text: str | None) -> bool:
    return bool(text) and any(p.search(text) for p, _ in _RULES)

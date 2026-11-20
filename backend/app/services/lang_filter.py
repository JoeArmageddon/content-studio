"""
English-only filter for competitor data.

The competitor scan searches YouTube for videos in each niche; without a language hint it
returns plenty of Hindi / Hinglish / other-language videos, whose titles and hashtags then
ended up in our English hook, script and metadata prompts. Three cheap checks, no deps:
  1. the video's own declared language (defaultAudioLanguage / defaultLanguage), if set,
  2. script: mostly non-Latin letters (Devanagari, Arabic, CJK, ...) => not English,
  3. romanised-Hindi/Urdu marker words ("kahani", "chudail", "ki", "wali", ...).
"""
import re
import unicodedata

# Strong markers: one is enough. Weak markers: two needed (they are short and could be English).
_STRONG = {
    "hindi", "hinglish", "urdu", "kahani", "kahaniya", "bhoot", "bhootiya", "chudail", "pyaar", "dosti",
    "bhabhi", "jaadu", "shaadi", "gaon", "ghar", "bhai", "didi", "yaar", "zindagi", "desi", "bollywood",
    "dikh", "dikha", "gaye", "gayi", "bhule", "munne", "mujhe", "tumhare", "bahut", "bohot", "sabse", "kaise",
    "kyun", "kyu", "lekin", "magar", "sachchi", "pehli", "bachpan", "dukh", "maa", "papa", "mummy", "beta", "beti",
    "shivamsingh", "varunbundela",
}
_WEAK = {
    "ki", "ke", "ka", "ko", "mein", "se", "wali", "wala", "hai", "hain", "aur", "yeh", "kya", "ek", "tha", "thi",
    "nahi", "raat", "ne", "mai", "mere", "mera", "meri", "jana", "na", "ye", "wo", "woh", "gaya", "hua", "hui",
    "raha", "rahi", "apna", "apni", "tum", "hum", "kar", "karo", "sach", "baad", "log",
}
_WORD = re.compile(r"[a-z]+")


def declared_language_ok(lang: str | None) -> bool:
    """True if no language is declared, or it is English (en, en-US, en-GB, ...)."""
    return not lang or lang.lower().startswith("en")


def looks_english(text: str | None) -> bool:
    if not text:
        return False
    letters = [ch for ch in text if unicodedata.category(ch).startswith("L")]
    if not letters:
        return False
    non_latin = sum(1 for ch in letters if "LATIN" not in unicodedata.name(ch, ""))
    if non_latin / len(letters) > 0.2:
        return False
    words = _WORD.findall(text.lower())
    if any(w in _STRONG for w in words):
        return False
    return sum(1 for w in words if w in _WEAK) < 2


def hashtag_ok(tag: str) -> bool:
    """Hashtags: ASCII only and not a known Hindi/Urdu marker."""
    body = tag.lstrip("#").replace("_", " ")
    return bool(body) and body.isascii() and not any(w in _STRONG for w in _WORD.findall(body.lower()))

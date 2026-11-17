"""
LLM client wrappers — Milestone 3.

Groq (free tier) is tried first for Hook/Scriptwriter/Script QA agents,
Google Gemini (free tier) as fallback if Groq isn't configured or fails —
mirrors StoriqueOS's provider choice, which already proved workable on the
free tier. Raises a clear error (not a silent empty string) when neither is
configured, so callers can decide how to degrade gracefully.
"""
from typing import Optional

from app.core.config import settings

_GEMINI_MODEL = "gemini-1.5-flash"  # NOT re-verified — likely retired like Groq's Llama was; confirm before relying on this fallback

# Reasoning models (openai/gpt-oss-*) spend part of max_tokens on hidden
# reasoning, so a tight limit (e.g. the Hook Agent's 60) can come back as an
# EMPTY string with finish_reason="length" — caught when the Llama model we
# originally hardcoded was retired by Groq and its replacement was tested.
_REASONING_HEADROOM_TOKENS = 300


class LLMNotConfigured(RuntimeError):
    """Raised when neither GROQ_API_KEY nor GEMINI_API_KEY is set."""


def _generate_groq(prompt: str, system: Optional[str], max_tokens: int, temperature: float) -> str:
    from groq import Groq  # imported lazily — only needed on this path

    client = Groq(api_key=settings.groq_api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    extra = {}
    if "gpt-oss" in settings.groq_model:
        extra["reasoning_effort"] = "low"
        max_tokens += _REASONING_HEADROOM_TOKENS

    resp = client.chat.completions.create(
        model=settings.groq_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        **extra,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError(
            f"Groq model {settings.groq_model} returned empty content "
            f"(finish_reason={resp.choices[0].finish_reason})"
        )
    return text


def _generate_gemini(prompt: str, system: Optional[str], max_tokens: int, temperature: float) -> str:
    import google.generativeai as genai  # imported lazily

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(_GEMINI_MODEL, system_instruction=system)
    resp = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": max_tokens, "temperature": temperature},
    )
    return resp.text.strip()


def generate(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = 500,
    temperature: float = 0.9,
) -> str:
    """Groq first, Gemini fallback. Raises if neither is configured or both fail."""
    errors = []

    if settings.groq_api_key:
        try:
            return _generate_groq(prompt, system, max_tokens, temperature)
        except Exception as exc:  # noqa: BLE001 — fall through to Gemini
            errors.append(f"groq: {exc}")

    if settings.gemini_api_key:
        try:
            return _generate_gemini(prompt, system, max_tokens, temperature)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"gemini: {exc}")

    if errors:
        raise RuntimeError(f"All configured LLM providers failed: {'; '.join(errors)}")
    raise LLMNotConfigured(
        "No LLM configured — set GROQ_API_KEY or GEMINI_API_KEY in backend/.env "
        "(both have free tiers; see .env.example)"
    )

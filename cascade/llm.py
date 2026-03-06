"""Unified LLM interface for OpenAI and Anthropic Claude."""

from __future__ import annotations

import logging
from typing import Generator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from cascade.config import get_settings
from cascade.exceptions import ConfigError, LLMError

console = Console()
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal clients (lazy-initialised)
# ---------------------------------------------------------------------------
_openai_client = None
_anthropic_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        s = get_settings()
        if not s.openai_api_key:
            raise ConfigError("OPENAI_API_KEY is not set. Add it to your .env file.")
        _openai_client = OpenAI(api_key=s.openai_api_key)
    return _openai_client


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        s = get_settings()
        if not s.anthropic_api_key:
            raise ConfigError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
        _anthropic_client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    return _anthropic_client


# ---------------------------------------------------------------------------
# Core ask functions
# ---------------------------------------------------------------------------

def ask_openai(
    prompt: str,
    system: str = "You are a helpful research assistant.",
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Send a prompt to OpenAI and return the full response text."""
    client = _get_openai()
    s = get_settings()
    try:
        resp = client.chat.completions.create(
            model=model or s.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        log.error("OpenAI API error: %s", e)
        raise LLMError(f"OpenAI API call failed: {e}") from e


def ask_claude(
    prompt: str,
    system: str = "You are a helpful research assistant.",
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Send a prompt to Anthropic Claude and return the full response text."""
    client = _get_anthropic()
    s = get_settings()
    try:
        resp = client.messages.create(
            model=model or s.claude_model,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.content[0].text
    except Exception as e:
        log.error("Claude API error: %s", e)
        raise LLMError(f"Claude API call failed: {e}") from e


def ask(
    prompt: str,
    system: str = "You are a helpful research assistant.",
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Unified ask — routes to OpenAI or Claude based on provider setting."""
    s = get_settings()
    provider = provider or s.default_llm
    if provider == "openai":
        return ask_openai(prompt, system, model, temperature, max_tokens)
    else:
        return ask_claude(prompt, system, model, temperature, max_tokens)


# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------

def stream_openai(
    prompt: str,
    system: str = "You are a helpful research assistant.",
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Generator[str, None, None]:
    """Yield text chunks from OpenAI streaming response."""
    client = _get_openai()
    s = get_settings()
    stream = client.chat.completions.create(
        model=model or s.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def stream_claude(
    prompt: str,
    system: str = "You are a helpful research assistant.",
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Generator[str, None, None]:
    """Yield text chunks from Claude streaming response."""
    client = _get_anthropic()
    s = get_settings()
    with client.messages.stream(
        model=model or s.claude_model,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    ) as stream:
        for text in stream.text_stream:
            yield text


def stream_ask(
    prompt: str,
    system: str = "You are a helpful research assistant.",
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Generator[str, None, None]:
    """Unified streaming — yields text chunks from the chosen provider."""
    s = get_settings()
    provider = provider or s.default_llm
    if provider == "openai":
        yield from stream_openai(prompt, system, model, temperature, max_tokens)
    else:
        yield from stream_claude(prompt, system, model, temperature, max_tokens)


def ask_and_display(
    prompt: str,
    system: str = "You are a helpful research assistant.",
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Stream LLM response to terminal with Rich live markdown rendering."""
    full_text = ""
    with Live(Markdown(""), console=console, refresh_per_second=8) as live:
        for chunk in stream_ask(prompt, system, provider, model, temperature, max_tokens):
            full_text += chunk
            live.update(Markdown(full_text))
    return full_text


def ask_both(
    prompt: str,
    system: str = "You are a helpful research assistant.",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> dict[str, str]:
    """Ask both OpenAI and Claude, return dict with both responses."""
    results: dict[str, str] = {}
    s = get_settings()
    if s.openai_api_key:
        try:
            results["openai"] = ask_openai(prompt, system, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:
            results["openai"] = f"[Error] {e}"
    if s.anthropic_api_key:
        try:
            results["claude"] = ask_claude(prompt, system, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:
            results["claude"] = f"[Error] {e}"
    return results

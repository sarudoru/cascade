"""Token budget management for LLM context windows.

Provides token counting and intelligent truncation to prevent silent
context overflow when building prompts from paper content.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

# Approximate chars-per-token for rough estimation (used as fallback)
_CHARS_PER_TOKEN_ESTIMATE = 4


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in *text* for the given model.

    Uses ``tiktoken`` for OpenAI models and a character-based estimate
    for Claude / other models.
    """
    try:
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        log.debug("tiktoken not installed — using character estimate")
        return len(text) // _CHARS_PER_TOKEN_ESTIMATE


# ---------------------------------------------------------------------------
# Model context limits (conservative usable limits leaving room for output)
# ---------------------------------------------------------------------------

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # OpenAI
    "gpt-4": 6_000,
    "gpt-4-turbo": 100_000,
    "gpt-4o": 100_000,
    "gpt-5.2": 100_000,
    # Claude
    "claude-opus-4-6": 150_000,
    "claude-sonnet-4-6": 150_000,
    "claude-3-opus": 150_000,
    "claude-3-sonnet": 150_000,
}

DEFAULT_CONTEXT_LIMIT = 8_000  # Safe fallback


def get_context_limit(model: str) -> int:
    """Return the usable context limit for a model."""
    return MODEL_CONTEXT_LIMITS.get(model, DEFAULT_CONTEXT_LIMIT)


# ---------------------------------------------------------------------------
# Intelligent truncation
# ---------------------------------------------------------------------------

def truncate_to_budget(text: str, max_tokens: int, model: str = "gpt-4") -> str:
    """Truncate *text* to fit within *max_tokens*.

    Truncates at paragraph boundaries when possible and appends an
    indicator that the text was shortened.
    """
    current = count_tokens(text, model)
    if current <= max_tokens:
        return text

    # Binary search for the right character cutoff
    ratio = max_tokens / current
    char_budget = int(len(text) * ratio * 0.95)  # 5% safety margin

    truncated = text[:char_budget]

    # Try to cut at the last paragraph break
    last_para = truncated.rfind("\n\n")
    if last_para > char_budget * 0.5:
        truncated = truncated[:last_para]

    return truncated + "\n\n[... truncated to fit token budget ...]"


# ---------------------------------------------------------------------------
# Budgeted context builder for paper lists
# ---------------------------------------------------------------------------

def build_budgeted_context(
    papers: list[dict[str, Any]],
    max_tokens: int | None = None,
    model: str = "gpt-4",
) -> str:
    """Build an LLM context string from papers, staying within budget.

    Papers are prioritised by citation count (descending) so the most
    impactful work is included first.  Each paper contributes its title,
    authors, year, and abstract (truncated if needed).

    Parameters
    ----------
    papers : list[dict]
        Paper dicts (as returned by ``Memory.search_papers``).
    max_tokens : int, optional
        Token budget.  Defaults to model's context limit.
    model : str
        Model name for token counting.
    """
    import json

    budget = max_tokens or get_context_limit(model)
    # Reserve ~20% for system prompt + user query + output
    budget = int(budget * 0.6)

    # Sort by citation count (highest first), then year
    def _sort_key(p: dict) -> tuple:
        cites = p.get("citations") or p.get("citation_count") or 0
        year = p.get("year") or 0
        return (-cites, -year)

    sorted_papers = sorted(papers, key=_sort_key)

    parts: list[str] = ["## Relevant Papers\n"]
    used_tokens = count_tokens(parts[0], model)

    for p in sorted_papers:
        authors_raw = p.get("authors", "[]")
        if isinstance(authors_raw, str):
            try:
                authors = json.loads(authors_raw)
            except json.JSONDecodeError:
                authors = [authors_raw]
        else:
            authors = list(authors_raw)

        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."

        abstract = (p.get("abstract") or "")[:500]
        entry = (
            f"- **{p.get('title', 'Untitled')}** ({p.get('year', '?')}) — {author_str}\n"
            f"  {abstract}\n"
        )

        entry_tokens = count_tokens(entry, model)
        if used_tokens + entry_tokens > budget:
            parts.append("\n[... additional papers omitted due to token budget ...]\n")
            break

        parts.append(entry)
        used_tokens += entry_tokens

    return "\n".join(parts)

"""Export utilities — BibTeX generation from stored papers."""

from __future__ import annotations

import json
import re
from typing import Any


def _sanitise_bibtex(text: str) -> str:
    """Escape special LaTeX characters in a string."""
    for char in ("&", "%", "$", "#", "_"):
        text = text.replace(char, f"\\{char}")
    return text


def paper_to_bibtex(paper: dict[str, Any]) -> str:
    """Convert a paper row (dict from Memory) into a BibTeX entry.

    Produces an ``@article`` entry with a generated cite key.
    """
    # Parse authors
    authors_raw = paper.get("authors", "[]")
    if isinstance(authors_raw, str):
        try:
            authors = json.loads(authors_raw)
        except json.JSONDecodeError:
            authors = [authors_raw]
    else:
        authors = list(authors_raw)

    # Generate cite key: first-author-last-name + year
    first_last = "unknown"
    if authors:
        parts = authors[0].split()
        if parts:
            first_last = re.sub(r"[^a-zA-Z]", "", parts[-1]).lower()
    year = paper.get("year", 0)
    cite_key = f"{first_last}{year}"

    # Build BibTeX fields
    title = _sanitise_bibtex(paper.get("title", ""))
    author_str = _sanitise_bibtex(" and ".join(authors))
    url = paper.get("url", "")
    doi = paper.get("doi", "")
    arxiv_id = paper.get("arxiv_id", "")

    lines = [f"@article{{{cite_key},"]
    lines.append(f"  title = {{{title}}},")
    lines.append(f"  author = {{{author_str}}},")
    lines.append(f"  year = {{{year}}},")
    if url:
        lines.append(f"  url = {{{url}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    if arxiv_id:
        lines.append(f"  eprint = {{{arxiv_id}}},")
        lines.append("  archiveprefix = {arXiv},")
    lines.append("}")
    return "\n".join(lines)


def papers_to_bibtex(papers: list[dict[str, Any]]) -> str:
    """Convert a list of paper dicts to a full .bib file string."""
    entries: list[str] = []
    seen_keys: set[str] = set()

    for p in papers:
        entry = paper_to_bibtex(p)
        # Deduplicate by cite key — append suffix if needed
        key_match = re.match(r"@article\{(\w+),", entry)
        if key_match:
            key = key_match.group(1)
            if key in seen_keys:
                suffix = "b"
                while f"{key}{suffix}" in seen_keys:
                    suffix = chr(ord(suffix) + 1)
                new_key = f"{key}{suffix}"
                entry = entry.replace(f"@article{{{key},", f"@article{{{new_key},", 1)
                seen_keys.add(new_key)
            else:
                seen_keys.add(key)

        entries.append(entry)

    return "\n\n".join(entries) + "\n"

"""DBLP API wrapper for venue-aware academic paper search.

DBLP (https://dblp.org) is a computer science bibliography database with
excellent venue/conference metadata.  Free, no API key required.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from cascade.config import get_settings
from cascade.exceptions import SearchError
from cascade.search.arxiv_search import Paper

log = logging.getLogger(__name__)

BASE_URL = "https://dblp.org/search/publ/api"

# Persistent HTTP session
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Return a shared HTTP session (connection-pooled)."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Cascade/0.1",
        })
    return _session


def _request_with_retry(
    url: str,
    params: dict[str, Any],
    max_retries: int = 3,
) -> dict:
    """GET *url* with retry logic for transient failures."""
    session = _get_session()
    for attempt in range(max_retries + 1):
        try:
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    log.warning(
                        "DBLP returned %d, retrying in %ds (%d/%d)",
                        resp.status_code, wait, attempt + 1, max_retries,
                    )
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise SearchError(f"DBLP request failed: {e}") from e
    raise SearchError("DBLP request failed after retries")


def _parse_hit(hit: dict) -> Paper | None:
    """Convert a DBLP hit to a Paper."""
    info = hit.get("info", {})
    title = info.get("title", "").rstrip(".")
    if not title:
        return None

    # Authors — DBLP returns either a string or a list
    authors_raw = info.get("authors", {}).get("author", [])
    if isinstance(authors_raw, str):
        authors = [authors_raw]
    elif isinstance(authors_raw, dict):
        authors = [authors_raw.get("text", authors_raw.get("@pid", ""))]
    elif isinstance(authors_raw, list):
        authors = [
            (a.get("text", a) if isinstance(a, dict) else str(a))
            for a in authors_raw
        ]
    else:
        authors = []

    # URL
    url = info.get("ee", info.get("url", ""))
    if isinstance(url, list):
        url = url[0] if url else ""

    # Venue
    venue = info.get("venue", "")

    # DOI
    doi = info.get("doi", None)

    # Year
    try:
        year = int(info.get("year", 0))
    except (ValueError, TypeError):
        year = 0

    # Type mapping
    pub_type = info.get("type", "")
    categories = [venue] if venue else []
    if pub_type:
        categories.append(pub_type)

    return Paper(
        title=title,
        authors=authors,
        abstract="",  # DBLP doesn't provide abstracts
        url=url,
        year=year,
        source="dblp",
        categories=categories,
        doi=doi,
    )


def search_papers(
    query: str,
    max_results: int | None = None,
    venue: str | None = None,
) -> list[Paper]:
    """Search DBLP for papers matching the query.

    Parameters
    ----------
    query : str
        Free-text search query.
    max_results : int, optional
        Maximum results (default: from settings, max 1000).
    venue : str, optional
        Venue filter — appended to the query as ``venue:NAME``.
    """
    s = get_settings()
    limit = min(max_results or s.default_search_limit, 1000)

    search_query = query
    if venue:
        search_query = f"{query} venue:{venue}"

    params: dict[str, Any] = {
        "q": search_query,
        "h": limit,
        "format": "json",
    }

    try:
        data = _request_with_retry(BASE_URL, params)
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"DBLP search failed: {e}") from e

    result = data.get("result", {})
    hits_container = result.get("hits", {})
    hits = hits_container.get("hit", [])

    papers: list[Paper] = []
    for hit in hits:
        paper = _parse_hit(hit)
        if paper:
            papers.append(paper)

    return papers[:limit]

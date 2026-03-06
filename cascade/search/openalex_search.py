"""OpenAlex API wrapper for academic paper search.

OpenAlex (https://openalex.org) is a free, open bibliometric database with rich
metadata including citations, concepts, open-access links, and institutional
affiliations.  No API key required (polite pool: include email in User-Agent).
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

BASE_URL = "https://api.openalex.org"

# Persistent HTTP session
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Return a shared HTTP session (connection-pooled)."""
    global _session
    if _session is None:
        _session = requests.Session()
        # Polite pool: include contact email for higher rate limits
        _session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Cascade/0.1 (mailto:cascade@research.dev)",
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
                        "OpenAlex returned %d, retrying in %ds (%d/%d)",
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
            raise SearchError(f"OpenAlex request failed: {e}") from e
    raise SearchError("OpenAlex request failed after retries")


def _parse_work(work: dict) -> Paper | None:
    """Convert an OpenAlex Work object to a Paper."""
    title = work.get("title")
    if not title:
        return None

    # Authors
    authorships = work.get("authorships") or []
    authors = []
    for a in authorships[:10]:
        name = (a.get("author") or {}).get("display_name")
        if name:
            authors.append(name)

    # External IDs
    ids = work.get("ids") or {}
    doi_raw = ids.get("doi") or work.get("doi") or ""
    doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

    # Open access PDF
    oa = work.get("open_access") or {}
    pdf_url = oa.get("oa_url")

    # URL
    url = work.get("id") or ""  # OpenAlex ID URL
    if doi_raw:
        url = doi_raw

    # Abstract (OpenAlex returns inverted index, reconstruct)
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

    return Paper(
        title=title,
        authors=authors,
        abstract=abstract,
        url=url,
        year=work.get("publication_year") or 0,
        source="openalex",
        categories=[c.get("display_name", "") for c in (work.get("concepts") or [])[:5]],
        citation_count=work.get("cited_by_count"),
        doi=doi,
        pdf_url=pdf_url,
    )


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """Reconstruct abstract text from OpenAlex inverted index format."""
    if not inverted_index:
        return ""
    # {word: [position, ...]} → list of (position, word) → join
    pairs: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pairs)


def search_papers(
    query: str,
    max_results: int | None = None,
    year_range: str | None = None,
    venue: str | None = None,
) -> list[Paper]:
    """Search OpenAlex for papers matching the query.

    Parameters
    ----------
    query : str
        Free-text search query.
    max_results : int, optional
        Maximum results (default: from settings, max 200).
    year_range : str, optional
        Year filter, e.g. "2020-2024" or "2023-".
    venue : str, optional
        Venue/journal name filter.
    """
    s = get_settings()
    limit = min(max_results or s.default_search_limit, 200)

    # Build filter string
    filters: list[str] = []
    if year_range:
        if "-" in year_range:
            parts = year_range.split("-")
            if parts[0] and parts[1]:
                filters.append(f"publication_year:{parts[0]}-{parts[1]}")
            elif parts[0]:
                filters.append(f"from_publication_date:{parts[0]}-01-01")
        else:
            filters.append(f"publication_year:{year_range}")
    if venue:
        filters.append(f"primary_location.source.display_name.search:{venue}")

    params: dict[str, Any] = {
        "search": query,
        "per_page": limit,
        "sort": "cited_by_count:desc",
    }
    if filters:
        params["filter"] = ",".join(filters)

    try:
        data = _request_with_retry(f"{BASE_URL}/works", params)
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"OpenAlex search failed: {e}") from e

    papers: list[Paper] = []
    for work in data.get("results", []):
        paper = _parse_work(work)
        if paper:
            papers.append(paper)

    return papers[:limit]

"""Semantic Scholar API wrapper for academic paper search."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from cascade.config import get_settings
from cascade.exceptions import SearchError
from cascade.search.arxiv_search import Paper

log = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1"

# Fields to request from the API
PAPER_FIELDS = ",".join([
    "title",
    "abstract",
    "year",
    "citationCount",
    "authors",
    "externalIds",
    "url",
    "fieldsOfStudy",
    "publicationTypes",
])

# Persistent HTTP session for connection pooling
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Return a shared HTTP session (connection-pooled)."""
    global _session
    if _session is None:
        _session = requests.Session()
    _session.headers.update(_headers())
    return _session


def _headers() -> dict[str, str]:
    """Build request headers, including API key if available."""
    h = {"Accept": "application/json"}
    s = get_settings()
    if s.semantic_scholar_api_key:
        h["x-api-key"] = s.semantic_scholar_api_key
    return h


def _rate_limit_delay() -> None:
    """Respect rate limits — 1 RPS with key, shared pool without."""
    time.sleep(1.1)


def _request_with_retry(
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    **kwargs: Any,
) -> requests.Response:
    """Make an HTTP request with exponential backoff for 429 / 5xx."""
    session = _get_session()
    for attempt in range(max_retries + 1):
        try:
            resp = session.request(method, url, timeout=30, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    log.warning(
                        "S2 API returned %d, retrying in %ds (attempt %d/%d)",
                        resp.status_code, wait, attempt + 1, max_retries,
                    )
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise SearchError(f"Semantic Scholar API request failed: {e}") from e
    # Should not reach here, but just in case
    raise SearchError("Semantic Scholar API request failed after retries")


def get_paper_id_from_url(url_or_id: str) -> str:
    """Resolve any paper identifier to an S2 paper ID.

    Accepts: S2 paper ID, DOI (10.xxx or DOI:10.xxx), arXiv (ArXiv:xxx or
    2301.12345), full URLs (arxiv.org, doi.org, semanticscholar.org).
    """
    import re

    s = url_or_id.strip()

    # Already an S2 40-char hex ID
    if re.match(r"^[0-9a-f]{40}$", s):
        return s

    # DOI: prefix
    if s.upper().startswith("DOI:"):
        s = s[4:]

    # ArXiv: prefix
    if s.upper().startswith("ARXIV:"):
        s = f"ArXiv:{s[6:]}"
        return _resolve_s2_id(s)

    # URL parsing
    if "arxiv.org" in s:
        m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", s)
        if m:
            return _resolve_s2_id(f"ArXiv:{m.group(1)}")

    if "doi.org" in s:
        # Extract DOI after doi.org/
        m = re.search(r"doi\.org/(.+?)(?:\?|#|$)", s)
        if m:
            return _resolve_s2_id(m.group(1))

    if "semanticscholar.org" in s:
        m = re.search(r"/paper/[^/]*/([0-9a-f]{40})", s)
        if m:
            return m.group(1)

    # Bare DOI (10.xxx)
    if s.startswith("10."):
        return _resolve_s2_id(s)

    # Bare arXiv ID
    if re.match(r"^\d{4}\.\d{4,5}$", s):
        return _resolve_s2_id(f"ArXiv:{s}")

    # Last resort: assume it's a paper ID and pass through
    return s


def _resolve_s2_id(identifier: str) -> str:
    """Resolve an identifier (DOI / ArXiv:xxx) to S2 paper ID via API lookup."""
    resp = _request_with_retry("GET", f"{BASE_URL}/paper/{identifier}", params={"fields": "paperId"})
    data = resp.json()
    pid = data.get("paperId")
    if not pid:
        raise SearchError(f"Could not resolve paper ID for: {identifier}")
    return pid


# -----------------------------------------------------------------------
# Raw citation/reference helpers (return dicts with paperId for graph use)
# -----------------------------------------------------------------------

GRAPH_FIELDS = "paperId,title,year,citationCount,authors,abstract,url,externalIds"


def get_citations_raw(paper_id: str, max_results: int = 50) -> list[dict]:
    """Fetch raw citation dicts (with paperId) for the graph crawler."""
    try:
        resp = _request_with_retry(
            "GET",
            f"{BASE_URL}/paper/{paper_id}/citations",
            params={"fields": f"citingPaper.{GRAPH_FIELDS}", "limit": max_results},
        )
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Failed to fetch citations: {e}") from e
    _rate_limit_delay()

    results = []
    for item in resp.json().get("data", []):
        cp = item.get("citingPaper", {})
        if cp.get("paperId") and cp.get("title"):
            results.append(cp)
    return results


def get_references_raw(paper_id: str, max_results: int = 50) -> list[dict]:
    """Fetch raw reference dicts (with paperId) for the graph crawler."""
    try:
        resp = _request_with_retry(
            "GET",
            f"{BASE_URL}/paper/{paper_id}/references",
            params={"fields": f"citedPaper.{GRAPH_FIELDS}", "limit": max_results},
        )
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Failed to fetch references: {e}") from e
    _rate_limit_delay()

    results = []
    for item in resp.json().get("data", []):
        cp = item.get("citedPaper", {})
        if cp.get("paperId") and cp.get("title"):
            results.append(cp)
    return results


def get_paper_details_raw(paper_id: str) -> dict:
    """Fetch raw paper details dict for the graph crawler."""
    try:
        resp = _request_with_retry(
            "GET",
            f"{BASE_URL}/paper/{paper_id}",
            params={"fields": GRAPH_FIELDS},
        )
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Failed to fetch paper details: {e}") from e
    _rate_limit_delay()
    return resp.json()


def search_papers(
    query: str,
    max_results: int | None = None,
    year_range: str | None = None,
    fields_of_study: list[str] | None = None,
) -> list[Paper]:
    """Search Semantic Scholar for papers matching the query.

    Parameters
    ----------
    query : str
        Free-text search query.
    max_results : int, optional
        Maximum results to return.
    year_range : str, optional
        Year range filter, e.g. "2020-2024" or "2023-".
    fields_of_study : list[str], optional
        Filter by field, e.g. ["Computer Science"].
    """
    s = get_settings()
    limit = min(max_results or s.default_search_limit, 100)

    params: dict[str, Any] = {
        "query": query,
        "limit": limit,
        "fields": PAPER_FIELDS,
    }
    if year_range:
        params["year"] = year_range
    if fields_of_study:
        params["fieldsOfStudy"] = ",".join(fields_of_study)

    try:
        resp = _request_with_retry(
            "GET",
            f"{BASE_URL}/paper/search",
            params=params,
        )
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Semantic Scholar search failed: {e}") from e

    data = resp.json()

    papers: list[Paper] = []
    for item in data.get("data", []):
        if not item.get("title"):
            continue
        ext_ids = item.get("externalIds") or {}
        papers.append(
            Paper(
                title=item["title"],
                authors=[a.get("name", "") for a in (item.get("authors") or [])],
                abstract=item.get("abstract") or "",
                url=item.get("url") or f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}",
                year=item.get("year") or 0,
                source="semantic_scholar",
                categories=item.get("fieldsOfStudy") or [],
                citation_count=item.get("citationCount"),
                arxiv_id=ext_ids.get("ArXiv"),
                doi=ext_ids.get("DOI"),
            )
        )

    return papers


def get_paper_details(paper_id: str) -> dict[str, Any]:
    """Fetch detailed info for a single paper by Semantic Scholar ID, DOI, or arXiv ID.

    Use prefixes like "DOI:10.xxx" or "ArXiv:2301.12345".
    """
    fields = PAPER_FIELDS + ",references,citations,tldr"
    try:
        resp = _request_with_retry(
            "GET",
            f"{BASE_URL}/paper/{paper_id}",
            params={"fields": fields},
        )
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Failed to fetch paper details: {e}") from e
    _rate_limit_delay()
    return resp.json()


def get_citations(paper_id: str, max_results: int = 50) -> list[Paper]:
    """Fetch papers that cite the given paper."""
    fields = PAPER_FIELDS
    try:
        resp = _request_with_retry(
            "GET",
            f"{BASE_URL}/paper/{paper_id}/citations",
            params={"fields": f"citingPaper.{fields}", "limit": max_results},
        )
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Failed to fetch citations: {e}") from e
    _rate_limit_delay()

    papers: list[Paper] = []
    for item in resp.json().get("data", []):
        cp = item.get("citingPaper", {})
        if not cp.get("title"):
            continue
        ext_ids = cp.get("externalIds") or {}
        papers.append(
            Paper(
                title=cp["title"],
                authors=[a.get("name", "") for a in (cp.get("authors") or [])],
                abstract=cp.get("abstract") or "",
                url=cp.get("url") or "",
                year=cp.get("year") or 0,
                source="semantic_scholar",
                citation_count=cp.get("citationCount"),
                arxiv_id=ext_ids.get("ArXiv"),
                doi=ext_ids.get("DOI"),
            )
        )
    return papers


def get_references(paper_id: str, max_results: int = 50) -> list[Paper]:
    """Fetch papers referenced by the given paper."""
    fields = PAPER_FIELDS
    try:
        resp = _request_with_retry(
            "GET",
            f"{BASE_URL}/paper/{paper_id}/references",
            params={"fields": f"citedPaper.{fields}", "limit": max_results},
        )
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Failed to fetch references: {e}") from e
    _rate_limit_delay()

    papers: list[Paper] = []
    for item in resp.json().get("data", []):
        cp = item.get("citedPaper", {})
        if not cp.get("title"):
            continue
        ext_ids = cp.get("externalIds") or {}
        papers.append(
            Paper(
                title=cp["title"],
                authors=[a.get("name", "") for a in (cp.get("authors") or [])],
                abstract=cp.get("abstract") or "",
                url=cp.get("url") or "",
                year=cp.get("year") or 0,
                source="semantic_scholar",
                citation_count=cp.get("citationCount"),
                arxiv_id=ext_ids.get("ArXiv"),
                doi=ext_ids.get("DOI"),
            )
        )
    return papers


def get_recommendations(paper_id: str, max_results: int = 20) -> list[Paper]:
    """Fetch recommended (related) papers for the given paper.

    Uses S2's single-paper recommendations endpoint.
    """
    fields = PAPER_FIELDS
    try:
        resp = _request_with_retry(
            "POST",
            f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{paper_id}",
            params={"fields": fields, "limit": max_results},
        )
    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Failed to fetch recommendations: {e}") from e
    _rate_limit_delay()

    papers: list[Paper] = []
    for item in resp.json().get("recommendedPapers", []):
        if not item.get("title"):
            continue
        ext_ids = item.get("externalIds") or {}
        papers.append(
            Paper(
                title=item["title"],
                authors=[a.get("name", "") for a in (item.get("authors") or [])],
                abstract=item.get("abstract") or "",
                url=item.get("url") or "",
                year=item.get("year") or 0,
                source="semantic_scholar",
                citation_count=item.get("citationCount"),
                arxiv_id=ext_ids.get("ArXiv"),
                doi=ext_ids.get("DOI"),
            )
        )
    return papers


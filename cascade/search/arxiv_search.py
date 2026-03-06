"""arXiv paper search via the official `arxiv` Python package."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

import arxiv

from cascade.config import get_settings
from cascade.exceptions import SearchError

log = logging.getLogger(__name__)


@dataclass
class Paper:
    """Normalised paper representation used across all search backends."""

    title: str
    authors: list[str]
    abstract: str
    url: str
    year: int
    source: str  # "arxiv" | "semantic_scholar"
    categories: list[str] = field(default_factory=list)
    citation_count: int | None = None
    arxiv_id: str | None = None
    doi: str | None = None
    pdf_url: str | None = None

    @property
    def author_str(self) -> str:
        if len(self.authors) <= 3:
            return ", ".join(self.authors)
        return f"{self.authors[0]} et al."

    @property
    def bib_key(self) -> str:
        first = self.authors[0].split()[-1].lower() if self.authors else "unknown"
        return f"{first}{self.year}"


def search_arxiv(
    query: str,
    max_results: int | None = None,
    categories: list[str] | None = None,
    sort_by: arxiv.SortCriterion = arxiv.SortCriterion.Relevance,
) -> list[Paper]:
    """Search arXiv and return normalised Paper objects.

    Parameters
    ----------
    query : str
        Free-text search query.
    max_results : int, optional
        Maximum papers to return (defaults to config setting).
    categories : list[str], optional
        arXiv category codes to filter by, e.g. ["cs.CV", "cs.CL"].
    sort_by : arxiv.SortCriterion
        How to sort results (Relevance, LastUpdatedDate, SubmittedDate).
    """
    s = get_settings()
    limit = max_results or s.default_search_limit

    # Build category-aware query if categories provided
    if categories:
        cat_filter = " OR ".join(f"cat:{c}" for c in categories)
        full_query = f"({query}) AND ({cat_filter})"
    else:
        full_query = query

    client = arxiv.Client(
        page_size=min(limit, 50),
        delay_seconds=1.0,
        num_retries=3,
    )

    search = arxiv.Search(
        query=full_query,
        max_results=limit,
        sort_by=sort_by,
    )

    papers: list[Paper] = []
    try:
        for result in client.results(search):
            pub_date: datetime = result.published
            papers.append(
                Paper(
                    title=result.title.strip(),
                    authors=[a.name for a in result.authors],
                    abstract=result.summary.strip(),
                    url=result.entry_id,
                    year=pub_date.year,
                    source="arxiv",
                    categories=[c for c in result.categories],
                    arxiv_id=result.get_short_id(),
                    doi=result.doi,
                    pdf_url=result.pdf_url,
                )
            )
    except Exception as e:
        log.error("arXiv search failed: %s", e)
        raise SearchError(f"arXiv search failed: {e}") from e

    return papers


def search_arxiv_by_domain(
    query: str,
    domain: str | None = None,
    max_results: int | None = None,
) -> list[Paper]:
    """Search arXiv with domain-specific category filtering.

    Parameters
    ----------
    query : str
        The search query.
    domain : str, optional
        Domain key from config.DOMAINS (e.g. "cv-motion", "nlp-interp").
        If None, searches across all active domain categories.
    """
    from cascade.config import DOMAINS

    if domain and domain in DOMAINS:
        cats = DOMAINS[domain]["arxiv_categories"]
    else:
        cats = get_settings().get_arxiv_categories()

    return search_arxiv(query, max_results=max_results, categories=cats)

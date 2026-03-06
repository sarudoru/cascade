"""Search API — multi-source paper search."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

from cascade.engine import _collect_papers

log = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


def _paper_to_dict(paper) -> dict:
    """Convert a Paper dataclass to a JSON-serialisable dict."""
    return {
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "url": paper.url,
        "year": paper.year,
        "source": paper.source,
        "categories": paper.categories,
        "citationCount": paper.citation_count,
        "arxivId": paper.arxiv_id,
        "doi": paper.doi,
        "pdfUrl": paper.pdf_url,
    }


@router.get("/search")
async def search_papers(
    q: str = Query(..., description="Search query"),
    sources: str = Query("arxiv,scholar", description="Comma-separated sources"),
    limit: int = Query(10, ge=1, le=50, description="Max results per source"),
):
    """Search for academic papers across sources."""
    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    try:
        papers = _collect_papers(q, sources=source_list or None, limit=limit)
    except Exception as e:
        log.exception("Search failed")
        return {"papers": [], "error": str(e)}

    # Save to memory in background
    try:
        from cascade.memory import Memory
        with Memory() as mem:
            mem.save_papers(papers)
    except Exception:
        pass

    return {
        "papers": [_paper_to_dict(p) for p in papers],
        "query": q,
        "sources": source_list,
        "total": len(papers),
    }

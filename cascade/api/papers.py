"""Papers API — read, store, and query papers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/papers", tags=["papers"])


class ReadRequest(BaseModel):
    url: str
    summarize: bool = False
    include_findings: bool = False


@router.post("/read")
async def read_paper_endpoint(request: ReadRequest):
    """Fetch and parse a paper from any supported URL."""
    from cascade.reader import read_paper, summarise_paper, extract_key_findings

    try:
        paper = read_paper(request.url)
    except Exception as e:
        log.exception("Failed to read paper")
        raise HTTPException(status_code=400, detail=f"Could not read paper: {e}")

    # Save to memory
    try:
        from cascade.memory import Memory
        with Memory() as mem:
            mem.save_paper(paper.to_paper())
    except Exception:
        pass

    response = {
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "year": paper.year,
        "url": paper.url,
        "source": paper.source,
        "sections": paper.sections,
        "fullTextLength": len(paper.full_text),
    }

    if request.summarize:
        try:
            response["summary"] = summarise_paper(paper)
        except Exception as e:
            log.warning("Summary generation failed: %s", e)

    if request.include_findings:
        try:
            response["findings"] = extract_key_findings(paper)
        except Exception as e:
            log.warning("Key findings extraction failed: %s", e)

    return response


@router.get("/memory")
async def query_memory(
    q: str = Query("", description="Search query (empty = all papers)"),
    limit: int = Query(20, ge=1, le=100),
):
    """Query saved papers from memory."""
    from cascade.memory import Memory

    try:
        with Memory() as mem:
            if q:
                papers = mem.search_papers(q, limit=limit, semantic=True)
            else:
                papers = mem.get_all_papers(limit=limit)
            stats = mem.stats()
    except Exception as e:
        log.exception("Memory query failed")
        raise HTTPException(status_code=500, detail=f"Memory query failed: {e}")

    return {
        "papers": papers,
        "stats": stats,
    }


@router.get("/memory/stats")
async def memory_stats():
    """Return memory statistics."""
    from cascade.memory import Memory

    try:
        with Memory() as mem:
            return mem.stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

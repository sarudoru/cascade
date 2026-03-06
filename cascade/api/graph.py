"""Citation graph API — crawl, retrieve, and manage citation networks."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cascade.graph import CitationGraph, GRAPH_DIR
from cascade.search.semantic_scholar import get_paper_id_from_url

log = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


class CrawlRequest(BaseModel):
    paper: str  # URL, arXiv ID, DOI, or S2 ID
    depth: int = 2
    max_papers: int = 100
    direction: str = "both"  # "both" | "citations" | "references"


class ResumeRequest(BaseModel):
    depth: int | None = None
    max_papers: int = 100
    direction: str | None = None


def _graph_to_json(graph: CitationGraph, graph_id: str | None = None) -> dict:
    """Convert a CitationGraph to a frontend-friendly JSON structure."""
    nodes = []
    for nid, node in graph.nodes.items():
        nodes.append({
            "id": nid,
            "title": node.title,
            "authors": node.authors,
            "year": node.year,
            "citationCount": node.citation_count,
            "abstract": node.abstract,
            "url": node.url,
            "depth": node.depth,
            "label": node.label,
        })

    edges = []
    for src, tgt in graph.edges:
        if src in graph.nodes and tgt in graph.nodes:
            edges.append({"source": src, "target": tgt})

    return {
        "graphId": graph_id,
        "nodes": nodes,
        "edges": edges,
        "stats": graph.stats(),
    }


def _extract_paper_id(paper: str) -> str:
    """Try to resolve a paper identifier to an S2 paper ID."""
    return get_paper_id_from_url(paper)


def _save_graph(graph: CitationGraph) -> str:
    """Save graph and return the persisted graph ID."""
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    save_path = graph.auto_save_path()
    graph.save(save_path)
    return save_path.stem


def _ingest_researchers(graph: CitationGraph) -> None:
    """Best-effort ingestion into researcher graph."""
    try:
        from cascade.researchers import ResearcherDB

        with ResearcherDB() as rdb:
            rdb.ingest_from_graph(graph)
    except Exception:
        pass


@router.post("/crawl")
async def crawl_graph(request: CrawlRequest):
    """Start a citation graph crawl from a seed paper."""
    if request.direction not in {"both", "citations", "references"}:
        raise HTTPException(status_code=400, detail="direction must be one of: both, citations, references")

    try:
        seed_id = _extract_paper_id(request.paper)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not resolve paper: {e}")

    graph = CitationGraph()

    try:
        graph.crawl(
            seed_id=seed_id,
            depth=request.depth,
            max_papers=request.max_papers,
            direction=request.direction,
        )
    except Exception as e:
        log.exception("Graph crawl failed")
        raise HTTPException(status_code=500, detail=f"Crawl failed: {e}")

    graph_id = seed_id[:12]
    try:
        graph_id = _save_graph(graph)
    except Exception as e:
        log.warning("Graph auto-save failed: %s", e)

    _ingest_researchers(graph)
    return _graph_to_json(graph, graph_id=graph_id)


@router.post("/{graph_id}/resume")
async def resume_graph(graph_id: str, request: ResumeRequest):
    """Resume a previously saved crawl from the frontier."""
    path = GRAPH_DIR / f"{graph_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Graph not found")
    if request.direction and request.direction not in {"both", "citations", "references"}:
        raise HTTPException(status_code=400, detail="direction must be one of: both, citations, references")

    try:
        graph = CitationGraph.load(path)
        graph.resume(
            depth=request.depth,
            max_papers=request.max_papers,
            direction=request.direction,
        )
        graph.save(path)
    except Exception as e:
        log.exception("Graph resume failed")
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")

    _ingest_researchers(graph)
    return _graph_to_json(graph, graph_id=graph_id)


@router.get("/list/saved")
async def list_graphs():
    """List all saved graphs."""
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    graphs = []
    for f in sorted(GRAPH_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            graphs.append(
                {
                    "id": f.stem,
                    "nodeCount": len(data.get("nodes", {})),
                    "edgeCount": len(data.get("edges", [])),
                    "seedTitle": next(
                        (n.get("title", "") for n in data.get("nodes", {}).values() if n.get("depth", 99) == 0),
                        f.stem,
                    ),
                }
            )
        except Exception:
            continue
    return graphs


@router.get("/{graph_id}")
async def get_graph(graph_id: str):
    """Retrieve a saved graph by ID."""
    path = GRAPH_DIR / f"{graph_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Graph not found")

    try:
        graph = CitationGraph.load(path)
        return _graph_to_json(graph, graph_id=graph_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load graph: {e}")

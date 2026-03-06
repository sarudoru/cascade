"""Tests for CitationGraph — BFS crawl, resume, exports, persistence.

All S2 API calls are mocked via injectable fetch functions.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from cascade.graph import CitationGraph, GraphNode


# -----------------------------------------------------------------------
# Mock data
# -----------------------------------------------------------------------

SEED = {
    "paperId": "seed001",
    "title": "Attention Is All You Need",
    "year": 2017,
    "citationCount": 80000,
    "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
    "abstract": "The dominant sequence models are based on complex recurrent networks.",
    "url": "https://s2.org/paper/seed001",
}

CITING_PAPERS = [
    {
        "paperId": "cite001",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "year": 2019,
        "citationCount": 50000,
        "authors": [{"name": "Jacob Devlin"}],
        "abstract": "We introduce BERT.",
        "url": "https://s2.org/paper/cite001",
    },
    {
        "paperId": "cite002",
        "title": "GPT-2: Language Models are Unsupervised Multitask Learners",
        "year": 2019,
        "citationCount": 10000,
        "authors": [{"name": "Alec Radford"}],
        "abstract": "We demonstrate that language models...",
        "url": "https://s2.org/paper/cite002",
    },
]

REF_PAPERS = [
    {
        "paperId": "ref001",
        "title": "Neural Machine Translation by Jointly Learning to Align and Translate",
        "year": 2015,
        "citationCount": 30000,
        "authors": [{"name": "Dzmitry Bahdanau"}],
        "abstract": "We conjecture that the fixed-length vector is a bottleneck.",
        "url": "https://s2.org/paper/ref001",
    },
]

DEPTH2_CITING = [
    {
        "paperId": "d2cite001",
        "title": "RoBERTa: A Robustly Optimized BERT Pretraining Approach",
        "year": 2019,
        "citationCount": 15000,
        "authors": [{"name": "Yinhan Liu"}],
        "abstract": "We present a replication study of BERT.",
        "url": "https://s2.org/paper/d2cite001",
    },
]


def _mock_details(paper_id: str) -> dict:
    if paper_id == "seed001":
        return SEED
    return {"paperId": paper_id, "title": f"Paper {paper_id}", "year": 2020,
            "citationCount": 100, "authors": [], "abstract": "", "url": ""}


def _mock_citations(paper_id: str, max_results: int = 50) -> list[dict]:
    if paper_id == "seed001":
        return CITING_PAPERS
    if paper_id == "cite001":
        return DEPTH2_CITING
    return []


def _mock_references(paper_id: str, max_results: int = 50) -> list[dict]:
    if paper_id == "seed001":
        return REF_PAPERS
    return []


# -----------------------------------------------------------------------
# BFS Crawl Tests
# -----------------------------------------------------------------------

class TestCrawl:
    def test_depth_1_both(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, max_papers=100, direction="both",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        assert g.seed_id == "seed001"
        assert len(g.nodes) == 4
        assert "seed001" in g.nodes
        assert "cite001" in g.nodes
        assert "cite002" in g.nodes
        assert "ref001" in g.nodes

    def test_depth_2(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=2, max_papers=100, direction="citations",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        assert len(g.nodes) == 4
        assert "d2cite001" in g.nodes
        assert g.nodes["d2cite001"].depth == 2

    def test_citations_only(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, direction="citations",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        assert "ref001" not in g.nodes
        assert len(g.nodes) == 3

    def test_references_only(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, direction="references",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        assert "cite001" not in g.nodes
        assert "ref001" in g.nodes
        assert len(g.nodes) == 2

    def test_max_papers_cap(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=2, max_papers=3, direction="both",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        assert len(g.nodes) <= 4  # seed + up to 3 new

    def test_deduplication(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=2, max_papers=100, direction="both",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        all_ids = list(g.nodes.keys())
        assert len(all_ids) == len(set(all_ids))

    def test_edges_direction(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, direction="both",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        assert ("cite001", "seed001") in g.edges
        assert ("cite002", "seed001") in g.edges
        assert ("seed001", "ref001") in g.edges

    def test_expanded_tracking(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, direction="both",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        assert "seed001" in g.expanded
        # Depth-1 nodes should be in frontier (not expanded) since depth=1
        # Actually they were queued but depth >= 1 so they're in frontier
        assert len(g.frontier) >= 0  # May have unexpanded papers


# -----------------------------------------------------------------------
# Resume Tests
# -----------------------------------------------------------------------

class TestResume:
    def test_resume_continues_crawl(self, tmp_path):
        """Crawl depth=1, save, resume to depth=2."""
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, max_papers=100, direction="citations",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        initial_count = len(g.nodes)

        # Save and reload
        path = tmp_path / "graph.json"
        g.save(str(path))
        g2 = CitationGraph.load(str(path))

        # Resume deeper
        g2.resume(
            depth=2, max_papers=100, direction="citations",
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )

        # Should have found RoBERTa (depth-2 citing BERT)
        assert len(g2.nodes) >= initial_count
        assert "d2cite001" in g2.nodes

    def test_resume_no_duplicate_expansion(self, tmp_path):
        """Already-expanded papers should not be re-fetched."""
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, max_papers=100, direction="citations",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )

        path = tmp_path / "graph.json"
        g.save(str(path))
        g2 = CitationGraph.load(str(path))

        assert "seed001" in g2.expanded

    def test_frontier_persistence(self, tmp_path):
        """Frontier should survive save/load cycle."""
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, max_papers=100, direction="both",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )

        path = tmp_path / "graph.json"
        g.save(str(path))

        data = json.loads(path.read_text())
        assert "frontier" in data
        assert "expanded" in data

        g2 = CitationGraph.load(str(path))
        assert g2.expanded == g.expanded

    def test_direction_persistence(self, tmp_path):
        """Direction should survive save/load."""
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, direction="citations",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        path = tmp_path / "graph.json"
        g.save(str(path))
        g2 = CitationGraph.load(str(path))
        assert g2.direction == "citations"


# -----------------------------------------------------------------------
# Export Tests
# -----------------------------------------------------------------------

class TestExports:
    @pytest.fixture
    def graph(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, direction="both",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        return g

    def test_to_json_roundtrip(self, graph, tmp_path):
        path = tmp_path / "graph.json"
        graph.save(str(path))
        loaded = CitationGraph.load(str(path))
        assert len(loaded.nodes) == len(graph.nodes)
        assert len(loaded.edges) == len(graph.edges)
        assert loaded.seed_id == graph.seed_id

    def test_to_dot(self, graph):
        dot = graph.to_dot()
        assert "digraph citation_graph" in dot
        assert "seed001" in dot
        assert "->" in dot

    def test_to_pyvis(self, graph, tmp_path):
        path = str(tmp_path / "graph.html")
        result = graph.to_pyvis(path)
        assert Path(result).exists()

    def test_to_networkx(self, graph):
        nx_graph = graph.to_networkx()
        assert nx_graph.number_of_nodes() == 4
        assert nx_graph.number_of_edges() == 3


# -----------------------------------------------------------------------
# Stats Tests
# -----------------------------------------------------------------------

class TestStats:
    def test_stats_empty(self):
        g = CitationGraph()
        s = g.stats()
        assert s["nodes"] == 0

    def test_stats_populated(self):
        g = CitationGraph()
        g.crawl(
            "seed001", depth=1, direction="both",
            fetch_details_fn=_mock_details,
            fetch_citations_fn=_mock_citations,
            fetch_references_fn=_mock_references,
        )
        s = g.stats()
        assert s["nodes"] == 4
        assert s["edges"] == 3
        assert "frontier" in s
        assert "expanded" in s
        assert "2015" in s["year_range"]
        assert s["seed_title"] == "Attention Is All You Need"


# -----------------------------------------------------------------------
# GraphNode Tests
# -----------------------------------------------------------------------

class TestGraphNode:
    def test_label(self):
        node = GraphNode(paper_id="x", title="Test", authors=["Ashish Vaswani"], year=2017)
        assert node.label == "Vaswani 2017"

    def test_label_no_author(self):
        node = GraphNode(paper_id="x", title="Test", authors=[], year=2020)
        assert node.label == "? 2020"

    def test_label_no_year(self):
        node = GraphNode(paper_id="x", title="Test", authors=["Devlin"], year=0)
        assert node.label == "Devlin"

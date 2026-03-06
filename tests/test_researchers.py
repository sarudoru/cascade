"""Tests for ResearcherDB — co-authorship network."""

from __future__ import annotations

import pytest
from cascade.researchers import ResearcherDB
from cascade.graph import CitationGraph, GraphNode


@pytest.fixture
def rdb(tmp_path):
    """Create a ResearcherDB with a temp database."""
    db = tmp_path / "test.db"
    return ResearcherDB(db_path=db)


@pytest.fixture
def graph_with_authors():
    """Create a CitationGraph with known author data."""
    g = CitationGraph()
    g.seed_id = "p1"
    g.nodes = {
        "p1": GraphNode(
            paper_id="p1", title="Attention Is All You Need", year=2017,
            citation_count=80000, authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        ),
        "p2": GraphNode(
            paper_id="p2", title="BERT", year=2019,
            citation_count=50000, authors=["Jacob Devlin", "Ashish Vaswani"],
        ),
        "p3": GraphNode(
            paper_id="p3", title="GPT-2", year=2019,
            citation_count=10000, authors=["Alec Radford"],
        ),
    }
    return g


class TestIngest:
    def test_ingest_creates_researchers(self, rdb, graph_with_authors):
        rdb.ingest_from_graph(graph_with_authors)
        s = rdb.stats()
        assert s["researchers"] == 5  # Vaswani, Shazeer, Parmar, Devlin, Radford
        assert s["papers_linked"] == 3

    def test_ingest_coauthorship(self, rdb, graph_with_authors):
        rdb.ingest_from_graph(graph_with_authors)
        coauthors = rdb.get_coauthors("Ashish Vaswani")
        names = [c["name"] for c in coauthors]
        assert "Noam Shazeer" in names
        assert "Niki Parmar" in names
        assert "Jacob Devlin" in names

    def test_ingest_idempotent(self, rdb, graph_with_authors):
        rdb.ingest_from_graph(graph_with_authors)
        rdb.ingest_from_graph(graph_with_authors)
        s = rdb.stats()
        assert s["researchers"] == 5  # No duplicates


class TestQueries:
    def test_get_researcher(self, rdb, graph_with_authors):
        rdb.ingest_from_graph(graph_with_authors)
        r = rdb.get_researcher("Ashish Vaswani")
        assert r is not None
        assert r["name"] == "Ashish Vaswani"
        assert len(r["papers"]) == 2  # p1 and p2

    def test_get_nonexistent(self, rdb):
        assert rdb.get_researcher("Nobody") is None

    def test_search(self, rdb, graph_with_authors):
        rdb.ingest_from_graph(graph_with_authors)
        results = rdb.search_researchers("Vaswani")
        assert len(results) == 1
        assert results[0]["name"] == "Ashish Vaswani"

    def test_top_researchers(self, rdb, graph_with_authors):
        rdb.ingest_from_graph(graph_with_authors)
        top = rdb.top_researchers(limit=3)
        assert len(top) == 3
        # Vaswani has 2 papers, should be first
        assert top[0]["name"] == "Ashish Vaswani"


class TestStats:
    def test_empty(self, rdb):
        s = rdb.stats()
        assert s["researchers"] == 0
        assert s["coauthor_pairs"] == 0

    def test_populated(self, rdb, graph_with_authors):
        rdb.ingest_from_graph(graph_with_authors)
        s = rdb.stats()
        assert s["researchers"] == 5
        assert s["coauthor_pairs"] > 0

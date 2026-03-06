"""Tests for semantic.py — ChromaDB vector search.

Uses ChromaDB's default (non-OpenAI) embedding function to avoid API calls.
"""

from __future__ import annotations

import pytest
from cascade.search.arxiv_search import Paper


@pytest.fixture
def semantic_memory(tmp_path, monkeypatch):
    """Create a SemanticMemory backed by a temp dir with mock embeddings.

    Uses ChromaDB's built-in default embedder (no OpenAI API needed).
    Each test gets unique collection names for isolation.
    """
    import uuid
    import chromadb
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    # Patch get_settings to provide fake keys and temp path
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    client = chromadb.Client()  # In-memory, no persistence
    ef = DefaultEmbeddingFunction()

    # Unique names to avoid cross-test contamination
    suffix = uuid.uuid4().hex[:8]
    papers_col = client.get_or_create_collection(
        name=f"papers_{suffix}", embedding_function=ef, metadata={"hnsw:space": "cosine"}
    )
    insights_col = client.get_or_create_collection(
        name=f"insights_{suffix}", embedding_function=ef, metadata={"hnsw:space": "cosine"}
    )

    # Build a lightweight SemanticMemory-like object by monkey-patching
    from cascade.semantic import SemanticMemory

    sem = object.__new__(SemanticMemory)
    sem._client = client
    sem._papers = papers_col
    sem._insights = insights_col
    sem._ef = ef
    sem._model = "default"
    sem._persist_path = tmp_path

    return sem


class TestEmbedAndSearch:
    """Tests for paper embed + search round-trip."""

    def test_embed_and_search_paper(self, semantic_memory):
        p = Paper(
            title="Attention Is All You Need",
            authors=["Vaswani", "Shazeer"],
            abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
            url="https://arxiv.org/abs/1706.03762",
            year=2017,
            source="arxiv",
        )
        semantic_memory.embed_paper(p)
        results = semantic_memory.search("attention mechanism transformer", n_results=5)
        assert len(results) == 1
        assert results[0]["title"] == "Attention Is All You Need"

    def test_search_empty_collection(self, semantic_memory):
        results = semantic_memory.search("anything")
        assert results == []

    def test_embed_multiple_papers(self, semantic_memory):
        papers = [
            Paper(
                title="BERT: Pre-training of Deep Bidirectional Transformers",
                authors=["Devlin"],
                abstract="We introduce BERT for language understanding.",
                url="https://arxiv.org/abs/1810.04805",
                year=2018,
                source="arxiv",
            ),
            Paper(
                title="MotionDiffuse: Text-Driven Human Motion Generation",
                authors=["Zhang"],
                abstract="Text-driven human motion generation with diffusion model.",
                url="https://arxiv.org/abs/2208.15001",
                year=2022,
                source="arxiv",
            ),
        ]
        count = semantic_memory.embed_papers(papers)
        assert count == 2
        assert semantic_memory.stats()["papers"] == 2

    def test_upsert_deduplicates(self, semantic_memory):
        p = Paper(
            title="Test Paper",
            authors=["Author"],
            abstract="Abstract text here.",
            url="https://example.com/paper1",
            year=2024,
            source="test",
        )
        semantic_memory.embed_paper(p)
        semantic_memory.embed_paper(p)  # Same URL
        assert semantic_memory.stats()["papers"] == 1


class TestInsights:
    """Tests for insight embedding and search."""

    def test_embed_and_search_insight(self, semantic_memory):
        semantic_memory.embed_insight("transformers", "Attention mechanisms revolutionized NLP.")
        results = semantic_memory.search_insights("attention NLP")
        assert len(results) == 1
        assert "attention" in results[0]["insight_text"].lower()

    def test_search_empty_insights(self, semantic_memory):
        results = semantic_memory.search_insights("anything")
        assert results == []


class TestBuildContext:
    """Tests for semantic context building."""

    def test_build_semantic_context(self, semantic_memory):
        p = Paper(
            title="Sparse Autoencoders for Interpretability",
            authors=["Bricken"],
            abstract="We study sparse autoencoders as a tool for mechanistic interpretability.",
            url="https://example.com/sae",
            year=2023,
            source="arxiv",
        )
        semantic_memory.embed_paper(p)
        semantic_memory.embed_insight("interp", "SAEs help decompose features.")

        ctx = semantic_memory.build_semantic_context("mechanistic interpretability")
        assert "Sparse Autoencoders" in ctx
        assert "Semantically Relevant" in ctx

    def test_build_context_empty(self, semantic_memory):
        ctx = semantic_memory.build_semantic_context("nothing here")
        assert ctx == ""


class TestStats:
    """Tests for stats reporting."""

    def test_stats_empty(self, semantic_memory):
        s = semantic_memory.stats()
        assert s == {"papers": 0, "insights": 0}

    def test_stats_after_embed(self, semantic_memory):
        p = Paper(
            title="Test", authors=["A"], abstract="B",
            url="https://example.com/1", year=2024, source="test",
        )
        semantic_memory.embed_paper(p)
        semantic_memory.embed_insight("topic", "insight text")
        s = semantic_memory.stats()
        assert s["papers"] == 1
        assert s["insights"] == 1

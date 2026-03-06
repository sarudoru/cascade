"""Tests for the Memory class (SQLite persistence)."""

from __future__ import annotations

import pytest
from cascade.memory import Memory
from cascade.search.arxiv_search import Paper


class TestMemoryContextManager:
    """Tests for context manager support."""

    def test_context_manager(self, tmp_db):
        with Memory(db_path=tmp_db) as mem:
            assert mem.count_papers() == 0
        # Connection should be closed — verify by trying to use it
        # (this is a best-effort check)
        assert tmp_db.exists()

    def test_close_called(self, tmp_db):
        mem = Memory(db_path=tmp_db)
        mem.close()
        # Should not raise even if called twice
        mem.close()


class TestMemorySavePaper:
    """Tests for paper persistence."""

    def test_save_and_count(self, tmp_db, sample_paper):
        with Memory(db_path=tmp_db) as mem:
            mem.save_paper(sample_paper)
            assert mem.count_papers() == 1

    def test_save_duplicate(self, tmp_db, sample_paper):
        with Memory(db_path=tmp_db) as mem:
            mem.save_paper(sample_paper)
            mem.save_paper(sample_paper)  # Same URL — should be ignored
            assert mem.count_papers() == 1

    def test_save_papers_batch(self, tmp_db, sample_papers):
        with Memory(db_path=tmp_db) as mem:
            added = mem.save_papers(sample_papers)
            assert added == 3
            assert mem.count_papers() == 3


class TestMemorySearch:
    """Tests for paper search."""

    def test_search_by_title(self, tmp_db, sample_papers):
        with Memory(db_path=tmp_db) as mem:
            mem.save_papers(sample_papers)
            results = mem.search_papers("Attention")
            assert len(results) == 1
            assert results[0]["title"] == "Attention Is All You Need"

    def test_search_by_abstract(self, tmp_db, sample_papers):
        with Memory(db_path=tmp_db) as mem:
            mem.save_papers(sample_papers)
            results = mem.search_papers("Transformer")
            assert len(results) >= 1


class TestMemoryInsights:
    """Tests for insight storage."""

    def test_save_and_retrieve_insight(self, tmp_db):
        with Memory(db_path=tmp_db) as mem:
            mem.save_insight("transformers", "Key finding about attention.", ["Paper A"])
            insights = mem.get_insights("transformers")
            assert len(insights) == 1
            assert "attention" in insights[0]["insight_text"]


class TestMemoryStats:
    """Tests for stats reporting."""

    def test_stats_empty(self, tmp_db):
        with Memory(db_path=tmp_db) as mem:
            s = mem.stats()
            assert s == {"papers": 0, "sessions": 0, "insights": 0}

    def test_stats_with_data(self, tmp_db, sample_paper):
        with Memory(db_path=tmp_db) as mem:
            mem.save_paper(sample_paper)
            mem.log_session("search", "test", "test result")
            mem.save_insight("topic", "insight text")
            s = mem.stats()
            assert s["papers"] == 1
            assert s["sessions"] == 1
            assert s["insights"] == 1

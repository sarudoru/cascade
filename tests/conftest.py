"""Shared test fixtures for Cascade tests."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cascade.search.arxiv_search import Paper


# ---------------------------------------------------------------------------
# Environment — ensure tests never hit real APIs by default
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Set placeholder API keys so Settings doesn't error, but we mock calls."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-anthropic")


# ---------------------------------------------------------------------------
# Temporary directories
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir(tmp_path):
    """Return a fresh temporary directory Path."""
    return tmp_path


@pytest.fixture
def tmp_db(tmp_path):
    """Return a path for a temporary SQLite database."""
    return tmp_path / "test_memory.db"


@pytest.fixture
def tmp_vault(tmp_path):
    """Return a temporary Obsidian vault directory."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_paper():
    """Return a minimal Paper object for testing."""
    return Paper(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        abstract="We propose a new simple network architecture, the Transformer, based solely on attention mechanisms.",
        url="https://arxiv.org/abs/1706.03762",
        year=2017,
        source="arxiv",
        categories=["cs.CL", "cs.LG"],
        citation_count=90000,
        arxiv_id="1706.03762",
        doi="10.48550/arXiv.1706.03762",
        pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
    )


@pytest.fixture
def sample_papers(sample_paper):
    """Return a list of sample Paper objects."""
    return [
        sample_paper,
        Paper(
            title="BERT: Pre-training of Deep Bidirectional Transformers",
            authors=["Jacob Devlin", "Ming-Wei Chang"],
            abstract="We introduce BERT, a new language representation model.",
            url="https://arxiv.org/abs/1810.04805",
            year=2018,
            source="arxiv",
            categories=["cs.CL"],
            citation_count=70000,
            arxiv_id="1810.04805",
        ),
        Paper(
            title="GPT-4 Technical Report",
            authors=["OpenAI"],
            abstract="We report the development of GPT-4, a large-scale multimodal model.",
            url="https://arxiv.org/abs/2303.08774",
            year=2023,
            source="arxiv",
            categories=["cs.CL", "cs.AI"],
            citation_count=5000,
            arxiv_id="2303.08774",
        ),
    ]


@pytest.fixture
def sample_paper_dict():
    """Return a paper as a dict (mimicking Memory.search_papers output)."""
    return {
        "title": "Attention Is All You Need",
        "authors": '["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]',
        "abstract": "We propose a new simple network architecture.",
        "url": "https://arxiv.org/abs/1706.03762",
        "year": 2017,
        "source": "arxiv",
        "citations": 90000,
        "arxiv_id": "1706.03762",
        "doi": "10.48550/arXiv.1706.03762",
    }

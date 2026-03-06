"""Tests for OpenAlex search module — response parsing only (no network)."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from cascade.search.openalex_search import _parse_work, _reconstruct_abstract


class TestParseWork:
    def test_basic_work(self):
        work = {
            "title": "Attention Is All You Need",
            "publication_year": 2017,
            "authorships": [
                {"author": {"display_name": "Vaswani"}},
                {"author": {"display_name": "Shazeer"}},
            ],
            "cited_by_count": 80000,
            "ids": {"doi": "https://doi.org/10.5555/3295222"},
            "doi": "https://doi.org/10.5555/3295222",
            "concepts": [{"display_name": "NLP"}, {"display_name": "Deep Learning"}],
            "open_access": {"oa_url": "https://arxiv.org/pdf/1706.03762"},
            "id": "https://openalex.org/W123",
        }
        paper = _parse_work(work)
        assert paper is not None
        assert paper.title == "Attention Is All You Need"
        assert paper.year == 2017
        assert len(paper.authors) == 2
        assert paper.citation_count == 80000
        assert paper.doi == "10.5555/3295222"
        assert paper.source == "openalex"

    def test_missing_title(self):
        assert _parse_work({"title": None}) is None
        assert _parse_work({}) is None


class TestReconstructAbstract:
    def test_basic(self):
        index = {"Hello": [0], "world": [1], "of": [2], "AI": [3]}
        assert _reconstruct_abstract(index) == "Hello world of AI"

    def test_empty(self):
        assert _reconstruct_abstract(None) == ""
        assert _reconstruct_abstract({}) == ""

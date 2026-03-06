"""Tests for DBLP search module — response parsing only (no network)."""

from __future__ import annotations

import pytest
from cascade.search.dblp_search import _parse_hit


class TestParseHit:
    def test_basic_hit(self):
        hit = {
            "info": {
                "title": "BERT: Pre-training of Deep Bidirectional Transformers.",
                "authors": {
                    "author": [
                        {"text": "Jacob Devlin"},
                        {"text": "Ming-Wei Chang"},
                    ]
                },
                "year": "2019",
                "venue": "NAACL-HLT",
                "ee": "https://arxiv.org/abs/1810.04805",
                "doi": "10.18653/v1/N19-1423",
                "type": "Conference",
            }
        }
        paper = _parse_hit(hit)
        assert paper is not None
        assert paper.title == "BERT: Pre-training of Deep Bidirectional Transformers"  # trailing dot stripped
        assert paper.year == 2019
        assert len(paper.authors) == 2
        assert paper.source == "dblp"
        assert "NAACL-HLT" in paper.categories

    def test_single_author_string(self):
        hit = {"info": {"title": "Test", "authors": {"author": "Solo Author"}, "year": "2024"}}
        paper = _parse_hit(hit)
        assert paper is not None
        assert paper.authors == ["Solo Author"]

    def test_single_author_dict(self):
        hit = {"info": {"title": "Test", "authors": {"author": {"text": "Dict Author"}}, "year": "2024"}}
        paper = _parse_hit(hit)
        assert paper is not None
        assert paper.authors == ["Dict Author"]

    def test_missing_title(self):
        assert _parse_hit({"info": {}}) is None
        assert _parse_hit({"info": {"title": ""}}) is None

    def test_url_list(self):
        hit = {"info": {"title": "Test", "ee": ["https://a.com", "https://b.com"], "year": "2024"}}
        paper = _parse_hit(hit)
        assert paper.url == "https://a.com"

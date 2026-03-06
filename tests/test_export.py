"""Tests for export.py — BibTeX generation."""

from __future__ import annotations

from cascade.export import paper_to_bibtex, papers_to_bibtex


class TestBibTeX:
    """Tests for BibTeX entry generation."""

    def test_single_entry(self, sample_paper_dict):
        bib = paper_to_bibtex(sample_paper_dict)
        assert "@article{vaswani2017," in bib
        assert "title = {Attention Is All You Need}" in bib
        assert "year = {2017}" in bib

    def test_latex_escaping(self):
        paper = {
            "title": "10% Better & Faster",
            "authors": '["Jane O\'Brien"]',
            "year": 2024,
            "url": "https://example.com",
        }
        bib = paper_to_bibtex(paper)
        assert "10\\% Better \\& Faster" in bib

    def test_multiple_entries(self, sample_paper_dict):
        papers = [sample_paper_dict, dict(sample_paper_dict)]
        bib = papers_to_bibtex(papers)
        # Should have two entries with deduplicated keys
        assert bib.count("@article{") == 2

    def test_arxiv_fields(self, sample_paper_dict):
        bib = paper_to_bibtex(sample_paper_dict)
        assert "eprint = {1706.03762}" in bib
        assert "archiveprefix = {arXiv}" in bib

    def test_doi_field(self, sample_paper_dict):
        bib = paper_to_bibtex(sample_paper_dict)
        assert "doi = {10.48550/arXiv.1706.03762}" in bib

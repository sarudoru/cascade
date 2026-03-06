"""Tests for the Paper dataclass."""

from cascade.search.arxiv_search import Paper


def test_paper_author_str_short():
    p = Paper(
        title="Test",
        authors=["Alice", "Bob"],
        abstract="",
        url="https://example.com",
        year=2024,
        source="test",
    )
    assert p.author_str == "Alice, Bob"


def test_paper_author_str_long():
    p = Paper(
        title="Test",
        authors=["Alice", "Bob", "Charlie", "Dave"],
        abstract="",
        url="https://example.com",
        year=2024,
        source="test",
    )
    assert p.author_str == "Alice et al."


def test_paper_bib_key():
    p = Paper(
        title="Test",
        authors=["Ashish Vaswani"],
        abstract="",
        url="https://example.com",
        year=2017,
        source="test",
    )
    assert p.bib_key == "vaswani2017"


def test_paper_bib_key_unknown():
    p = Paper(
        title="Test",
        authors=[],
        abstract="",
        url="https://example.com",
        year=2024,
        source="test",
    )
    assert p.bib_key == "unknown2024"

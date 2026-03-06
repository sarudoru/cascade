"""Tests for tokens.py — token counting and budget management."""

from __future__ import annotations

from cascade.tokens import count_tokens, truncate_to_budget, build_budgeted_context, get_context_limit


class TestCountTokens:
    """Tests for token counting."""

    def test_count_returns_positive(self):
        tokens = count_tokens("Hello, world!")
        assert tokens > 0

    def test_empty_string(self):
        tokens = count_tokens("")
        assert tokens == 0

    def test_longer_text_more_tokens(self):
        short = count_tokens("Hello")
        long = count_tokens("Hello " * 100)
        assert long > short


class TestTruncateToBudget:
    """Tests for intelligent truncation."""

    def test_no_truncation_when_within_budget(self):
        text = "Short text"
        result = truncate_to_budget(text, max_tokens=1000)
        assert result == text

    def test_truncation_when_over_budget(self):
        text = "word " * 5000  # Very long
        result = truncate_to_budget(text, max_tokens=100)
        assert len(result) < len(text)
        assert "[... truncated" in result

    def test_preserves_paragraph_boundary(self):
        text = "First paragraph.\n\nSecond paragraph.\n\n" + "word " * 5000
        result = truncate_to_budget(text, max_tokens=50)
        assert "[... truncated" in result


class TestGetContextLimit:
    """Tests for model context limits."""

    def test_known_model(self):
        limit = get_context_limit("gpt-4")
        assert limit > 0

    def test_unknown_model_returns_default(self):
        limit = get_context_limit("some-unknown-model")
        assert limit > 0


class TestBuildBudgetedContext:
    """Tests for budgeted context building."""

    def test_builds_context(self, sample_paper_dict):
        ctx = build_budgeted_context([sample_paper_dict])
        assert "Attention Is All You Need" in ctx
        assert "## Relevant Papers" in ctx

    def test_empty_papers(self):
        ctx = build_budgeted_context([])
        assert "## Relevant Papers" in ctx

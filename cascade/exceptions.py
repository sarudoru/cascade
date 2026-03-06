"""Cascade exception hierarchy.

All Cascade-specific errors inherit from ``CascadeError`` so callers can
catch a single base class when needed.
"""

from __future__ import annotations


class CascadeError(Exception):
    """Base exception for all Cascade errors."""


class SearchError(CascadeError):
    """Raised when a search-backend API call fails."""


class LLMError(CascadeError):
    """Raised when an LLM API call fails."""


class MemoryError(CascadeError):
    """Raised when SQLite / persistence operations fail."""


class ReaderError(CascadeError):
    """Raised when paper fetching or PDF parsing fails."""


class ConfigError(CascadeError):
    """Raised for missing API keys or invalid configuration."""

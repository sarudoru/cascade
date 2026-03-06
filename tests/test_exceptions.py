"""Tests for exceptions.py — exception hierarchy."""

from cascade.exceptions import (
    CascadeError,
    SearchError,
    LLMError,
    MemoryError,
    ReaderError,
    ConfigError,
)


def test_all_inherit_from_cascade_error():
    """All custom exceptions should be children of CascadeError."""
    for exc_cls in (SearchError, LLMError, MemoryError, ReaderError, ConfigError):
        assert issubclass(exc_cls, CascadeError)


def test_cascade_error_inherits_exception():
    assert issubclass(CascadeError, Exception)


def test_can_raise_and_catch():
    """Verify we can raise specific errors and catch by base class."""
    with __import__("pytest").raises(CascadeError):
        raise SearchError("test")

    with __import__("pytest").raises(CascadeError):
        raise LLMError("test")

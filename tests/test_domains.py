"""Tests for domains.py — YAML-based domain management."""

from __future__ import annotations

import pytest
from cascade.domains import load_domains, save_domains, add_domain, remove_domain, list_domains


class TestLoadDomains:
    """Tests for loading domain configurations."""

    def test_load_defaults_when_no_file(self, tmp_path):
        path = tmp_path / "domains.yaml"
        domains = load_domains(path)
        assert "cv-motion" in domains
        assert "nlp-interp" in domains
        # Should have been written to disk
        assert path.exists()

    def test_load_from_existing_file(self, tmp_path):
        path = tmp_path / "domains.yaml"
        save_domains({"custom": {"name": "Custom Domain", "keywords": ["test"]}}, path)
        domains = load_domains(path)
        assert "custom" in domains
        assert domains["custom"]["name"] == "Custom Domain"


class TestSaveDomains:
    """Tests for saving domain configurations."""

    def test_save_creates_file(self, tmp_path):
        path = tmp_path / "sub" / "domains.yaml"
        save_domains({"test": {"name": "Test"}}, path)
        assert path.exists()

    def test_roundtrip(self, tmp_path):
        path = tmp_path / "domains.yaml"
        original = {
            "my-domain": {
                "name": "My Domain",
                "keywords": ["keyword1", "keyword2"],
                "arxiv_categories": ["cs.AI"],
                "tags": ["#research/custom"],
            }
        }
        save_domains(original, path)
        loaded = load_domains(path)
        assert loaded["my-domain"]["keywords"] == ["keyword1", "keyword2"]


class TestCRUDOperations:
    """Tests for add/remove/list operations."""

    def test_add_domain(self, tmp_path):
        path = tmp_path / "domains.yaml"
        add_domain("new-domain", "New Domain", ["kw1", "kw2"], path=path)
        domains = load_domains(path)
        assert "new-domain" in domains
        assert domains["new-domain"]["keywords"] == ["kw1", "kw2"]

    def test_remove_domain(self, tmp_path):
        path = tmp_path / "domains.yaml"
        add_domain("temp", "Temp", ["kw"], path=path)
        assert remove_domain("temp", path=path)
        domains = load_domains(path)
        assert "temp" not in domains

    def test_remove_nonexistent(self, tmp_path):
        path = tmp_path / "domains.yaml"
        save_domains({}, path)
        assert not remove_domain("nonexistent", path=path)

    def test_list_domains(self, tmp_path):
        path = tmp_path / "domains.yaml"
        domains = list_domains(path)
        # Should get defaults on first call
        assert isinstance(domains, dict)
        assert len(domains) >= 2

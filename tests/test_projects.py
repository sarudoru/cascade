"""Tests for ProjectManager CRUD operations."""

from __future__ import annotations

import pytest
from cascade.projects import ProjectManager


@pytest.fixture
def pm(tmp_path):
    """Create a ProjectManager with a temp database."""
    db = tmp_path / "test.db"
    return ProjectManager(db_path=db)


class TestProjectCRUD:
    def test_create_and_list(self, pm):
        pid = pm.create_project("test-proj", "A test")
        assert pid >= 1
        projects = pm.list_projects()
        assert len(projects) == 1
        assert projects[0]["name"] == "test-proj"

    def test_switch_project(self, pm):
        pm.create_project("proj-a")
        pm.create_project("proj-b")
        assert pm.switch_project("proj-a")
        active = pm.get_active_project()
        assert active is not None
        assert active["name"] == "proj-a"

        # Switch again
        pm.switch_project("proj-b")
        active = pm.get_active_project()
        assert active["name"] == "proj-b"

    def test_switch_nonexistent(self, pm):
        assert pm.switch_project("nope") is False

    def test_delete_project(self, pm):
        pm.create_project("to-delete")
        assert pm.delete_project("to-delete")
        assert pm.list_projects() == []

    def test_delete_nonexistent(self, pm):
        assert pm.delete_project("nope") is False


class TestTags:
    def test_tag_and_get(self, pm):
        pm.tag_paper("http://example.com/paper1", "important")
        pm.tag_paper("http://example.com/paper1", "to-read")
        tags = pm.get_tags("http://example.com/paper1")
        assert "important" in tags
        assert "to-read" in tags

    def test_untag(self, pm):
        pm.tag_paper("http://example.com/p", "remove-me")
        pm.untag_paper("http://example.com/p", "remove-me")
        assert pm.get_tags("http://example.com/p") == []

    def test_get_papers_by_tag(self, pm):
        pm.tag_paper("http://a.com", "ml")
        pm.tag_paper("http://b.com", "ml")
        papers = pm.get_papers_by_tag("ml")
        assert len(papers) == 2

    def test_all_tags(self, pm):
        pm.tag_paper("http://a.com", "ml")
        pm.tag_paper("http://b.com", "ml")
        pm.tag_paper("http://a.com", "nlp")
        tags = pm.get_all_tags()
        assert tags[0]["tag"] == "ml"
        assert tags[0]["count"] == 2


class TestAnnotations:
    def test_annotate_and_get(self, pm):
        aid = pm.annotate_paper("http://example.com/p", "Great paper on transformers")
        assert aid >= 1
        notes = pm.get_annotations("http://example.com/p")
        assert len(notes) == 1
        assert "transformers" in notes[0]["note"]

    def test_multiple_annotations(self, pm):
        pm.annotate_paper("http://example.com/p", "Note 1")
        pm.annotate_paper("http://example.com/p", "Note 2")
        notes = pm.get_annotations("http://example.com/p")
        assert len(notes) == 2


class TestReadingLists:
    def test_create_and_list(self, pm):
        rl_id = pm.create_reading_list("survey-papers", "Papers to survey")
        assert rl_id >= 1
        lists = pm.list_reading_lists()
        assert len(lists) == 1
        assert lists[0]["name"] == "survey-papers"

    def test_add_and_get_items(self, pm):
        pm.create_reading_list("my-list")
        pm.add_to_reading_list("my-list", "http://paper.com/1", priority=5)
        pm.add_to_reading_list("my-list", "http://paper.com/2", priority=3)
        items = pm.get_reading_list_items("my-list")
        assert len(items) == 2

    def test_update_status(self, pm):
        pm.create_reading_list("reading")
        pm.add_to_reading_list("reading", "http://paper.com/1")
        assert pm.update_reading_status("reading", "http://paper.com/1", "done")


class TestStats:
    def test_stats_empty(self, pm):
        s = pm.stats()
        assert s["projects"] == 0
        assert s["tags"] == 0

    def test_stats_populated(self, pm):
        pm.create_project("p1")
        pm.tag_paper("http://a.com", "ml")
        pm.annotate_paper("http://a.com", "note")
        s = pm.stats()
        assert s["projects"] == 1
        assert s["tags"] == 1
        assert s["annotations"] == 1

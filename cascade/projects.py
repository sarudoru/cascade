"""Project & collection management for Cascade.

Provides project scoping, paper tagging, annotations, and reading lists.
All data stored in the same SQLite database used by Memory.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from cascade.config import get_settings

log = logging.getLogger(__name__)


class ProjectManager:
    """Manage research projects, tags, annotations, and reading lists."""

    def __init__(self, db_path: Path | None = None):
        s = get_settings()
        self._db_path = db_path or s.db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def __enter__(self) -> "ProjectManager":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                active      INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_papers (
                project_id  INTEGER NOT NULL,
                paper_url   TEXT NOT NULL,
                added_at    TEXT NOT NULL,
                PRIMARY KEY (project_id, paper_url)
            );

            CREATE TABLE IF NOT EXISTS paper_tags (
                paper_url   TEXT NOT NULL,
                tag         TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (paper_url, tag)
            );

            CREATE TABLE IF NOT EXISTS paper_annotations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_url   TEXT NOT NULL,
                note        TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reading_lists (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reading_list_items (
                list_id     INTEGER NOT NULL,
                paper_url   TEXT NOT NULL,
                status      TEXT DEFAULT 'unread',
                priority    INTEGER DEFAULT 0,
                notes       TEXT DEFAULT '',
                added_at    TEXT NOT NULL,
                PRIMARY KEY (list_id, paper_url)
            );

            CREATE INDEX IF NOT EXISTS idx_tags_paper ON paper_tags(paper_url);
            CREATE INDEX IF NOT EXISTS idx_annotations_paper ON paper_annotations(paper_url);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def create_project(self, name: str, description: str = "") -> int:
        """Create a new project. Returns its ID."""
        cur = self._conn.execute(
            "INSERT INTO projects (name, description, created_at) VALUES (?, ?, ?)",
            (name, description, datetime.now().isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def list_projects(self) -> list[dict]:
        cur = self._conn.execute("SELECT * FROM projects ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def get_active_project(self) -> dict | None:
        cur = self._conn.execute("SELECT * FROM projects WHERE active = 1 LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None

    def switch_project(self, name: str) -> bool:
        """Set *name* as the active project. Returns False if not found."""
        cur = self._conn.execute("SELECT id FROM projects WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return False
        self._conn.execute("UPDATE projects SET active = 0")
        self._conn.execute("UPDATE projects SET active = 1 WHERE id = ?", (row["id"],))
        self._conn.commit()
        return True

    def delete_project(self, name: str) -> bool:
        cur = self._conn.execute("SELECT id FROM projects WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return False
        pid = row["id"]
        self._conn.execute("DELETE FROM project_papers WHERE project_id = ?", (pid,))
        self._conn.execute("DELETE FROM reading_lists WHERE project_id = ?", (pid,))
        self._conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
        self._conn.commit()
        return True

    def add_paper_to_project(self, project_name: str, paper_url: str) -> bool:
        proj = self._get_project_by_name(project_name)
        if not proj:
            return False
        self._conn.execute(
            "INSERT OR IGNORE INTO project_papers (project_id, paper_url, added_at) VALUES (?, ?, ?)",
            (proj["id"], paper_url, datetime.now().isoformat()),
        )
        self._conn.commit()
        return True

    def get_project_papers(self, project_name: str) -> list[str]:
        proj = self._get_project_by_name(project_name)
        if not proj:
            return []
        cur = self._conn.execute(
            "SELECT paper_url FROM project_papers WHERE project_id = ? ORDER BY added_at DESC",
            (proj["id"],),
        )
        return [r["paper_url"] for r in cur.fetchall()]

    def _get_project_by_name(self, name: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM projects WHERE name = ?", (name,))
        row = cur.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def tag_paper(self, paper_url: str, tag: str) -> None:
        """Add a tag to a paper."""
        self._conn.execute(
            "INSERT OR IGNORE INTO paper_tags (paper_url, tag, created_at) VALUES (?, ?, ?)",
            (paper_url, tag, datetime.now().isoformat()),
        )
        self._conn.commit()

    def untag_paper(self, paper_url: str, tag: str) -> None:
        self._conn.execute(
            "DELETE FROM paper_tags WHERE paper_url = ? AND tag = ?",
            (paper_url, tag),
        )
        self._conn.commit()

    def get_tags(self, paper_url: str) -> list[str]:
        cur = self._conn.execute(
            "SELECT tag FROM paper_tags WHERE paper_url = ? ORDER BY tag",
            (paper_url,),
        )
        return [r["tag"] for r in cur.fetchall()]

    def get_papers_by_tag(self, tag: str) -> list[str]:
        cur = self._conn.execute(
            "SELECT paper_url FROM paper_tags WHERE tag = ?",
            (tag,),
        )
        return [r["paper_url"] for r in cur.fetchall()]

    def get_all_tags(self) -> list[dict]:
        """Return all tags with their counts."""
        cur = self._conn.execute(
            "SELECT tag, COUNT(*) as count FROM paper_tags GROUP BY tag ORDER BY count DESC"
        )
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Annotations
    # ------------------------------------------------------------------

    def annotate_paper(self, paper_url: str, note: str) -> int:
        """Add an annotation to a paper. Returns annotation ID."""
        cur = self._conn.execute(
            "INSERT INTO paper_annotations (paper_url, note, created_at) VALUES (?, ?, ?)",
            (paper_url, note, datetime.now().isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_annotations(self, paper_url: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM paper_annotations WHERE paper_url = ? ORDER BY created_at DESC",
            (paper_url,),
        )
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Reading Lists
    # ------------------------------------------------------------------

    def create_reading_list(
        self, name: str, description: str = "", project_name: str | None = None
    ) -> int:
        """Create a reading list, optionally scoped to a project."""
        project_id = None
        if project_name:
            proj = self._get_project_by_name(project_name)
            if proj:
                project_id = proj["id"]

        cur = self._conn.execute(
            "INSERT INTO reading_lists (project_id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (project_id, name, description, datetime.now().isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def list_reading_lists(self, project_name: str | None = None) -> list[dict]:
        if project_name:
            proj = self._get_project_by_name(project_name)
            if proj:
                cur = self._conn.execute(
                    "SELECT * FROM reading_lists WHERE project_id = ? ORDER BY created_at DESC",
                    (proj["id"],),
                )
                return [dict(r) for r in cur.fetchall()]
        cur = self._conn.execute("SELECT * FROM reading_lists ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]

    def add_to_reading_list(
        self, list_name: str, paper_url: str, priority: int = 0, notes: str = ""
    ) -> bool:
        rl = self._get_reading_list_by_name(list_name)
        if not rl:
            return False
        self._conn.execute(
            """INSERT OR REPLACE INTO reading_list_items
               (list_id, paper_url, status, priority, notes, added_at)
               VALUES (?, ?, 'unread', ?, ?, ?)""",
            (rl["id"], paper_url, priority, notes, datetime.now().isoformat()),
        )
        self._conn.commit()
        return True

    def update_reading_status(self, list_name: str, paper_url: str, status: str) -> bool:
        """Update status: unread, reading, done."""
        rl = self._get_reading_list_by_name(list_name)
        if not rl:
            return False
        self._conn.execute(
            "UPDATE reading_list_items SET status = ? WHERE list_id = ? AND paper_url = ?",
            (status, rl["id"], paper_url),
        )
        self._conn.commit()
        return True

    def get_reading_list_items(self, list_name: str) -> list[dict]:
        rl = self._get_reading_list_by_name(list_name)
        if not rl:
            return []
        cur = self._conn.execute(
            """SELECT * FROM reading_list_items
               WHERE list_id = ?
               ORDER BY priority DESC, added_at DESC""",
            (rl["id"],),
        )
        return [dict(r) for r in cur.fetchall()]

    def _get_reading_list_by_name(self, name: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM reading_lists WHERE name = ?", (name,))
        row = cur.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        return {
            "projects": self._conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
            "tags": self._conn.execute("SELECT COUNT(DISTINCT tag) FROM paper_tags").fetchone()[0],
            "annotations": self._conn.execute("SELECT COUNT(*) FROM paper_annotations").fetchone()[0],
            "reading_lists": self._conn.execute("SELECT COUNT(*) FROM reading_lists").fetchone()[0],
        }

    def close(self) -> None:
        self._conn.close()

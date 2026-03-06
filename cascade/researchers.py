"""Researcher co-authorship network database.

Automatically populated during citation graph crawls.  Stores researchers,
their papers, and co-authorship links in SQLite alongside the main memory DB.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from cascade.config import get_settings

log = logging.getLogger(__name__)


class ResearcherDB:
    """Manage a network of research scientists extracted from citation graphs."""

    def __init__(self, db_path: Path | None = None):
        s = get_settings()
        self._db_path = db_path or s.db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def __enter__(self) -> "ResearcherDB":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS researchers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL UNIQUE COLLATE NOCASE,
                paper_count     INTEGER DEFAULT 0,
                total_citations INTEGER DEFAULT 0,
                first_seen      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS researcher_papers (
                researcher_id   INTEGER NOT NULL,
                paper_id        TEXT NOT NULL,
                paper_title     TEXT DEFAULT '',
                year            INTEGER DEFAULT 0,
                PRIMARY KEY (researcher_id, paper_id)
            );

            CREATE TABLE IF NOT EXISTS coauthorships (
                researcher_a_id INTEGER NOT NULL,
                researcher_b_id INTEGER NOT NULL,
                shared_papers   INTEGER DEFAULT 1,
                PRIMARY KEY (researcher_a_id, researcher_b_id)
            );

            CREATE INDEX IF NOT EXISTS idx_researcher_name ON researchers(name);
            CREATE INDEX IF NOT EXISTS idx_rp_researcher ON researcher_papers(researcher_id);
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Ingest from citation graph
    # ------------------------------------------------------------------

    def ingest_from_graph(self, graph: Any) -> int:
        """Extract all authors and co-authorship pairs from a CitationGraph.

        Returns the number of new researchers added.
        """
        added = 0
        for node in graph.nodes.values():
            if not node.authors:
                continue

            # Get or create each author
            author_ids: list[int] = []
            for name in node.authors:
                name = name.strip()
                if not name:
                    continue
                rid = self._get_or_create_researcher(name)
                author_ids.append(rid)

                # Link author to paper
                self._conn.execute(
                    "INSERT OR IGNORE INTO researcher_papers (researcher_id, paper_id, paper_title, year) "
                    "VALUES (?, ?, ?, ?)",
                    (rid, node.paper_id, node.title, node.year),
                )

            # Update paper_count and total_citations for each author
            for rid in author_ids:
                self._conn.execute(
                    """UPDATE researchers SET
                        paper_count = (SELECT COUNT(*) FROM researcher_papers WHERE researcher_id = ?),
                        total_citations = total_citations + ?
                       WHERE id = ?""",
                    (rid, node.citation_count or 0, rid),
                )

            # Record co-authorship pairs
            for i, a_id in enumerate(author_ids):
                for b_id in author_ids[i + 1:]:
                    lo, hi = min(a_id, b_id), max(a_id, b_id)
                    existing = self._conn.execute(
                        "SELECT shared_papers FROM coauthorships WHERE researcher_a_id = ? AND researcher_b_id = ?",
                        (lo, hi),
                    ).fetchone()
                    if existing:
                        self._conn.execute(
                            "UPDATE coauthorships SET shared_papers = shared_papers + 1 "
                            "WHERE researcher_a_id = ? AND researcher_b_id = ?",
                            (lo, hi),
                        )
                    else:
                        self._conn.execute(
                            "INSERT INTO coauthorships (researcher_a_id, researcher_b_id, shared_papers) "
                            "VALUES (?, ?, 1)",
                            (lo, hi),
                        )

        self._conn.commit()
        return added

    def _get_or_create_researcher(self, name: str) -> int:
        cur = self._conn.execute("SELECT id FROM researchers WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur = self._conn.execute(
            "INSERT INTO researchers (name, first_seen) VALUES (?, ?)",
            (name, datetime.now().isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_researcher(self, name: str) -> dict | None:
        """Get researcher info + their papers."""
        cur = self._conn.execute("SELECT * FROM researchers WHERE name = ? COLLATE NOCASE", (name,))
        row = cur.fetchone()
        if not row:
            return None
        r = dict(row)
        papers = self._conn.execute(
            "SELECT paper_id, paper_title, year FROM researcher_papers WHERE researcher_id = ? ORDER BY year DESC",
            (r["id"],),
        ).fetchall()
        r["papers"] = [dict(p) for p in papers]
        return r

    def get_coauthors(self, name: str) -> list[dict]:
        """Get ranked co-authors for a researcher."""
        researcher = self.get_researcher(name)
        if not researcher:
            return []
        rid = researcher["id"]

        coauthors = self._conn.execute(
            """SELECT r.name, r.paper_count, r.total_citations, c.shared_papers
               FROM coauthorships c
               JOIN researchers r ON (
                   CASE WHEN c.researcher_a_id = ? THEN c.researcher_b_id
                        ELSE c.researcher_a_id END = r.id
               )
               WHERE c.researcher_a_id = ? OR c.researcher_b_id = ?
               ORDER BY c.shared_papers DESC""",
            (rid, rid, rid),
        ).fetchall()
        return [dict(c) for c in coauthors]

    def search_researchers(self, query: str, limit: int = 20) -> list[dict]:
        """Fuzzy search researchers by name."""
        cur = self._conn.execute(
            "SELECT * FROM researchers WHERE name LIKE ? ORDER BY paper_count DESC LIMIT ?",
            (f"%{query}%", limit),
        )
        return [dict(r) for r in cur.fetchall()]

    def top_researchers(self, limit: int = 20, sort_by: str = "paper_count") -> list[dict]:
        """Get top researchers by paper count or total citations."""
        col = "total_citations" if sort_by == "citations" else "paper_count"
        cur = self._conn.execute(
            f"SELECT * FROM researchers ORDER BY {col} DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    def stats(self) -> dict[str, int]:
        return {
            "researchers": self._conn.execute("SELECT COUNT(*) FROM researchers").fetchone()[0],
            "papers_linked": self._conn.execute("SELECT COUNT(DISTINCT paper_id) FROM researcher_papers").fetchone()[0],
            "coauthor_pairs": self._conn.execute("SELECT COUNT(*) FROM coauthorships").fetchone()[0],
        }

    def close(self) -> None:
        self._conn.close()

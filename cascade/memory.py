"""SQLite-based memory store for papers, sessions, and insights."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from cascade.config import get_settings
from cascade.exceptions import MemoryError as CascadeMemoryError
from cascade.search.arxiv_search import Paper

log = logging.getLogger(__name__)


class Memory:
    """Persistent memory backed by SQLite."""

    def __init__(self, db_path: Path | None = None):
        s = get_settings()
        self._db_path = db_path or s.db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_tables()
        self._semantic: Any = None  # Lazy-loaded SemanticMemory

    def _get_semantic(self) -> Any:
        """Lazy-load SemanticMemory (returns None if unavailable)."""
        if self._semantic is None:
            try:
                from cascade.semantic import get_semantic_memory
                self._semantic = get_semantic_memory()
            except Exception as e:
                log.debug("Semantic memory unavailable: %s", e)
                self._semantic = False  # Sentinel: don't retry
        return self._semantic if self._semantic is not False else None

    # Context manager support
    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_tables(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS papers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                authors     TEXT,
                abstract    TEXT,
                url         TEXT,
                source      TEXT,
                year        INTEGER,
                citations   INTEGER,
                categories  TEXT,
                arxiv_id    TEXT,
                doi         TEXT,
                pdf_url     TEXT,
                added_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                command         TEXT NOT NULL,
                query           TEXT,
                result_summary  TEXT,
                timestamp       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS insights (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                topic           TEXT NOT NULL,
                insight_text    TEXT NOT NULL,
                source_papers   TEXT,
                created_at      TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_url ON papers(url);
            CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);
            CREATE INDEX IF NOT EXISTS idx_insights_topic ON insights(topic);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Papers
    # ------------------------------------------------------------------

    def save_paper(self, paper: Paper) -> None:
        """Save a paper, ignoring duplicates by URL."""
        try:
            self._conn.execute(
                """INSERT OR IGNORE INTO papers
                   (title, authors, abstract, url, source, year, citations,
                    categories, arxiv_id, doi, pdf_url, added_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    paper.title,
                    json.dumps(paper.authors),
                    paper.abstract,
                    paper.url,
                    paper.source,
                    paper.year,
                    paper.citation_count,
                    json.dumps(paper.categories),
                    paper.arxiv_id,
                    paper.doi,
                    paper.pdf_url,
                    datetime.now().isoformat(),
                ),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            log.error("Failed to save paper '%s': %s", paper.title, e)
            raise CascadeMemoryError(f"Failed to save paper '{paper.title}': {e}") from e

        # Embed into ChromaDB (best-effort)
        sem = self._get_semantic()
        if sem:
            try:
                sem.embed_paper(paper)
            except Exception as e:
                log.debug("Semantic embed failed for '%s': %s", paper.title, e)

    def save_papers(self, papers: list[Paper]) -> int:
        """Save multiple papers, return count of newly added."""
        before = self.count_papers()
        for p in papers:
            self.save_paper(p)
        return self.count_papers() - before

    def search_papers(
        self, query: str, limit: int = 20, semantic: bool = False
    ) -> list[dict]:
        """Search stored papers by title or abstract.

        When *semantic* is True and ChromaDB is available, uses vector
        similarity search instead of SQL LIKE.
        """
        if semantic:
            sem = self._get_semantic()
            if sem:
                return sem.search(query, n_results=limit)

        cur = self._conn.execute(
            """SELECT * FROM papers
               WHERE title LIKE ? OR abstract LIKE ?
               ORDER BY year DESC
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_all_papers(self, limit: int = 50) -> list[dict]:
        """Retrieve all stored papers, most recent first."""
        cur = self._conn.execute(
            "SELECT * FROM papers ORDER BY added_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cur.fetchall()]

    def count_papers(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM papers")
        return cur.fetchone()[0]

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def log_session(self, command: str, query: str, result_summary: str) -> None:
        """Log a CLI session/command."""
        self._conn.execute(
            """INSERT INTO sessions (command, query, result_summary, timestamp)
               VALUES (?, ?, ?, ?)""",
            (command, query, result_summary, datetime.now().isoformat()),
        )
        self._conn.commit()

    def get_sessions(self, limit: int = 20) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM sessions ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def save_insight(
        self, topic: str, insight_text: str, source_papers: list[str] | None = None
    ) -> None:
        """Store a research insight."""
        self._conn.execute(
            """INSERT INTO insights (topic, insight_text, source_papers, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                topic,
                insight_text,
                json.dumps(source_papers or []),
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()

        # Embed into ChromaDB (best-effort)
        sem = self._get_semantic()
        if sem:
            try:
                sem.embed_insight(topic, insight_text)
            except Exception as e:
                log.debug("Semantic embed insight failed: %s", e)

    def get_insights(self, topic: str | None = None, limit: int = 20) -> list[dict]:
        """Retrieve insights, optionally filtered by topic."""
        if topic:
            cur = self._conn.execute(
                """SELECT * FROM insights
                   WHERE topic LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (f"%{topic}%", limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM insights ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def build_context(self, topic: str, max_papers: int = 10) -> str:
        """Build a context string from stored papers and insights for LLM prompts.

        Uses semantic search (ChromaDB) when available; falls back to keyword.
        """
        # Try semantic context first
        sem = self._get_semantic()
        if sem:
            try:
                ctx = sem.build_semantic_context(
                    topic, max_papers=max_papers, max_insights=5
                )
                if ctx:
                    return ctx
            except Exception as e:
                log.debug("Semantic context failed, falling back: %s", e)

        # Keyword fallback
        papers = self.search_papers(topic, limit=max_papers)
        insights = self.get_insights(topic, limit=5)

        parts: list[str] = []

        if papers:
            parts.append("## Relevant Papers from Memory\n")
            for p in papers:
                authors = json.loads(p["authors"]) if isinstance(p["authors"], str) else p["authors"]
                author_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    author_str += " et al."
                parts.append(
                    f"- **{p['title']}** ({p['year']}) — {author_str}\n"
                    f"  {(p.get('abstract') or '')[:200]}...\n"
                )

        if insights:
            parts.append("\n## Previous Insights\n")
            for i in insights:
                parts.append(f"- [{i['topic']}] {i['insight_text'][:300]}\n")

        return "\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        """Return counts of all stored entities."""
        return {
            "papers": self.count_papers(),
            "sessions": self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            "insights": self._conn.execute("SELECT COUNT(*) FROM insights").fetchone()[0],
        }

    def close(self) -> None:
        self._conn.close()

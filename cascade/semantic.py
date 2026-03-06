"""Semantic memory — ChromaDB-backed vector search for papers and insights.

Uses OpenAI ``text-embedding-3-large`` embeddings and ChromaDB for persistent
vector storage, enabling semantic (meaning-based) search across stored papers
and research insights.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from cascade.config import get_settings
from cascade.exceptions import ConfigError, MemoryError as CascadeMemoryError
from cascade.search.arxiv_search import Paper

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------

_instance: "SemanticMemory | None" = None


def get_semantic_memory() -> "SemanticMemory":
    """Return the global SemanticMemory instance (lazy-initialised)."""
    global _instance
    if _instance is None:
        _instance = SemanticMemory()
    return _instance


# ---------------------------------------------------------------------------
# SemanticMemory
# ---------------------------------------------------------------------------

class SemanticMemory:
    """ChromaDB-backed vector store for semantic search.

    Two collections are maintained:
        * ``papers`` — title + abstract embeddings
        * ``insights`` — research insight text embeddings

    All embeddings are generated via the OpenAI embedding API using the
    model specified in ``Settings.embedding_model``.
    """

    def __init__(
        self,
        persist_path: Path | None = None,
        embedding_model: str | None = None,
    ) -> None:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        s = get_settings()
        self._persist_path = persist_path or s.chroma_path
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._model = embedding_model or s.embedding_model

        if not s.openai_api_key:
            raise ConfigError(
                "OPENAI_API_KEY is required for semantic memory embeddings. "
                "Add it to your .env file."
            )

        self._ef = OpenAIEmbeddingFunction(
            api_key=s.openai_api_key,
            model_name=self._model,
        )

        self._client = chromadb.PersistentClient(
            path=str(self._persist_path),
        )

        self._papers = self._client.get_or_create_collection(
            name="papers",
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._insights = self._client.get_or_create_collection(
            name="insights",
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Papers
    # ------------------------------------------------------------------

    def embed_paper(self, paper: Paper) -> None:
        """Upsert a paper into the vector store.

        The document text is ``title + abstract`` concatenated.
        Metadata stores all structured fields for retrieval.
        """
        doc_id = paper.url or paper.arxiv_id or paper.title
        text = f"{paper.title}\n\n{paper.abstract}"

        metadata: dict[str, Any] = {
            "title": paper.title,
            "year": paper.year or 0,
            "source": paper.source,
            "url": paper.url or "",
            "citation_count": paper.citation_count or 0,
        }
        # ChromaDB metadata values must be str, int, float, or bool
        if paper.authors:
            metadata["authors"] = ", ".join(paper.authors[:5])
        if paper.arxiv_id:
            metadata["arxiv_id"] = paper.arxiv_id
        if paper.doi:
            metadata["doi"] = paper.doi

        try:
            self._papers.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
            )
        except Exception as e:
            log.error("Failed to embed paper '%s': %s", paper.title, e)
            raise CascadeMemoryError(f"Failed to embed paper: {e}") from e

    def embed_papers(self, papers: list[Paper]) -> int:
        """Embed multiple papers. Returns count embedded."""
        for p in papers:
            self.embed_paper(p)
        return len(papers)

    def search(
        self,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search for papers.

        Returns a list of dicts with keys: title, year, source, url,
        citation_count, authors, distance, abstract_snippet.
        """
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, self._papers.count() or n_results),
        }
        if where:
            kwargs["where"] = where

        if self._papers.count() == 0:
            return []

        results = self._papers.query(**kwargs)

        papers: list[dict[str, Any]] = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results.get("distances") else None
            doc_text = results["documents"][0][i] if results.get("documents") else ""

            papers.append({
                "id": doc_id,
                "title": meta.get("title", ""),
                "year": meta.get("year", 0),
                "source": meta.get("source", ""),
                "url": meta.get("url", ""),
                "citation_count": meta.get("citation_count", 0),
                "authors": meta.get("authors", ""),
                "arxiv_id": meta.get("arxiv_id"),
                "doi": meta.get("doi"),
                "distance": distance,
                "abstract": doc_text.split("\n\n", 1)[1] if "\n\n" in doc_text else doc_text,
            })

        return papers

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def embed_insight(self, topic: str, insight_text: str) -> None:
        """Upsert a research insight into the vector store."""
        import hashlib

        doc_id = hashlib.md5(f"{topic}:{insight_text[:100]}".encode()).hexdigest()

        try:
            self._insights.upsert(
                ids=[doc_id],
                documents=[insight_text],
                metadatas=[{"topic": topic}],
            )
        except Exception as e:
            log.error("Failed to embed insight: %s", e)

    def search_insights(
        self,
        query: str,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search for insights."""
        if self._insights.count() == 0:
            return []

        results = self._insights.query(
            query_texts=[query],
            n_results=min(n_results, self._insights.count()),
        )

        insights: list[dict[str, Any]] = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            insights.append({
                "topic": meta.get("topic", ""),
                "insight_text": results["documents"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })

        return insights

    # ------------------------------------------------------------------
    # Context building (replaces keyword-based Memory.build_context)
    # ------------------------------------------------------------------

    def build_semantic_context(
        self,
        query: str,
        max_papers: int = 10,
        max_insights: int = 5,
    ) -> str:
        """Build an LLM context string using semantic similarity.

        This is the semantic upgrade to ``Memory.build_context()``.
        """
        parts: list[str] = []

        papers = self.search(query, n_results=max_papers)
        if papers:
            parts.append("## Semantically Relevant Papers from Memory\n")
            for p in papers:
                authors = p.get("authors", "")
                dist = p.get("distance")
                score_str = f" (similarity: {1 - dist:.2f})" if dist is not None else ""
                abstract = (p.get("abstract") or "")[:200]
                parts.append(
                    f"- **{p['title']}** ({p['year']}) — {authors}{score_str}\n"
                    f"  {abstract}...\n"
                )

        insights = self.search_insights(query, n_results=max_insights)
        if insights:
            parts.append("\n## Semantically Relevant Insights\n")
            for ins in insights:
                parts.append(
                    f"- [{ins['topic']}] {ins['insight_text'][:300]}\n"
                )

        return "\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Sync & stats
    # ------------------------------------------------------------------

    def sync_from_sqlite(self, memory: Any) -> int:
        """Bulk-import papers from the SQLite Memory into ChromaDB.

        Useful for back-filling when semantic memory is first enabled.
        Returns the count of papers synced.
        """
        all_papers = memory.get_all_papers(limit=10_000)
        count = 0

        for row in all_papers:
            authors_raw = row.get("authors", "[]")
            if isinstance(authors_raw, str):
                try:
                    authors = json.loads(authors_raw)
                except json.JSONDecodeError:
                    authors = [authors_raw]
            else:
                authors = list(authors_raw)

            paper = Paper(
                title=row.get("title", ""),
                authors=authors,
                abstract=row.get("abstract", ""),
                url=row.get("url", ""),
                year=row.get("year", 0),
                source=row.get("source", ""),
                categories=[],
                citation_count=row.get("citations"),
                arxiv_id=row.get("arxiv_id"),
                doi=row.get("doi"),
                pdf_url=row.get("pdf_url"),
            )
            try:
                self.embed_paper(paper)
                count += 1
            except Exception as e:
                log.warning("Skipping paper '%s': %s", paper.title, e)

        # Sync insights too
        all_insights = memory.get_insights(limit=10_000)
        for ins in all_insights:
            self.embed_insight(ins.get("topic", ""), ins.get("insight_text", ""))

        return count

    def stats(self) -> dict[str, int]:
        """Return counts of embedded items."""
        return {
            "papers": self._papers.count(),
            "insights": self._insights.count(),
        }

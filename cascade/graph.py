"""Citation graph spider — recursive BFS crawler with interactive visualization.

Spiders outward from a seed paper via Semantic Scholar's citation/reference APIs,
building a directed graph.  Renders as interactive HTML (pyvis), DOT, or JSON.

Supports **resumable crawling**: the BFS frontier and expanded set are persisted
alongside the graph, allowing ``resume()`` to pick up exactly where the last
crawl left off without re-fetching already-explored papers.
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

log = logging.getLogger(__name__)
console = Console()

# Default auto-save directory
GRAPH_DIR = Path(os.getenv("CASCADE_HOME", str(Path.home() / ".cascade"))) / "graphs"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    """A paper node in the citation graph."""

    paper_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int = 0
    citation_count: int = 0
    abstract: str = ""
    url: str = ""
    depth: int = 0  # Hops from seed paper

    @property
    def label(self) -> str:
        """Short label for visualization: first author + year."""
        first = self.authors[0].split()[-1] if self.authors else "?"
        return f"{first} {self.year}" if self.year else first


# ---------------------------------------------------------------------------
# Citation graph
# ---------------------------------------------------------------------------

class CitationGraph:
    """BFS citation spider with graph construction, visualization, and resumable crawling."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[tuple[str, str]] = []  # (source → target) = source cites target
        self.seed_id: str = ""
        # Resumable state
        self.frontier: list[tuple[str, int]] = []  # (paper_id, depth) — unexpanded queue
        self.expanded: set[str] = set()  # Papers whose citations/refs have been fetched
        self.direction: str = "both"  # Last crawl direction (preserved for resume)

    # ------------------------------------------------------------------
    # Crawl
    # ------------------------------------------------------------------

    def crawl(
        self,
        seed_id: str,
        *,
        depth: int = 2,
        max_papers: int = 200,
        direction: Literal["both", "citations", "references"] = "both",
        fetch_citations_fn: Any = None,
        fetch_references_fn: Any = None,
        fetch_details_fn: Any = None,
    ) -> None:
        """BFS crawl outward from *seed_id*.

        Parameters
        ----------
        seed_id : str
            S2 paper ID (40-char hex) of the starting paper.
        depth : int
            Maximum BFS depth (default 2).
        max_papers : int
            Stop after collecting this many papers (default 200).
        direction : str
            "citations" (who cites this), "references" (what this cites), "both".
        fetch_citations_fn / fetch_references_fn / fetch_details_fn :
            Injectable functions for testing.  Default to S2 API helpers.
        """
        _fetch_citations, _fetch_references, _fetch_details = self._resolve_fetchers(
            fetch_citations_fn, fetch_references_fn, fetch_details_fn,
        )

        self.seed_id = seed_id
        self.direction = direction
        queue: deque[tuple[str, int]] = deque()
        visited: set[str] = set()

        # Fetch seed paper details
        try:
            seed_data = _fetch_details(seed_id)
        except Exception as e:
            log.error("Failed to fetch seed paper: %s", e)
            raise

        self._add_node_from_dict(seed_data, depth=0)
        visited.add(seed_id)
        queue.append((seed_id, 0))

        self._bfs_loop(queue, visited, depth, max_papers, direction,
                       _fetch_citations, _fetch_references)

    def resume(
        self,
        *,
        depth: int | None = None,
        max_papers: int = 200,
        direction: str | None = None,
        fetch_citations_fn: Any = None,
        fetch_references_fn: Any = None,
        fetch_details_fn: Any = None,
    ) -> None:
        """Continue crawling from where the last crawl stopped.

        Reloads the frontier (unexpanded papers) and continues BFS.
        """
        _fetch_citations, _fetch_references, _ = self._resolve_fetchers(
            fetch_citations_fn, fetch_references_fn, fetch_details_fn,
        )

        if not self.frontier:
            console.print("[yellow]No frontier to resume from — graph is fully expanded.[/yellow]")
            return

        direction = direction or self.direction or "both"
        # Use at least the max depth in frontier + 1 if no explicit depth given
        max_frontier_depth = max(d for _, d in self.frontier) if self.frontier else 0
        crawl_depth = depth if depth is not None else max_frontier_depth + 1

        queue: deque[tuple[str, int]] = deque(self.frontier)
        visited: set[str] = set(self.nodes.keys())

        console.print(
            f"[bold cyan]Resuming crawl:[/bold cyan] "
            f"{len(self.frontier)} papers in frontier, "
            f"{len(self.nodes)} already crawled, "
            f"new depth limit={crawl_depth}, max_papers={max_papers}"
        )

        self._bfs_loop(queue, visited, crawl_depth, max_papers, direction,
                       _fetch_citations, _fetch_references)

    def _bfs_loop(
        self,
        queue: deque[tuple[str, int]],
        visited: set[str],
        depth: int,
        max_papers: int,
        direction: str,
        _fetch_citations: Any,
        _fetch_references: Any,
    ) -> None:
        """Core BFS loop shared by crawl() and resume()."""
        self.frontier = []  # Reset frontier — will be rebuilt with unexpanded items
        total_limit = len(self.nodes) + max_papers  # allow max_papers new additions

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} papers"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Crawling citation graph...", total=total_limit,
                completed=len(self.nodes),
            )

            while queue and len(self.nodes) < total_limit:
                current_id, current_depth = queue.popleft()

                if current_depth >= depth:
                    # Beyond depth limit — keep in frontier for future resume
                    self.frontier.append((current_id, current_depth))
                    continue

                if current_id in self.expanded:
                    continue  # Already fetched citations/refs for this paper

                next_depth = current_depth + 1

                # Fetch citations (papers that cite this one)
                if direction in ("both", "citations"):
                    try:
                        citing = _fetch_citations(current_id, max_results=50)
                    except Exception as e:
                        log.warning("Citations fetch failed for %s: %s", current_id, e)
                        citing = []

                    for raw in citing:
                        pid = raw.get("paperId")
                        if not pid or len(self.nodes) >= total_limit:
                            break
                        self.edges.append((pid, current_id))
                        if pid not in visited:
                            visited.add(pid)
                            self._add_node_from_dict(raw, depth=next_depth)
                            queue.append((pid, next_depth))
                            progress.update(task, completed=len(self.nodes))

                # Fetch references (papers this one cites)
                if direction in ("both", "references"):
                    try:
                        refs = _fetch_references(current_id, max_results=50)
                    except Exception as e:
                        log.warning("References fetch failed for %s: %s", current_id, e)
                        refs = []

                    for raw in refs:
                        pid = raw.get("paperId")
                        if not pid or len(self.nodes) >= total_limit:
                            break
                        self.edges.append((current_id, pid))
                        if pid not in visited:
                            visited.add(pid)
                            self._add_node_from_dict(raw, depth=next_depth)
                            queue.append((pid, next_depth))
                            progress.update(task, completed=len(self.nodes))

                self.expanded.add(current_id)

            # Save remaining queue items to frontier for future resume
            self.frontier.extend(list(queue))
            progress.update(task, completed=len(self.nodes), total=len(self.nodes))

        if self.frontier:
            console.print(
                f"[dim]💾 {len(self.frontier)} papers remain in frontier for future --resume[/dim]"
            )

    @staticmethod
    def _resolve_fetchers(cit_fn: Any, ref_fn: Any, det_fn: Any) -> tuple:
        from cascade.search.semantic_scholar import (
            get_citations_raw,
            get_references_raw,
            get_paper_details_raw,
        )
        return (cit_fn or get_citations_raw,
                ref_fn or get_references_raw,
                det_fn or get_paper_details_raw)

    def _add_node_from_dict(self, data: dict, depth: int) -> None:
        pid = data.get("paperId", "")
        if not pid:
            return
        self.nodes[pid] = GraphNode(
            paper_id=pid,
            title=data.get("title", ""),
            authors=[a.get("name", "") for a in (data.get("authors") or [])],
            year=data.get("year") or 0,
            citation_count=data.get("citationCount") or 0,
            abstract=data.get("abstract") or "",
            url=data.get("url") or "",
            depth=depth,
        )

    # ------------------------------------------------------------------
    # Conversions
    # ------------------------------------------------------------------

    def to_networkx(self) -> Any:
        """Return a NetworkX DiGraph."""
        import networkx as nx

        G = nx.DiGraph()
        for pid, node in self.nodes.items():
            G.add_node(pid, **asdict(node))
        for src, tgt in self.edges:
            if src in self.nodes and tgt in self.nodes:
                G.add_edge(src, tgt)
        return G

    def to_pyvis(self, output_path: str = "citation_graph.html") -> str:
        """Render an interactive HTML graph. Returns the output path."""
        from pyvis.network import Network

        net = Network(
            height="900px",
            width="100%",
            directed=True,
            bgcolor="#1a1a2e",
            font_color="white",
            notebook=False,
        )

        # Color palette by depth
        depth_colors = ["#e63946", "#f4a261", "#2a9d8f", "#264653", "#6c5ce7", "#a29bfe"]

        for pid, node in self.nodes.items():
            size = max(8, min(60, 8 + int(math.log(node.citation_count + 1) * 5)))
            color = depth_colors[min(node.depth, len(depth_colors) - 1)]

            if pid == self.seed_id:
                color = "#ff006e"
                size = max(size, 40)

            abstract_preview = (node.abstract[:200] + "...") if len(node.abstract) > 200 else node.abstract
            tooltip = (
                f"<b>{node.title}</b><br>"
                f"<i>{', '.join(node.authors[:3])}</i><br>"
                f"Year: {node.year} | Citations: {node.citation_count}<br>"
                f"Depth: {node.depth}<br><br>"
                f"{abstract_preview}"
            )

            net.add_node(
                pid,
                label=node.label,
                title=tooltip,
                size=size,
                color=color,
                borderWidth=2 if pid == self.seed_id else 1,
                borderWidthSelected=4,
            )

        for src, tgt in self.edges:
            if src in self.nodes and tgt in self.nodes:
                net.add_edge(src, tgt, arrows="to", color="#555555")

        net.set_options("""
        {
            "physics": {
                "forceAtlas2Based": {
                    "gravitationalConstant": -30,
                    "centralGravity": 0.005,
                    "springLength": 150,
                    "springConstant": 0.02,
                    "damping": 0.85
                },
                "solver": "forceAtlas2Based",
                "stabilization": {"iterations": 200}
            },
            "edges": {
                "smooth": {"type": "continuous"},
                "arrows": {"to": {"scaleFactor": 0.5}}
            },
            "interaction": {
                "hover": true,
                "tooltipDelay": 100,
                "zoomView": true,
                "navigationButtons": true
            }
        }
        """)

        out = Path(output_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        net.save_graph(str(out))
        return str(out)

    def to_dot(self) -> str:
        """Return a GraphViz DOT string."""
        lines = ["digraph citation_graph {", '  rankdir=LR;', '  node [shape=box, style=filled];']
        for pid, node in self.nodes.items():
            color = "#ff006e" if pid == self.seed_id else "#2a9d8f"
            label = node.label.replace('"', '\\"')
            lines.append(f'  "{pid}" [label="{label}", fillcolor="{color}", fontcolor="white"];')
        for src, tgt in self.edges:
            if src in self.nodes and tgt in self.nodes:
                lines.append(f'  "{src}" -> "{tgt}";')
        lines.append("}")
        return "\n".join(lines)

    def to_json(self) -> str:
        """Return JSON representation including resumable state."""
        return json.dumps({
            "seed_id": self.seed_id,
            "direction": self.direction,
            "nodes": {pid: asdict(n) for pid, n in self.nodes.items()},
            "edges": self.edges,
            "frontier": self.frontier,
            "expanded": list(self.expanded),
        }, indent=2)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Save the crawled graph (with frontier) to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")

    def auto_save_path(self) -> Path:
        """Return the default auto-save path for this graph."""
        short_id = self.seed_id[:12] if self.seed_id else "unknown"
        GRAPH_DIR.mkdir(parents=True, exist_ok=True)
        return GRAPH_DIR / f"{short_id}.json"

    @classmethod
    def load(cls, path: str | Path) -> "CitationGraph":
        """Load a previously saved graph (with frontier) from JSON."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        graph = cls()
        graph.seed_id = data.get("seed_id", "")
        graph.direction = data.get("direction", "both")
        for pid, nd in data.get("nodes", {}).items():
            graph.nodes[pid] = GraphNode(**nd)
        graph.edges = [tuple(e) for e in data.get("edges", [])]
        graph.frontier = [tuple(f) for f in data.get("frontier", [])]
        graph.expanded = set(data.get("expanded", []))
        return graph

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return summary statistics about the crawled graph."""
        if not self.nodes:
            return {"nodes": 0, "edges": 0, "frontier": 0}

        years = [n.year for n in self.nodes.values() if n.year > 0]
        citations = [n.citation_count for n in self.nodes.values()]

        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "frontier": len(self.frontier),
            "expanded": len(self.expanded),
            "avg_citations": sum(citations) / len(citations) if citations else 0,
            "max_citations": max(citations) if citations else 0,
            "year_range": f"{min(years)}-{max(years)}" if years else "?",
            "max_depth": max(n.depth for n in self.nodes.values()) if self.nodes else 0,
            "seed_title": self.nodes.get(self.seed_id, GraphNode("", "")).title,
        }

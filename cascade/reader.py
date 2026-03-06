"""Paper reader — fetch, parse, summarise, and Q&A over a paper from a URL."""

from __future__ import annotations

import io
import logging
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from cascade.config import get_settings
from cascade.exceptions import ReaderError
from cascade.llm import ask, ask_and_display
from cascade.memory import Memory
from cascade.obsidian import save_paper_md
from cascade.search.arxiv_search import Paper

console = Console()
log = logging.getLogger(__name__)

# Maximum characters to send to the LLM (roughly ~30k tokens)
MAX_CONTEXT_CHARS = 120_000


# ---------------------------------------------------------------------------
# Parsed paper container
# ---------------------------------------------------------------------------

@dataclass
class ReadPaper:
    """Container for a fully-read paper with extracted content."""

    title: str
    authors: list[str]
    abstract: str
    full_text: str
    url: str
    year: int
    source: str  # "arxiv" | "semantic_scholar" | "web" | "pdf"
    pdf_url: str | None = None
    arxiv_id: str | None = None
    doi: str | None = None
    citation_count: int | None = None
    categories: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)

    def to_paper(self) -> Paper:
        """Convert to a standard Paper object for storage."""
        return Paper(
            title=self.title,
            authors=self.authors,
            abstract=self.abstract,
            url=self.url,
            year=self.year,
            source=self.source,
            categories=self.categories,
            citation_count=self.citation_count,
            arxiv_id=self.arxiv_id,
            doi=self.doi,
            pdf_url=self.pdf_url,
        )

    @property
    def context_text(self) -> str:
        """Return text suitable for LLM context, truncated if needed."""
        text = self.full_text or self.abstract
        if len(text) > MAX_CONTEXT_CHARS:
            text = text[:MAX_CONTEXT_CHARS] + "\n\n[... truncated for length ...]"
        return text


# ---------------------------------------------------------------------------
# URL type detection
# ---------------------------------------------------------------------------

def _detect_url_type(url: str) -> str:
    """Categorise a URL into arxiv, semantic_scholar, pdf, or web."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if "arxiv.org" in host:
        return "arxiv"
    if "semanticscholar.org" in host:
        return "semantic_scholar"
    if url.lower().endswith(".pdf"):
        return "pdf"
    # Check for arxiv-style IDs passed as raw strings
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", url):
        return "arxiv_id"
    return "web"


def _extract_arxiv_id(url: str) -> str:
    """Extract arXiv ID from a URL like https://arxiv.org/abs/2301.12345."""
    # Handle /abs/XXXX.XXXXX or /pdf/XXXX.XXXXX patterns
    match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", url)
    if match:
        return match.group(0)
    return url


def _extract_s2_id(url: str) -> str:
    """Extract Semantic Scholar paper ID from URL."""
    # https://www.semanticscholar.org/paper/Title-Words/HEX_ID
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "paper":
        return parts[-1]
    return url


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def _fetch_arxiv_paper(arxiv_id: str) -> ReadPaper:
    """Fetch an arXiv paper using the arxiv API + PDF text extraction."""
    import arxiv as arxiv_lib

    client = arxiv_lib.Client(delay_seconds=1.0, num_retries=3)
    search = arxiv_lib.Search(id_list=[arxiv_id])

    results = list(client.results(search))
    if not results:
        raise ReaderError(f"No arXiv paper found with ID: {arxiv_id}")

    result = results[0]

    # Try to extract full text from PDF
    full_text = ""
    pdf_url = result.pdf_url
    if pdf_url:
        try:
            full_text = _extract_pdf_from_url(pdf_url)
        except Exception as e:
            console.print(f"[yellow]PDF extraction failed: {e}. Using abstract only.[/yellow]")

    return ReadPaper(
        title=result.title.strip(),
        authors=[a.name for a in result.authors],
        abstract=result.summary.strip(),
        full_text=full_text or result.summary.strip(),
        url=result.entry_id,
        year=result.published.year,
        source="arxiv",
        pdf_url=pdf_url,
        arxiv_id=result.get_short_id(),
        doi=result.doi,
        categories=list(result.categories),
    )


def _fetch_s2_paper(paper_id: str) -> ReadPaper:
    """Fetch a paper from Semantic Scholar API + try PDF extraction.

    Includes retry logic for 429 rate limits (common without API key).
    """
    import time
    import requests
    from cascade.search.semantic_scholar import PAPER_FIELDS, _headers

    fields = PAPER_FIELDS + ",references,citations,tldr,openAccessPdf"

    # Retry with backoff for rate limits
    for attempt in range(4):
        resp = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}",
            params={"fields": fields},
            headers=_headers(),
            timeout=30,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt + 1
            console.print(f"[yellow]Rate limited by S2. Retrying in {wait}s...[/yellow]")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        raise ReaderError("Semantic Scholar rate limit exceeded after retries. Try again later.")

    data = resp.json()
    if not data.get("title"):
        raise ReaderError(f"No Semantic Scholar paper found for: {paper_id}")

    ext_ids = data.get("externalIds") or {}
    pdf_url = None

    # Try to find an open-access PDF
    if data.get("openAccessPdf"):
        pdf_url = data["openAccessPdf"].get("url")
    elif ext_ids.get("ArXiv"):
        pdf_url = f"https://arxiv.org/pdf/{ext_ids['ArXiv']}.pdf"

    # Try full-text extraction
    full_text = ""
    if pdf_url:
        try:
            full_text = _extract_pdf_from_url(pdf_url)
        except Exception as e:
            console.print(f"[yellow]PDF extraction failed: {e}. Using abstract only.[/yellow]")

    tldr = data.get("tldr", {})
    abstract = data.get("abstract") or ""
    if tldr and tldr.get("text"):
        abstract = f"{abstract}\n\nTL;DR: {tldr['text']}"

    return ReadPaper(
        title=data["title"],
        authors=[a.get("name", "") for a in (data.get("authors") or [])],
        abstract=abstract,
        full_text=full_text or abstract,
        url=data.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
        year=data.get("year") or 0,
        source="semantic_scholar",
        pdf_url=pdf_url,
        arxiv_id=ext_ids.get("ArXiv"),
        doi=ext_ids.get("DOI"),
        citation_count=data.get("citationCount"),
        categories=data.get("fieldsOfStudy") or [],
    )


def _extract_pdf_from_url(pdf_url: str) -> str:
    """Download a PDF and extract its text content."""
    import fitz  # pymupdf

    resp = httpx.get(
        pdf_url,
        follow_redirects=True,
        timeout=60.0,
        headers={"User-Agent": "cascade-research-assistant/0.1"},
    )
    resp.raise_for_status()

    doc = fitz.open(stream=resp.content, filetype="pdf")
    text_parts: list[str] = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()

    return "\n".join(text_parts).strip()


def _extract_pdf_from_file(filepath: str | Path) -> str:
    """Extract text from a local PDF file."""
    import fitz

    doc = fitz.open(str(filepath))
    text_parts: list[str] = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts).strip()


def _fetch_web_page(url: str) -> ReadPaper:
    """Fetch a web page and extract paper-like content from HTML."""
    resp = httpx.get(
        url,
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "cascade-research-assistant/0.1"},
    )
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")

    # If it's a PDF, extract text directly
    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        import fitz
        doc = fitz.open(stream=resp.content, filetype="pdf")
        text_parts = [page.get_text() for page in doc]
        doc.close()
        full_text = "\n".join(text_parts).strip()
        return ReadPaper(
            title=Path(urlparse(url).path).stem.replace("-", " ").replace("_", " ").title(),
            authors=[],
            abstract=full_text[:500],
            full_text=full_text,
            url=url,
            year=0,
            source="pdf",
            pdf_url=url,
        )

    # Parse HTML
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove script, style, nav, footer elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Extract title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    # Extract main content — prefer <article> or <main>, fall back to <body>
    main_content = soup.find("article") or soup.find("main") or soup.find("body")
    full_text = main_content.get_text(separator="\n", strip=True) if main_content else ""

    # Try to find abstract
    abstract = ""
    abstract_section = soup.find(id=re.compile(r"abstract", re.I))
    if not abstract_section:
        abstract_section = soup.find(class_=re.compile(r"abstract", re.I))
    if abstract_section:
        abstract = abstract_section.get_text(strip=True)
    else:
        # Use first ~500 chars as abstract
        abstract = full_text[:500]

    # Try to find authors
    authors: list[str] = []
    author_meta = soup.find("meta", attrs={"name": "citation_author"})
    if author_meta:
        for tag in soup.find_all("meta", attrs={"name": "citation_author"}):
            authors.append(tag.get("content", ""))

    # Try to find year
    year = 0
    date_meta = soup.find("meta", attrs={"name": "citation_publication_date"})
    if date_meta:
        date_str = date_meta.get("content", "")
        match = re.search(r"(\d{4})", date_str)
        if match:
            year = int(match.group(1))

    return ReadPaper(
        title=title,
        authors=authors,
        abstract=abstract,
        full_text=full_text,
        url=url,
        year=year,
        source="web",
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def read_paper(url: str) -> ReadPaper:
    """Fetch and parse a paper from any supported URL type.

    Supports:
    - arXiv URLs (abs or pdf) and raw arXiv IDs
    - Semantic Scholar URLs
    - Direct PDF URLs
    - General web pages (HTML extraction)
    """
    url_type = _detect_url_type(url)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        if url_type == "arxiv":
            task = progress.add_task("Fetching from arXiv...", total=None)
            arxiv_id = _extract_arxiv_id(url)
            paper = _fetch_arxiv_paper(arxiv_id)
            progress.remove_task(task)

        elif url_type == "arxiv_id":
            task = progress.add_task("Fetching from arXiv...", total=None)
            paper = _fetch_arxiv_paper(url)
            progress.remove_task(task)

        elif url_type == "semantic_scholar":
            task = progress.add_task("Fetching from Semantic Scholar...", total=None)
            s2_id = _extract_s2_id(url)
            paper = _fetch_s2_paper(s2_id)
            progress.remove_task(task)

        elif url_type == "pdf":
            task = progress.add_task("Downloading and parsing PDF...", total=None)
            paper = _fetch_web_page(url)
            progress.remove_task(task)

        else:
            task = progress.add_task("Fetching web page...", total=None)
            paper = _fetch_web_page(url)
            progress.remove_task(task)

    return paper


# ---------------------------------------------------------------------------
# LLM-powered analysis
# ---------------------------------------------------------------------------

SYSTEM_READER = """You are a world-class research paper analyst. You read academic papers
carefully and provide thorough, precise summaries and analyses.
When summarising, focus on:
1. The core contribution / key insight
2. Methodology and approach
3. Main results and their significance
4. Limitations and future work
5. How this connects to the broader field

Be precise and cite specific details from the paper. Write in clear academic prose."""


def summarise_paper(paper: ReadPaper) -> str:
    """Generate a structured summary of the paper using the LLM."""
    prompt = f"""Read and summarise this paper thoroughly.

## Paper: {paper.title}
**Authors:** {', '.join(paper.authors[:10])}
**Year:** {paper.year}

## Full Content:
{paper.context_text}

Provide a structured summary with:
1. **One-Line Summary** — The key contribution in one sentence
2. **Core Problem** — What problem does this paper address?
3. **Approach** — What methodology/technique do they use?
4. **Key Results** — Main findings with specific numbers if available
5. **Strengths** — What's done well?
6. **Limitations** — What could be improved?
7. **Key Takeaways for Research** — What should a researcher remember from this?
8. **Related Work Connections** — What other work does this build on or relate to?"""

    return ask_and_display(prompt, system=SYSTEM_READER, max_tokens=4000)


def ask_about_paper(paper: ReadPaper, question: str) -> str:
    """Answer a question about the paper using the LLM."""
    prompt = f"""Based on this paper, answer the following question.

## Paper: {paper.title}
**Authors:** {', '.join(paper.authors[:10])}

## Full Content:
{paper.context_text}

## Question:
{question}

Answer thoroughly, citing specific parts of the paper. If the paper doesn't address
the question directly, say so and provide your best analysis based on related content."""

    return ask_and_display(prompt, system=SYSTEM_READER, max_tokens=3000)


def extract_key_findings(paper: ReadPaper) -> str:
    """Extract key findings suitable for saving as a research insight."""
    prompt = f"""Extract the most important findings and insights from this paper in a concise format.

## Paper: {paper.title}
**Authors:** {', '.join(paper.authors[:10])}

## Full Content:
{paper.context_text}

Provide:
1. **Key Claims** (numbered list, 3-5 most important claims)
2. **Novel Contributions** (what's new)
3. **Quantitative Results** (specific numbers, if any)
4. **Methodological Innovations** (new techniques introduced)
5. **Open Questions** (what this paper leaves for future work)

Be concise but precise. Use bullet points."""

    return ask(prompt, system=SYSTEM_READER, max_tokens=2000)


# ---------------------------------------------------------------------------
# Save to memory + Obsidian
# ---------------------------------------------------------------------------

def save_reading(
    paper: ReadPaper,
    summary: str,
    key_findings: str | None = None,
    qa_history: list[tuple[str, str]] | None = None,
) -> Path:
    """Save the reading to memory (SQLite) and Obsidian vault.

    Returns the path to the saved Obsidian markdown file.
    """
    mem = Memory()
    s = get_settings()

    # Save the paper record to memory
    std_paper = paper.to_paper()
    mem.save_paper(std_paper)

    # Save the summary as an insight
    insight_text = f"## Summary\n{summary}"
    if key_findings:
        insight_text += f"\n\n## Key Findings\n{key_findings}"
    mem.save_insight(paper.title, insight_text, [paper.title])

    # Log the session
    mem.log_session("read", paper.url, f"Read and summarised: {paper.title}")

    # Save to Obsidian with enhanced content
    filepath = _save_reading_md(paper, summary, key_findings, qa_history)

    return filepath


def _save_reading_md(
    paper: ReadPaper,
    summary: str,
    key_findings: str | None = None,
    qa_history: list[tuple[str, str]] | None = None,
) -> Path:
    """Save a rich reading note to the Obsidian vault."""
    from datetime import datetime
    from cascade.obsidian import _frontmatter, _domain_tags

    s = get_settings()
    vault = s.vault_path
    papers_dir = vault / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    std_paper = paper.to_paper()
    tags = _domain_tags(std_paper)
    tags.append("#reading")

    metadata = {
        "title": f'"{paper.title}"',
        "authors": paper.authors[:10],
        "year": paper.year,
        "source": paper.source,
        "url": paper.url,
        "tags": tags,
        "date_read": datetime.now().strftime("%Y-%m-%d"),
        "status": "read",
    }
    if paper.citation_count is not None:
        metadata["citations"] = paper.citation_count
    if paper.arxiv_id:
        metadata["arxiv_id"] = paper.arxiv_id
    if paper.doi:
        metadata["doi"] = paper.doi

    sections = [
        _frontmatter(metadata),
        "",
        f"# {paper.title}",
        "",
        f"**Authors:** {', '.join(paper.authors[:10])}",
        f"**Year:** {paper.year}",
        f"**Source:** {paper.source}",
    ]

    if paper.citation_count is not None:
        sections.append(f"**Citations:** {paper.citation_count}")
    if paper.url:
        sections.append(f"**Link:** [Paper]({paper.url})")
    if paper.pdf_url:
        sections.append(f"**PDF:** [Download]({paper.pdf_url})")

    sections.extend([
        "",
        "## Abstract",
        "",
        paper.abstract[:1000] if paper.abstract else "_No abstract available._",
        "",
        "## Summary",
        "",
        summary,
    ])

    if key_findings:
        sections.extend([
            "",
            "## Key Findings",
            "",
            key_findings,
        ])

    if qa_history:
        sections.extend([
            "",
            "## Q&A",
            "",
        ])
        for q, a in qa_history:
            sections.extend([
                f"### Q: {q}",
                "",
                a,
                "",
            ])

    sections.extend([
        "",
        "## Personal Notes",
        "",
        "<!-- Add your own notes, connections, and ideas here -->",
        "",
    ])

    # sanitise filename
    safe_title = "".join(
        c if c.isalnum() or c in " -_" else "" for c in paper.title
    )[:80].strip()
    filename = f"{safe_title}.md"
    filepath = papers_dir / filename

    filepath.write_text("\n".join(sections), encoding="utf-8")
    return filepath

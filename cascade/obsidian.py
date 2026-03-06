"""Obsidian-compatible markdown export."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cascade.config import DOMAINS, get_settings
from cascade.search.arxiv_search import Paper


def _frontmatter(metadata: dict[str, Any]) -> str:
    """Generate YAML frontmatter block."""
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f'{key}: |')
            for l in value.split("\n"):
                lines.append(f"  {l}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _domain_tags(paper: Paper) -> list[str]:
    """Infer Obsidian tags from paper categories and keywords."""
    tags: list[str] = []
    title_abstract = (paper.title + " " + paper.abstract).lower()

    for domain_key, domain_info in DOMAINS.items():
        for kw in domain_info["keywords"]:
            if kw.lower() in title_abstract:
                tags.extend(domain_info["tags"])
                break

    # Add source tag
    tags.append(f"#source/{paper.source}")
    return list(set(tags))


def paper_to_md(paper: Paper) -> str:
    """Convert a Paper to Obsidian-compatible markdown."""
    tags = _domain_tags(paper)

    metadata = {
        "title": f'"{paper.title}"',
        "authors": paper.authors[:10],
        "year": paper.year,
        "source": paper.source,
        "url": paper.url,
        "tags": tags,
        "date_added": datetime.now().strftime("%Y-%m-%d"),
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
        f"**Authors:** {paper.author_str}",
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
        paper.abstract,
        "",
        "## Notes",
        "",
        "<!-- Add your reading notes here -->",
        "",
    ])

    return "\n".join(sections)


def save_paper_md(paper: Paper, vault_path: Path | None = None) -> Path:
    """Save a paper as a markdown file in the vault."""
    s = get_settings()
    vault = vault_path or s.vault_path
    papers_dir = vault / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    # Sanitise filename
    safe_title = "".join(
        c if c.isalnum() or c in " -_" else "" for c in paper.title
    )[:80].strip()
    filename = f"{safe_title}.md"
    filepath = papers_dir / filename

    filepath.write_text(paper_to_md(paper), encoding="utf-8")
    return filepath


def review_to_md(
    topic: str,
    content: str,
    papers: list[Paper],
    vault_path: Path | None = None,
) -> Path:
    """Save a literature review as markdown."""
    s = get_settings()
    vault = vault_path or s.vault_path
    reviews_dir = vault / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "title": f'"{topic} — Literature Review"',
        "type": "literature-review",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "papers_reviewed": len(papers),
        "tags": ["#review", "#research"],
    }

    sections = [
        _frontmatter(metadata),
        "",
        f"# Literature Review: {topic}",
        "",
        content,
        "",
        "## References",
        "",
    ]

    for i, p in enumerate(papers, 1):
        wikilink = f"[[{p.title}]]"
        sections.append(f"{i}. {wikilink} ({p.author_str}, {p.year})")

    safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:60].strip()
    ts = datetime.now().strftime("%Y%m%d")
    filepath = reviews_dir / f"{ts}_{safe_topic}.md"
    filepath.write_text("\n".join(sections), encoding="utf-8")
    return filepath


def gaps_to_md(
    topic: str,
    content: str,
    papers: list[Paper],
    vault_path: Path | None = None,
) -> Path:
    """Save research gap analysis as markdown."""
    s = get_settings()
    vault = vault_path or s.vault_path
    ideas_dir = vault / "ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "title": f'"{topic} — Research Gaps"',
        "type": "gap-analysis",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tags": ["#gap", "#research"],
    }

    sections = [
        _frontmatter(metadata),
        "",
        f"# Research Gaps: {topic}",
        "",
        content,
        "",
        "## Source Papers",
        "",
    ]

    for i, p in enumerate(papers, 1):
        sections.append(f"{i}. [[{p.title}]] ({p.author_str}, {p.year})")

    safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:60].strip()
    ts = datetime.now().strftime("%Y%m%d")
    filepath = ideas_dir / f"{ts}_gaps_{safe_topic}.md"
    filepath.write_text("\n".join(sections), encoding="utf-8")
    return filepath


def idea_to_md(
    problem: str,
    content: str,
    vault_path: Path | None = None,
) -> Path:
    """Save ideation output as markdown."""
    s = get_settings()
    vault = vault_path or s.vault_path
    ideas_dir = vault / "ideas"
    ideas_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "title": f'"{problem} — Ideas"',
        "type": "ideation",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tags": ["#idea", "#research"],
    }

    sections = [
        _frontmatter(metadata),
        "",
        f"# Ideation: {problem}",
        "",
        content,
    ]

    safe_problem = "".join(c if c.isalnum() or c in " -_" else "" for c in problem)[:60].strip()
    ts = datetime.now().strftime("%Y%m%d")
    filepath = ideas_dir / f"{ts}_idea_{safe_problem}.md"
    filepath.write_text("\n".join(sections), encoding="utf-8")
    return filepath


def draft_to_md(
    section_name: str,
    content: str,
    vault_path: Path | None = None,
) -> Path:
    """Save a paper section draft as markdown."""
    s = get_settings()
    vault = vault_path or s.vault_path
    drafts_dir = vault / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "title": f'"{section_name} — Draft"',
        "type": "draft",
        "section": section_name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tags": ["#draft", "#writing"],
    }

    sections = [
        _frontmatter(metadata),
        "",
        f"# Draft: {section_name}",
        "",
        content,
    ]

    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in section_name)[:60].strip()
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filepath = drafts_dir / f"{ts}_{safe_name}.md"
    filepath.write_text("\n".join(sections), encoding="utf-8")
    return filepath

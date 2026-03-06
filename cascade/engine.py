"""Research orchestrator — gap analysis, literature review, ideation."""

from __future__ import annotations

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from cascade.config import DOMAINS, get_settings
from cascade.llm import ask, ask_and_display
from cascade.memory import Memory
from cascade.obsidian import gaps_to_md, idea_to_md, review_to_md, save_paper_md
from cascade.search.arxiv_search import Paper, search_arxiv, search_arxiv_by_domain
from cascade.search.semantic_scholar import search_papers as ss_search
from cascade.tokens import build_budgeted_context, count_tokens, truncate_to_budget

console = Console()

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_RESEARCH = """You are a world-class CS AI researcher specialising in:
1. Computer Vision — Human Motion Generation (motion diffusion, text-to-motion, skeletal animation, action-conditioned synthesis)
2. NLP — Mechanistic Interpretability (transformer circuits, superposition, sparse autoencoders, activation patching, probing)

You have an encyclopaedic knowledge of the literature and can identify connections across sub-fields.
Always be precise, cite specific papers when possible, and think critically about methodology.
Write in clear, academic prose suitable for a top-tier venue (NeurIPS, CVPR, ICML, ACL, ICLR)."""

SYSTEM_GAPS = SYSTEM_RESEARCH + """

Your task is to identify RESEARCH GAPS. For each gap you identify:
1. Describe what is missing or under-explored
2. Explain why it matters (impact)
3. Suggest a concrete research direction to address it
4. Rate its novelty potential (High / Medium / Low)
5. Note any cross-domain opportunities (e.g. applying mech-interp techniques to motion generation models)

Be specific and actionable. Avoid vague statements like "more work is needed"."""

SYSTEM_REVIEW = SYSTEM_RESEARCH + """

Your task is to write a comprehensive LITERATURE REVIEW. Structure it as:
1. **Overview** — High-level landscape of the field
2. **Thematic Analysis** — Group papers by approach/methodology
3. **Chronological Evolution** — How the field has progressed
4. **Key Contributions** — Most impactful papers and why
5. **Comparison Table** — Methods, datasets, metrics, results (markdown table)
6. **Open Questions** — What remains unsolved

Use wikilinks like [[Paper Title]] when referencing papers.
Be thorough but concise. Target an audience of PhD students and researchers."""

SYSTEM_IDEATE = SYSTEM_RESEARCH + """

Your task is to IDEATE novel solutions to a research problem. For each idea:
1. **Title** — Catchy, descriptive name
2. **Core Insight** — What is the key innovation?
3. **Approach** — How would you implement this?
4. **Expected Advantages** — Why would this work better?
5. **Potential Challenges** — What could go wrong?
6. **Related Work** — Which existing papers are most relevant?
7. **Feasibility** — (High/Medium/Low) with time estimate

Generate at least 3-5 ideas, ranging from incremental to radical. Think across both CV and NLP sub-fields for cross-pollination opportunities."""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _collect_papers(
    topic: str,
    sources: list[str] | None = None,
    limit: int = 10,
) -> list[Paper]:
    """Search across multiple sources and aggregate results."""
    sources = sources or ["arxiv", "scholar"]
    all_papers: list[Paper] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        if "arxiv" in sources:
            task = progress.add_task("Searching arXiv...", total=None)
            try:
                papers = search_arxiv_by_domain(topic, max_results=limit)
                all_papers.extend(papers)
            except Exception as e:
                console.print(f"[yellow]arXiv search failed: {e}[/yellow]")
            progress.remove_task(task)

        if "scholar" in sources:
            task = progress.add_task("Searching Semantic Scholar...", total=None)
            try:
                papers = ss_search(topic, max_results=limit, fields_of_study=["Computer Science"])
                all_papers.extend(papers)
            except Exception as e:
                console.print(f"[yellow]Semantic Scholar search failed: {e}[/yellow]")
            progress.remove_task(task)

        if "openalex" in sources:
            task = progress.add_task("Searching OpenAlex...", total=None)
            try:
                from cascade.search.openalex_search import search_papers as oa_search
                papers = oa_search(topic, max_results=limit)
                all_papers.extend(papers)
            except Exception as e:
                console.print(f"[yellow]OpenAlex search failed: {e}[/yellow]")
            progress.remove_task(task)

        if "dblp" in sources:
            task = progress.add_task("Searching DBLP...", total=None)
            try:
                from cascade.search.dblp_search import search_papers as dblp_search
                papers = dblp_search(topic, max_results=limit)
                all_papers.extend(papers)
            except Exception as e:
                console.print(f"[yellow]DBLP search failed: {e}[/yellow]")
            progress.remove_task(task)

    # Deduplicate by title (case-insensitive)
    seen: set[str] = set()
    unique: list[Paper] = []
    for p in all_papers:
        key = p.title.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def _papers_to_context(papers: list[Paper]) -> str:
    """Format papers into an LLM-digestible context string.

    Uses token-aware truncation so abstracts don't blow the context budget.
    """
    s = get_settings()
    model = s.openai_model if s.default_llm == "openai" else s.claude_model

    lines: list[str] = []
    for i, p in enumerate(papers, 1):
        cites = f", citations: {p.citation_count}" if p.citation_count is not None else ""
        abstract = truncate_to_budget(p.abstract, max_tokens=400, model=model) if p.abstract else ""
        lines.append(
            f"{i}. **{p.title}** ({p.author_str}, {p.year}{cites})\n"
            f"   Abstract: {abstract}\n"
        )
    return "\n".join(lines)


def find_gaps(
    topic: str,
    limit: int = 15,
    save: bool = True,
) -> tuple[str, list[Paper]]:
    """Identify research gaps for a topic.

    Returns the gap analysis text and the papers analysed.
    """
    console.print(f"\n[bold cyan]🔍 Analysing research gaps for:[/bold cyan] {topic}\n")

    papers = _collect_papers(topic, limit=limit)
    if not papers:
        console.print("[red]No papers found. Try a different query.[/red]")
        return "", []

    console.print(f"[green]Found {len(papers)} papers. Analysing gaps...[/green]\n")

    # Build prompt with memory context
    mem = Memory()
    memory_ctx = mem.build_context(topic)

    prompt = f"""Analyse the following {len(papers)} papers on "{topic}" and identify research gaps.

{_papers_to_context(papers)}

{memory_ctx}

Provide a thorough gap analysis following your structured format."""

    result = ask_and_display(prompt, system=SYSTEM_GAPS)

    # Persist
    if save:
        for p in papers:
            mem.save_paper(p)
        mem.save_insight(topic, result, [p.title for p in papers[:10]])
        mem.log_session("gaps", topic, f"Identified gaps from {len(papers)} papers")
        filepath = gaps_to_md(topic, result, papers)
        console.print(f"\n[bold green]✅ Saved to:[/bold green] {filepath}")

    return result, papers


def literature_review(
    topic: str,
    limit: int = 20,
    save: bool = True,
) -> tuple[str, list[Paper]]:
    """Generate a structured literature review.

    Returns the review text and the papers reviewed.
    """
    console.print(f"\n[bold cyan]📚 Generating literature review for:[/bold cyan] {topic}\n")

    papers = _collect_papers(topic, limit=limit)
    if not papers:
        console.print("[red]No papers found. Try a different query.[/red]")
        return "", []

    console.print(f"[green]Found {len(papers)} papers. Synthesising review...[/green]\n")

    mem = Memory()
    memory_ctx = mem.build_context(topic)

    prompt = f"""Write a comprehensive literature review on "{topic}" based on these {len(papers)} papers.

{_papers_to_context(papers)}

{memory_ctx}

Follow your structured literature review format. Use [[Paper Title]] wikilinks when referencing papers."""

    result = ask_and_display(prompt, system=SYSTEM_REVIEW, max_tokens=8000)

    if save:
        for p in papers:
            mem.save_paper(p)
            save_paper_md(p)
        mem.save_insight(topic, f"Literature review: {result[:500]}...", [p.title for p in papers[:10]])
        mem.log_session("review", topic, f"Reviewed {len(papers)} papers")
        filepath = review_to_md(topic, result, papers)
        console.print(f"\n[bold green]✅ Saved to:[/bold green] {filepath}")

    return result, papers


def ideate(
    problem: str,
    limit: int = 10,
    save: bool = True,
) -> str:
    """Brainstorm novel solutions to a research problem.

    Pulls context from memory and recent papers.
    """
    console.print(f"\n[bold cyan]💡 Ideating solutions for:[/bold cyan] {problem}\n")

    papers = _collect_papers(problem, limit=limit)
    mem = Memory()
    memory_ctx = mem.build_context(problem)

    paper_ctx = _papers_to_context(papers) if papers else "No directly relevant papers found."

    prompt = f"""Generate novel research ideas to address: "{problem}"

## Related Work
{paper_ctx}

## Previous Context
{memory_ctx}

Think creatively. Consider cross-domain approaches between Computer Vision (motion generation) and NLP (mechanistic interpretability)."""

    result = ask_and_display(prompt, system=SYSTEM_IDEATE, max_tokens=6000)

    if save:
        for p in papers:
            mem.save_paper(p)
        mem.save_insight(problem, f"Ideation: {result[:500]}...", [p.title for p in papers[:5]])
        mem.log_session("ideate", problem, f"Generated ideas from {len(papers)} related papers")
        filepath = idea_to_md(problem, result)
        console.print(f"\n[bold green]✅ Saved to:[/bold green] {filepath}")

    return result

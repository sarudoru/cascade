"""Paper section drafting and feedback system."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from cascade.config import get_settings
from cascade.llm import ask, ask_and_display, ask_both
from cascade.memory import Memory
from cascade.obsidian import draft_to_md

console = Console()

# ---------------------------------------------------------------------------
# Section-specific system prompts
# ---------------------------------------------------------------------------

_BASE = """You are a world-class academic writer specialising in CS AI research.
You write with precision, clarity, and rigor suitable for top-tier venues (NeurIPS, CVPR, ICML, ACL, ICLR).
Your prose is clear and concise, avoids unnecessary jargon, and makes complex ideas accessible.
Always use proper academic conventions: passive voice where appropriate, hedging language for uncertain claims,
and precise technical terminology."""

SECTION_PROMPTS = {
    "abstract": _BASE + """
Write a concise, impactful abstract (150-250 words). Structure:
1. Problem statement (1-2 sentences)
2. Key limitation of existing work (1 sentence)
3. Your approach/contribution (2-3 sentences)
4. Key results and their significance (1-2 sentences)
Use specific numbers for results when available.""",

    "introduction": _BASE + """
Write a compelling introduction section. Structure:
1. **Hook** — Why does this problem matter? (broad context)
2. **Problem Definition** — What specific challenge are we addressing?
3. **Limitations of Prior Work** — What's missing? (be specific, cite papers)
4. **Our Approach** — What do we propose? (high-level)
5. **Contributions** — Bullet-pointed list of concrete contributions
6. **Paper Organisation** — Brief roadmap of the rest of the paper

Use wikilinks [[Paper Title]] when citing. Length: ~1-1.5 pages.""",

    "related-work": _BASE + """
Write a thorough related work section. Structure by thematic clusters, not chronologically.
For each cluster:
1. Describe the general approach
2. Discuss 3-5 key papers with specific details (methods, results)
3. Explain how our work differs or improves upon them

End with a paragraph explicitly positioning our work relative to the landscape.
Use wikilinks [[Paper Title]] when citing.""",

    "methods": _BASE + """
Write a clear, reproducible methods section. Structure:
1. **Problem Formulation** — Mathematical setup, notation, definitions
2. **Overview** — High-level architecture/approach (reference a figure if helpful)
3. **Component Details** — Each major component in its own subsection
4. **Training / Optimisation** — Loss functions, training procedure
5. **Implementation Details** — Key hyperparameters, architecture choices

Use LaTeX notation for math: $x$ for inline, $$x$$ for display.
Be precise enough that someone could reimplement the method.""",

    "experiments": _BASE + """
Write a rigorous experiments section. Structure:
1. **Experimental Setup** — Datasets, metrics, baselines, hardware
2. **Main Results** — Comparison tables with our method highlighted
3. **Ablation Studies** — What happens when we remove/change components?
4. **Qualitative Results** — Examples, visualisations (describe figures)
5. **Analysis** — Why does our method work? Failure cases?

Use markdown tables for results. Bold the best numbers.""",

    "conclusion": _BASE + """
Write a concise conclusion section (0.5-1 page). Structure:
1. **Summary** — What did we do and what did we find? (2-3 sentences)
2. **Key Takeaways** — Most important insights (2-3 points)
3. **Limitations** — Honest assessment of limitations
4. **Future Work** — Concrete, actionable directions (not vague)

End on a positive, forward-looking note.""",
}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_section(
    section: str,
    topic: str,
    context: str = "",
    save: bool = True,
) -> str:
    """Draft a specific paper section.

    Parameters
    ----------
    section : str
        One of: abstract, introduction, related-work, methods, experiments, conclusion
    topic : str
        The paper's topic or research question.
    context : str, optional
        Additional context (e.g. method description, results).
    """
    section_key = section.lower().strip()
    if section_key not in SECTION_PROMPTS:
        available = ", ".join(SECTION_PROMPTS.keys())
        console.print(f"[red]Unknown section '{section}'. Available: {available}[/red]")
        return ""

    console.print(f"\n[bold cyan]✍️  Drafting {section} for:[/bold cyan] {topic}\n")

    mem = Memory()
    memory_ctx = mem.build_context(topic)

    prompt = f"""Write the **{section}** section for a paper on: "{topic}"

## Additional Context
{context if context else "No additional context provided."}

## Background from Memory
{memory_ctx}

Write the section now. Use markdown formatting."""

    system = SECTION_PROMPTS[section_key]
    result = ask_and_display(prompt, system=system, max_tokens=6000)

    if save:
        mem.log_session("write", f"{section}: {topic}", f"Drafted {section} section")
        filepath = draft_to_md(f"{section} — {topic}", result)
        console.print(f"\n[bold green]✅ Saved to:[/bold green] {filepath}")

    return result


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

SYSTEM_FEEDBACK = """You are a senior reviewer for top-tier AI conferences (NeurIPS, CVPR, ICML, ACL, ICLR).
You provide constructive, specific, and actionable feedback. You are tough but fair.

For each piece of writing, evaluate:
1. **Clarity** — Is the writing clear and well-organised?
2. **Technical Rigor** — Are claims supported? Are there logical gaps?
3. **Novelty Framing** — Is the contribution clearly articulated?
4. **Completeness** — What's missing?
5. **Style** — Academic writing quality, grammar, flow
6. **Specific Suggestions** — Line-by-line or paragraph-by-paragraph improvements

Rate the overall quality: Strong Accept / Weak Accept / Borderline / Weak Reject / Strong Reject
Provide an estimated confidence score (1-5)."""


def feedback(
    text: str | None = None,
    filepath: str | None = None,
    dual: bool = True,
) -> str:
    """Get structured feedback on a piece of writing.

    Parameters
    ----------
    text : str, optional
        The text to review.
    filepath : str, optional
        Path to a markdown file to review.
    dual : bool
        If True, get feedback from both OpenAI and Claude.
    """
    if filepath:
        path = Path(filepath)
        if not path.exists():
            console.print(f"[red]File not found: {filepath}[/red]")
            return ""
        text = path.read_text(encoding="utf-8")
    elif not text:
        console.print("[red]Provide either text or a filepath.[/red]")
        return ""

    console.print("\n[bold cyan]📝 Getting feedback...[/bold cyan]\n")

    prompt = f"""Review the following academic writing and provide detailed feedback.

---
{text}
---

Provide your structured review now."""

    if dual:
        console.print("[dim]Querying both OpenAI and Claude for diverse perspectives...[/dim]\n")
        responses = ask_both(prompt, system=SYSTEM_FEEDBACK, max_tokens=4000)

        combined_parts: list[str] = []

        if "openai" in responses:
            console.print(Panel(
                Markdown(responses["openai"]),
                title="[bold blue]GPT-4o Feedback[/bold blue]",
                border_style="blue",
            ))
            combined_parts.append(f"## GPT-4o Feedback\n\n{responses['openai']}")

        if "claude" in responses:
            console.print(Panel(
                Markdown(responses["claude"]),
                title="[bold magenta]Claude Feedback[/bold magenta]",
                border_style="magenta",
            ))
            combined_parts.append(f"## Claude Feedback\n\n{responses['claude']}")

        # Synthesise
        if len(responses) == 2:
            synthesis_prompt = f"""Two reviewers gave the following feedback on the same paper:

### Reviewer 1 (GPT-4o):
{responses.get('openai', 'N/A')}

### Reviewer 2 (Claude):
{responses.get('claude', 'N/A')}

Synthesise their feedback into a unified action plan. Identify:
1. Points of agreement (most critical)
2. Points of disagreement (discuss both perspectives)
3. Prioritised action items (ranked by impact)"""

            console.print("\n[bold cyan]🔄 Synthesising reviews...[/bold cyan]\n")
            synthesis = ask_and_display(synthesis_prompt, system=SYSTEM_FEEDBACK)
            combined_parts.append(f"## Synthesised Action Plan\n\n{synthesis}")

        result = "\n\n---\n\n".join(combined_parts)
    else:
        result = ask_and_display(prompt, system=SYSTEM_FEEDBACK, max_tokens=4000)

    # Log
    mem = Memory()
    mem.log_session("feedback", filepath or "inline text", f"Feedback provided ({len(text)} chars)")

    return result

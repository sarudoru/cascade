"""Chat API — SSE-streamed conversation with the research agent."""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    mode: str = "auto"
    conversation: list[dict[str, str]] = Field(default_factory=list)


def _detect_url(text: str) -> str | None:
    """Return the first URL found in text, or None."""
    m = re.search(r'https?://\S+', text.strip())
    return m.group(0) if m else None


def _is_paper_url(url: str) -> bool:
    """Check if a URL looks like an academic paper link."""
    paper_patterns = [
        r'arxiv\.org',
        r'semanticscholar\.org',
        r'doi\.org',
        r'\.pdf$',
        r'openreview\.net',
        r'aclanthology\.org',
        r'papers\.nips\.cc',
        r'proceedings\.mlr\.press',
    ]
    return any(re.search(p, url, re.IGNORECASE) for p in paper_patterns)


async def _stream_chat(request: ChatRequest):
    """Generator that yields SSE events."""
    from cascade.llm import stream_ask
    from cascade.engine import (
        SYSTEM_GAPS,
        SYSTEM_IDEATE,
        SYSTEM_RESEARCH,
        SYSTEM_REVIEW,
        _collect_papers,
        _papers_to_context,
    )
    from cascade.reader import read_paper, summarise_paper
    from cascade.memory import Memory

    try:
        mode = (request.mode or "auto").lower()
        url = _detect_url(request.message)

        if url and _is_paper_url(url):
            # --- Paper reading flow ---
            yield _sse("status", {"text": "Reading paper...", "tool": "read_paper"})

            try:
                paper = read_paper(url)
                yield _sse("paper", {
                    "title": paper.title,
                    "authors": paper.authors,
                    "year": paper.year,
                    "url": paper.url,
                    "abstract": paper.abstract[:500] if paper.abstract else "",
                })

                yield _sse("status", {"text": "Summarising...", "tool": "summarise"})
                summary = summarise_paper(paper)
                yield _sse("text", {"content": summary})

                # Save to memory
                try:
                    with Memory() as mem:
                        mem.save_paper(paper.to_paper())
                except Exception:
                    pass

                yield _sse("done", {})

            except Exception as e:
                yield _sse("error", {"message": f"Failed to read paper: {e}"})
                return

        else:
            # --- General mode-aware research chat flow ---
            context_str = ""
            try:
                with Memory() as mem:
                    context_str = mem.build_context(request.message, max_papers=5)
            except Exception:
                pass

            papers = []
            if mode in {"research", "review", "gaps"}:
                yield _sse("status", {"text": "Finding relevant papers...", "tool": "search"})
                try:
                    papers = _collect_papers(
                        request.message,
                        sources=["arxiv", "scholar", "openalex", "dblp"],
                        limit=8,
                    )
                except Exception as e:
                    log.warning("Paper collection failed: %s", e)
                    papers = []

                if papers:
                    yield _sse(
                        "papers",
                        {
                            "items": [
                                {
                                    "title": p.title,
                                    "authors": p.authors,
                                    "year": p.year,
                                    "url": p.url,
                                    "abstract": (p.abstract or "")[:300],
                                    "source": p.source,
                                }
                                for p in papers[:8]
                            ]
                        },
                    )
                    try:
                        with Memory() as mem:
                            mem.save_papers(papers)
                    except Exception:
                        pass

            prompt_parts: list[str] = []

            # Add conversation history to prompt
            if request.conversation:
                history = "\n".join(
                    f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:500]}"
                    for m in request.conversation[-(6 * 2):]
                )
                prompt_parts.append(f"Previous conversation:\n{history}")

            if context_str:
                prompt_parts.append(f"Research context from saved memory:\n{context_str}")

            if papers:
                prompt_parts.append(f"Freshly discovered papers:\n{_papers_to_context(papers)}")

            if mode == "review":
                system = SYSTEM_REVIEW
                request_text = (
                    f'Produce a literature review on "{request.message}". '
                    "Prioritise concrete paper-level synthesis and clear section headers."
                )
                status_text = "Synthesizing literature review..."
            elif mode == "gaps":
                system = SYSTEM_GAPS
                request_text = (
                    f'Identify high-value research gaps for "{request.message}". '
                    "Use markdown headings and actionable next-step proposals."
                )
                status_text = "Analyzing research gaps..."
            elif mode == "research":
                system = SYSTEM_RESEARCH
                request_text = (
                    f'Conduct deep research on "{request.message}". '
                    "Return: overview, state of the art, strongest papers, open challenges, and concrete next experiments."
                )
                status_text = "Running deep research..."
            elif mode == "ideate":
                system = SYSTEM_IDEATE
                request_text = (
                    f'Generate practical and novel research ideas for "{request.message}". '
                    "Include feasibility and likely pitfalls."
                )
                status_text = "Generating research ideas..."
            else:
                system = (
                    "You are Cascade, an AI research assistant. You help researchers "
                    "find papers, analyze literature, trace citation graphs, identify "
                    "research gaps, and write academic text. Be precise, cite specific "
                    "details, and write in clear academic prose. Use markdown formatting."
                )
                request_text = f"User question: {request.message}"
                status_text = "Thinking..."

            prompt_parts.append(request_text)
            prompt = "\n\n---\n\n".join(prompt_parts)

            yield _sse("status", {"text": status_text, "tool": "llm"})

            for chunk in stream_ask(prompt, system=system):
                yield _sse("chunk", {"content": chunk})

            yield _sse("done", {})

    except Exception as e:
        log.exception("Chat stream error")
        yield _sse("error", {"message": str(e)})


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        _stream_chat(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

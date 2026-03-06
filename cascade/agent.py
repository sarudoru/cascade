"""LLM-native agent shell — translates natural language to tool calls.

Uses OpenAI or Anthropic function-calling APIs to interpret user queries
and dispatch them to the appropriate Cascade actions (search, read, cascade, etc.).
Slash commands remain as a power-user fallback.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Generator

from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel

from cascade.config import get_settings
from cascade.exceptions import ConfigError, LLMError

log = logging.getLogger(__name__)
console = Console()


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for academic papers across multiple sources (arXiv, Semantic Scholar, OpenAlex, DBLP, GitHub).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for academic papers"},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["arxiv", "scholar", "openalex", "dblp", "github"]},
                        "description": "Which sources to search. Defaults to arxiv + scholar.",
                    },
                    "limit": {"type": "integer", "description": "Max results per source (default 10)", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_paper",
            "description": "Read and summarize a paper from a URL (arXiv, Semantic Scholar, PDF link, or web page).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL of the paper to read"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_gaps",
            "description": "Identify research gaps and open problems in a given topic area.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Research topic to analyze for gaps"},
                    "limit": {"type": "integer", "description": "Number of papers to consider", "default": 5},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "literature_review",
            "description": "Generate a literature review on a topic, synthesizing key papers and themes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic for the literature review"},
                    "limit": {"type": "integer", "description": "Number of papers to include", "default": 10},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ideate",
            "description": "Brainstorm novel research ideas for a given problem or topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem or topic to brainstorm ideas for"},
                    "num_ideas": {"type": "integer", "description": "Number of ideas to generate", "default": 5},
                },
                "required": ["problem"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_section",
            "description": "Write a section of an academic paper (abstract, introduction, methods, results, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "description": "Section type: abstract, introduction, methods, results, discussion, conclusion"},
                    "topic": {"type": "string", "description": "Topic or title of the paper"},
                    "context": {"type": "string", "description": "Additional context or notes for the section"},
                },
                "required": ["section", "topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_feedback",
            "description": "Get critical peer-review-style feedback on a piece of academic text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The academic text to review"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cascade_crawl",
            "description": "Spider a citation graph from a seed paper, finding all papers that cite it and all papers it references. Builds an interactive visualization.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper": {"type": "string", "description": "Paper URL, arXiv ID, DOI, or Semantic Scholar ID"},
                    "depth": {"type": "integer", "description": "BFS depth (default 2)", "default": 2},
                    "max_papers": {"type": "integer", "description": "Max papers to collect (default 200)", "default": 200},
                    "direction": {"type": "string", "enum": ["both", "citations", "references"], "description": "Crawl direction", "default": "both"},
                },
                "required": ["paper"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_researchers",
            "description": "Browse the researcher co-authorship network. List top researchers, show a researcher's papers, or find co-authors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "show", "coauthors", "search"], "description": "What to do"},
                    "name": {"type": "string", "description": "Researcher name (for show/coauthors)"},
                    "query": {"type": "string", "description": "Search query (for search action)"},
                    "limit": {"type": "integer", "description": "Max results", "default": 20},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_citations",
            "description": "Find papers that cite a given paper.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "S2 paper ID or arXiv ID"},
                    "limit": {"type": "integer", "description": "Max citations to show", "default": 10},
                },
                "required": ["paper_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_related",
            "description": "Find papers similar/related to a given paper using Semantic Scholar recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "S2 paper ID or arXiv ID"},
                    "limit": {"type": "integer", "description": "Max results", "default": 5},
                },
                "required": ["paper_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_paper",
            "description": "Open a paper in the user's default browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Paper URL or ID to open"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_bibtex",
            "description": "Export saved papers as a BibTeX file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Filter papers by query (optional)"},
                    "output": {"type": "string", "description": "Output file path", "default": "papers.bib"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_query",
            "description": "Search the research memory (saved papers and insights).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["stats", "papers", "insights", "search"], "description": "What to query"},
                    "query": {"type": "string", "description": "Search query (for search action)"},
                },
                "required": ["action"],
            },
        },
    },
]

# Anthropic-format tools (converted on the fly)
def _to_anthropic_tools() -> list[dict]:
    """Convert OpenAI-format tools to Anthropic format."""
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "input_schema": t["function"]["parameters"],
        }
        for t in TOOLS
    ]


# ---------------------------------------------------------------------------
# Tool dispatch — maps tool names to shell command handlers
# ---------------------------------------------------------------------------

def _build_tool_args(name: str, params: dict) -> str:
    """Convert tool call params into the string args format expected by _cmd_* handlers."""
    if name == "search":
        parts = [params.get("query", "")]
        for src in params.get("sources", []):
            parts.append(f"--{src}")
        if params.get("limit"):
            parts.extend(["-n", str(params["limit"])])
        return " ".join(parts)

    elif name == "read_paper":
        return params.get("url", "")

    elif name == "find_gaps":
        args = params.get("topic", "")
        if params.get("limit"):
            args += f" -n {params['limit']}"
        return args

    elif name == "literature_review":
        args = params.get("topic", "")
        if params.get("limit"):
            args += f" -n {params['limit']}"
        return args

    elif name == "ideate":
        args = params.get("problem", "")
        if params.get("num_ideas"):
            args += f" -n {params['num_ideas']}"
        return args

    elif name == "write_section":
        args = params.get("section", "")
        if params.get("topic"):
            args += f" --topic {params['topic']}"
        if params.get("context"):
            args += f" --context {params['context']}"
        return args

    elif name == "get_feedback":
        return params.get("text", "")

    elif name == "cascade_crawl":
        parts = [params.get("paper", "")]
        if params.get("depth"):
            parts.extend(["--depth", str(params["depth"])])
        if params.get("max_papers"):
            parts.extend(["--max-papers", str(params["max_papers"])])
        if params.get("direction"):
            parts.extend(["--direction", params["direction"]])
        return " ".join(parts)

    elif name == "show_researchers":
        parts = [params.get("action", "list")]
        if params.get("name"):
            parts.extend(["--name", params["name"]])
        if params.get("query"):
            parts.extend(["--query", params["query"]])
        if params.get("limit"):
            parts.extend(["--limit", str(params["limit"])])
        return " ".join(parts)

    elif name == "get_citations":
        args = params.get("paper_id", "")
        if params.get("limit"):
            args += f" -n {params['limit']}"
        return args

    elif name == "find_related":
        args = params.get("paper_id", "")
        if params.get("limit"):
            args += f" -n {params['limit']}"
        return args

    elif name == "open_paper":
        return params.get("url", "")

    elif name == "export_bibtex":
        parts = ["bibtex"]
        if params.get("query"):
            parts.extend(["-q", params["query"]])
        if params.get("output"):
            parts.extend(["-o", params["output"]])
        return " ".join(parts)

    elif name == "memory_query":
        parts = [params.get("action", "stats")]
        if params.get("query"):
            parts.extend(["--query", params["query"]])
        return " ".join(parts)

    return ""


# Map tool names → shell command handler names
TOOL_TO_CMD = {
    "search": "_cmd_search",
    "read_paper": "_cmd_read",
    "find_gaps": "_cmd_gaps",
    "literature_review": "_cmd_review",
    "ideate": "_cmd_ideate",
    "write_section": "_cmd_write",
    "get_feedback": "_cmd_feedback",
    "cascade_crawl": "_cmd_cascade",
    "show_researchers": "_cmd_researchers",
    "get_citations": "_cmd_cite",
    "find_related": "_cmd_related",
    "open_paper": "_cmd_open",
    "export_bibtex": "_cmd_export",
    "memory_query": "_cmd_memory",
}


# ---------------------------------------------------------------------------
# Agent Shell
# ---------------------------------------------------------------------------

AGENT_SYSTEM = """You are Cascade, an AI-powered research assistant. You help researchers find papers, \
analyze literature, trace citation graphs, identify research gaps, and write academic text.

You have access to tools that can:
- Search for papers across arXiv, Semantic Scholar, OpenAlex, DBLP, and GitHub
- Read and summarize papers from URLs
- Identify research gaps in a topic
- Write literature reviews
- Brainstorm research ideas
- Write paper sections (intro, methods, etc.)
- Give peer-review feedback
- Spider citation graphs from a seed paper
- Browse a network of researchers and co-authors
- Get citations and related papers
- Export to BibTeX
- Search the research memory

When the user asks something that requires one of these tools, use it. When they ask a general \
knowledge question, answer directly without using tools. Be concise and helpful.

IMPORTANT: When using a tool, always call it. Do not describe what you would do — actually do it."""


class AgentShell:
    """LLM-native agent that translates natural language to tool calls."""

    def __init__(self, commands: dict[str, Any]):
        """commands: the COMMANDS dict from shell.py mapping names to handler fns."""
        self._commands = commands

    def run(self, user_input: str, conversation: list[dict[str, str]]) -> str | None:
        """Process user input through the LLM agent.

        Returns:
            - None if the agent called tools (output already printed)
            - str if the agent responded with text (to be displayed)
        """
        s = get_settings()
        provider = s.default_llm

        messages = self._build_messages(user_input, conversation)

        if provider == "openai":
            return self._run_openai(messages)
        else:
            return self._run_anthropic(messages)

    def _build_messages(self, user_input: str, conversation: list[dict[str, str]]) -> list[dict]:
        """Build message history for the LLM."""
        messages = [{"role": "system", "content": AGENT_SYSTEM}]

        # Add recent conversation for context (last 6 turns)
        for msg in conversation[-(6 * 2):]:
            messages.append({"role": msg["role"], "content": msg["content"][:1000]})

        messages.append({"role": "user", "content": user_input})
        return messages

    def _run_openai(self, messages: list[dict]) -> str | None:
        """Execute via OpenAI function calling."""
        from openai import OpenAI

        s = get_settings()
        if not s.openai_api_key:
            raise ConfigError("OPENAI_API_KEY is not set.")

        client = OpenAI(api_key=s.openai_api_key)

        try:
            resp = client.chat.completions.create(
                model=s.openai_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=4096,
            )
        except Exception as e:
            raise LLMError(f"OpenAI agent call failed: {e}") from e

        choice = resp.choices[0]

        # If the model wants to call tools
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                name = tc.function.name
                try:
                    params = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    params = {}

                self._execute_tool(name, params)
            return None

        # Plain text response
        return choice.message.content or ""

    def _run_anthropic(self, messages: list[dict]) -> str | None:
        """Execute via Anthropic tool use."""
        import anthropic

        s = get_settings()
        if not s.anthropic_api_key:
            raise ConfigError("ANTHROPIC_API_KEY is not set.")

        client = anthropic.Anthropic(api_key=s.anthropic_api_key)

        # Separate system from messages for Anthropic
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else AGENT_SYSTEM
        chat_messages = [m for m in messages if m["role"] != "system"]

        try:
            resp = client.messages.create(
                model=s.claude_model,
                system=system,
                messages=chat_messages,
                tools=_to_anthropic_tools(),
                max_tokens=4096,
                temperature=0.3,
            )
        except Exception as e:
            raise LLMError(f"Anthropic agent call failed: {e}") from e

        # Process response blocks
        text_parts: list[str] = []
        tool_called = False

        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_called = True
                self._execute_tool(block.name, block.input)

        if tool_called:
            # If there was pre-tool text, display it
            if text_parts:
                pre_text = "\n".join(text_parts)
                console.print(Markdown(pre_text))
            return None

        return "\n".join(text_parts)

    def _execute_tool(self, name: str, params: dict) -> None:
        """Dispatch a tool call to the corresponding _cmd_* handler."""
        cmd_name = TOOL_TO_CMD.get(name)
        if not cmd_name:
            console.print(f"[yellow]Unknown tool: {name}[/yellow]")
            return

        handler = self._commands.get(f"/{cmd_name.replace('_cmd_', '')}")
        if not handler:
            console.print(f"[yellow]No handler for tool: {name}[/yellow]")
            return

        args = _build_tool_args(name, params)

        console.print(f"\n[dim]⚡ {name}({', '.join(f'{k}={v!r}' for k, v in params.items())})[/dim]")

        try:
            handler(args)
        except Exception as e:
            log.exception("Tool '%s' failed with args: %s", name, args)
            console.print(f"[red]Tool error ({name}): {e}[/red]")
            console.print(f"[dim]Full traceback written to ~/.cascade/cascade.log[/dim]")

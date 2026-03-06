<p align="center">
  <img src=".github/banner.png" alt="Cascade" width="600" />
</p>

<p align="center">
  <em>AI-powered research intelligence — web-native</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-coming_soon-c9a55a?style=flat-square&labelColor=0a0a0a" alt="Status: Coming Soon" />
  <img src="https://img.shields.io/badge/python-≥3.10-c9a55a?style=flat-square&labelColor=0a0a0a&logo=python&logoColor=c9a55a" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/next.js-15-c9a55a?style=flat-square&labelColor=0a0a0a&logo=nextdotjs&logoColor=c9a55a" alt="Next.js" />
  <img src="https://img.shields.io/badge/license-MIT-c9a55a?style=flat-square&labelColor=0a0a0a" alt="License: MIT" />
</p>

---

<br />

<h3 align="center">🚧&nbsp;&nbsp;Coming Soon&nbsp;&nbsp;🚧</h3>

<p align="center">
  Cascade is being built in the open. <br />
  Star this repo to get notified when it launches.
</p>

<br />

---

## What is Cascade?

**Cascade** is a web-native research intelligence platform that helps researchers navigate the academic landscape with AI. Think of it as a research copilot that reads, connects, and synthesizes papers — so you can focus on the ideas that matter.

<br />

### ✦ &nbsp; Core Capabilities

| | Feature | Description |
|---|---|---|
| 🔍 | **Deep Research** | Ask complex research questions and receive comprehensive, citation-backed answers synthesized from the literature |
| 🕸️ | **Citation Graph Explorer** | Visualize paper relationships through interactive force-directed graphs — trace influence, find clusters, discover hidden connections |
| 📄 | **Paper Reader** | Drop any arXiv link, DOI, or PDF — Cascade extracts, summarizes, and lets you interrogate the full text |
| 📚 | **Literature Reviews** | Generate structured literature reviews with gap analysis, trend identification, and research opportunity mapping |
| 🧠 | **Persistent Memory** | Every paper you explore is remembered — building a personal knowledge graph that grows with your research |

<br />

### ✦ &nbsp; Architecture

```
cascade/
├── cascade/            # Python backend
│   ├── agent.py        # LLM-powered research agent
│   ├── engine.py       # Core orchestration engine
│   ├── graph.py        # Citation graph builder (NetworkX)
│   ├── reader.py       # Paper extraction (arXiv, PDF, web)
│   ├── semantic.py     # Semantic Scholar integration
│   ├── memory.py       # SQLite + ChromaDB persistence
│   ├── api/            # FastAPI endpoints
│   └── search/         # Multi-source academic search
│
├── web/                # Next.js frontend
│   └── src/
│       ├── app/        # Editorial brutalism UI
│       └── components/ # Graph view, input, streaming
│
└── tests/              # Test suite
```

<br />

### ✦ &nbsp; Built With

<p>
  <img src="https://img.shields.io/badge/FastAPI-0a0a0a?style=for-the-badge&logo=fastapi&logoColor=c9a55a" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js-0a0a0a?style=for-the-badge&logo=nextdotjs&logoColor=c9a55a" alt="Next.js" />
  <img src="https://img.shields.io/badge/OpenAI-0a0a0a?style=for-the-badge&logo=openai&logoColor=c9a55a" alt="OpenAI" />
  <img src="https://img.shields.io/badge/Anthropic-0a0a0a?style=for-the-badge&logo=anthropic&logoColor=c9a55a" alt="Anthropic" />
  <img src="https://img.shields.io/badge/D3.js-0a0a0a?style=for-the-badge&logo=d3dotjs&logoColor=c9a55a" alt="D3.js" />
  <img src="https://img.shields.io/badge/ChromaDB-0a0a0a?style=for-the-badge&logo=databricks&logoColor=c9a55a" alt="ChromaDB" />
</p>

<br />

### ✦ &nbsp; Design Philosophy

Cascade's interface follows an **editorial brutalism** aesthetic — the precision of a typeset research journal meets the power of a modern research instrument. Built with [Cormorant Garamond](https://fonts.google.com/specimen/Cormorant+Garamond) for display and [JetBrains Mono](https://www.jetbrains.com/lp/mono/) for code, against a dark palette with warm amber accents.

<br />

---

<p align="center">
  <sub>Built by <a href="https://github.com/sarudoru">Sardor Nodirov</a></sub>
</p>

<p align="center">
  <sub>© 2026 Sardor Nodirov. All rights reserved.</sub>
</p>

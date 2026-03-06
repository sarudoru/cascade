  Cascade: Comprehensive Analysis & Feature Roadmap

  Current State Assessment

  Cascade is a ~2,300-line Python CLI at v0.1.0 with a solid foundation: multi-source search
  (arXiv, Semantic Scholar, GitHub), LLM-powered research intelligence (review, gaps, ideation),
  paper section drafting with dual-LLM feedback, persistent SQLite memory, and Obsidian vault
  export. The architecture is clean and well-modularized. Here's what's needed to make it
  production-grade.

  ---
  1. PDF Full-Text Processing (Critical Gap)

  The tool currently works only with abstracts (truncated to 200-500 chars in context). A real
  research assistant must read papers.

  - cascade read <arxiv-id|url|path> — Download and parse full PDFs via PyMuPDF / pdfplumber,
  extract sections (abstract, intro, methods, results), and store structured full-text in memory
  - Automatic PDF download — When a paper is found via search, optionally fetch and cache the PDF
  in ~/.cascade/pdfs/
  - Chunked embedding of full-text for semantic retrieval (see #6 below)
  - cascade summarize <paper> — Generate a structured summary from the full paper, not just the
  abstract
  - Table/figure extraction — Parse tables from PDFs into structured data for comparison across
  papers

  ---
  2. Citation Graph & Bibliometric Analysis

  get_citations() and get_references() exist in semantic_scholar.py but are never called from any
  command.

  - cascade cite <paper-id> — Show citation tree (who cites this, what this cites), with depth
  control
  - cascade trace <topic> — Build a citation graph across a set of papers; identify seminal works,
  emerging clusters, and bridge papers
  - Influence metrics — h-index of key authors, citation velocity (citations/year), field-weighted
  citation impact
  - "Snowball" search — Given a seed paper, recursively expand via references and citations to
  discover the full research neighborhood
  - Citation network visualization — Export to DOT/GraphViz or interactive HTML (via pyvis) showing
   paper clusters and influence flows
  - BibTeX export — cascade export bibtex <query|collection> generating proper .bib files from
  stored papers

  ---
  3. Search & Discovery Improvements

  - DBLP integration — Add cascade/search/dblp_search.py for venue-aware search (find all papers
  from CVPR 2024 on motion generation)
  - OpenAlex integration — Free, open bibliometric database with richer metadata than Semantic
  Scholar
  - Date-range filtering — --since 2023 / --year 2020-2024 flags on all search commands (Semantic
  Scholar supports this already but it's not exposed in the CLI)
  - Venue filtering — --venue "NeurIPS" to restrict to specific conferences/journals
  - Sort options — --sort citations|date|relevance across all sources
  - Semantic search — Use embeddings to find papers similar to a given abstract/description, not
  just keyword matching
  - "Related papers" — Given a paper ID, find conceptually similar work (using S2's recommendations
   API)
  - Search result ranking — Combine citation count, recency, and relevance into a unified ranking
  score across sources
  - Saved searches / alerts — cascade watch "topic" to track new papers on a topic (daily/weekly
  digest)

  ---
  4. Project & Collection Management

  Currently there's no concept of a "project" — everything is global.

  - cascade project create <name> — Create isolated research projects with their own vault, paper
  collections, and notes
  - cascade project list / cascade project switch <name> — Manage and switch between projects
  - Reading lists — cascade list create "survey-papers" → curated, ordered paper collections with
  read/unread status, priority, and personal notes
  - Paper tagging — cascade tag <paper-id> "important" "to-read" "baseline" — user-defined tags
  beyond auto-inferred domain tags
  - Paper annotations — Store per-paper notes, key takeaways, methodology critiques linked to
  specific papers
  - Export — cascade export <project> --format latex|markdown|html for sharing curated collections

  ---
  5. Advanced Writing Pipeline

  The current write command produces isolated sections. A real paper needs coherent multi-section
  orchestration.

  - cascade draft init --topic "..." --type conference|journal|workshop — Initialize a full paper
  project with all sections, managing inter-section consistency
  - Iterative refinement — cascade write refine <section> --feedback "make the intro more
  compelling" — revise existing drafts with specific feedback
  - Cross-section coherence — When drafting methods, automatically reference the claims made in the
   introduction; when drafting experiments, verify they test the contributions listed in the intro
  - LaTeX export — cascade export latex <draft-dir> producing a compilable .tex file with a chosen
  template (NeurIPS, CVPR, ACL, ICML)
  - Rebuttal drafting — cascade rebuttal <reviews-file> — parse reviewer comments and draft
  point-by-point responses with suggested paper edits
  - Diff view — Show what changed between draft revisions with tracked changes
  - Plagiarism/overlap check — Compare drafted text against stored papers' abstracts to flag
  unintentional similarity
  - Reference management — Auto-generate \cite{} commands and maintain a .bib file synchronized
  with the vault

  ---
  6. Semantic Memory & RAG (Retrieval-Augmented Generation)

  The current memory is keyword-based (LIKE %query%). This is inadequate for nuanced research
  queries.

  - Vector embeddings — Embed paper abstracts (and full-texts from #1) using text-embedding-3-small
   or voyage-3 and store in a local vector store (chromadb, lancedb, or sqlite-vec)
  - Hybrid search — Combine keyword (BM25) and semantic (vector) search for memory retrieval
  - Smarter context building — Replace the current build_context() with RAG: retrieve the top-K
  most semantically relevant papers/insights for each LLM prompt
  - Concept graph — Extract and store key concepts, methods, datasets, and metrics from papers;
  build a knowledge graph of relationships
  - Memory deduplication — The current INSERT OR IGNORE by URL misses duplicates across sources
  (same paper on arXiv and S2 has different URLs) 
  - Memory pruning — cascade memory prune --older-than 1y / --low-relevance to manage database
  growth

  ---
  7. Domain Generalization

  Currently hardcoded to two domains (CV Motion Gen + NLP Mech Interp). This must be
  user-configurable.

  - cascade domain add <name> — Interactive wizard to define keywords, arXiv categories, and tags
  for a new domain
  - cascade domain remove <name> / cascade domain list
  - YAML-based domain config — Move domain definitions from config.py to ~/.cascade/domains.yaml so
   users can edit them without touching source code
  - Domain auto-detection — Given a query, infer which domain(s) it belongs to and automatically
  apply the right categories/keywords
  - Multi-discipline support — Physics, biology, medicine, social science — each with appropriate
  source databases (PubMed, SSRN, etc.)

  ---
  8. CLI / UX Polish

  - cascade init — First-run setup wizard: configure API keys, choose domains, set vault path,
  verify connectivity
  - cascade status — Dashboard showing: papers in memory, active projects, recent sessions, API key
   health, disk usage
  - Progress bars — Replace bare spinners with rich.progress showing actual progress (e.g.,
  "Fetching paper 3/15...")
  - Async/concurrent search — Search arXiv and Semantic Scholar simultaneously using asyncio +
  httpx instead of sequentially (current design blocks on each source)
  - Pagination — --page flag or interactive "load more" for search results beyond the limit
  - Interactive selection — After search results, let the user select papers interactively
  (checkbox UI via rich or questionary) for saving, reading, or adding to a collection
  - cascade open <paper-id> — Open the paper URL or PDF in the system browser
  - Output format flag — --format json|table|markdown|csv for all commands, enabling piping into
  other tools
  - Shell completions — Generate and install Zsh/Bash/Fish completions (Typer supports this
  natively but it's disabled with add_completion=False)
  - Color themes — --no-color flag and configurable color schemes for accessibility
  - Command aliasing — cascade s for search, cascade r for review, etc.

  ---
  9. Testing & Reliability

  The codebase has zero tests. This is the single biggest gap for production use.

  - Unit tests — Test each module in isolation: Paper dataclass, Memory CRUD, _frontmatter(),
  _papers_to_context(), config loading
  - Integration tests — Test search → memory → obsidian pipeline with mocked API responses
  - LLM tests — Snapshot/golden tests for prompt construction; ensure prompts contain expected
  context
  - CLI tests — Use typer.testing.CliRunner to test every command with mocked backends
  - Fixtures — Factory functions for Paper, Repo objects; in-memory SQLite for memory tests
  - CI/CD — GitHub Actions workflow: lint (ruff), type-check (mypy), test (pytest), coverage
  - Error handling — The current except Exception: pass in save_paper() silently swallows errors.
  Add proper logging with structlog or logging
  - Retry logic — Exponential backoff for API calls (arXiv has it, S2 and GitHub don't)
  - Rate limiting — Centralized rate limiter instead of scattered time.sleep() calls
  - Input validation — Validate section names, provider names, action names using Typer Enum
  choices instead of string matching

  ---
  10. Robustness & Architecture

  - Proper error hierarchy — Define CascadeError, SearchError, LLMError, MemoryError exception
  classes instead of catching bare Exception
  - Connection pooling — Use requests.Session() for HTTP clients (S2, GitHub) instead of creating
  new connections per request
  - Database migrations — Use alembic or a lightweight migration system so schema changes don't
  break existing databases
  - Context manager for Memory — The Memory class opens a connection but close() is never called.
  Use __enter__/__exit__
  - Deduplication improvement — Current dedup is by URL (misses cross-source duplicates) and by
  title case-insensitive (brittle). Add DOI-based and arXiv-ID-based dedup
  - Token budget management — The LLM prompts naively concatenate paper abstracts without tracking
  token counts. Add a token counter to stay within model context limits and truncate intelligently
  - Caching layer — Cache search results for identical queries within a configurable TTL (avoid
  hitting APIs for repeated queries during a session)
  - Configuration validation — On startup, verify API keys are valid (make a test API call) rather
  than failing at command time

  ---
  11. Advanced Research Features

  - Methodology extraction — Parse papers to extract: datasets used, metrics reported, model
  architectures, training details → build a structured comparison database
  - Trend analysis — cascade trends "topic" --years 2020-2025 — show publication volume, key
  authors, emerging subtopics over time using S2 data
  - Author profiling — cascade author "Name" — show publications, h-index, co-author network,
  research trajectory
  - Conference tracker — cascade venue CVPR 2025 — list accepted papers, key themes, best paper
  awards
  - Experiment tracker integration — Link to W&B / MLflow to connect literature review with actual
  experiment results
  - Paper comparison — cascade compare <paper1> <paper2> — structured side-by-side comparison of
  methods, results, and contributions
  - Research timeline —  timeline "topic" — chronological view of key milestones and
  breakthroughs
  - Hypothesis generation — Go beyond ideation to generate testable hypotheses with expected
  outcomes and null hypotheses

  ---
  12. Collaboration & Sharing

  - Export to Notion / Google Docs — API integrations for team-based research
  - Shared vaults — Git-backed Obsidian vault for team collaboration
  - Annotated bibliography export — Generate formatted annotated bibliographies for coursework or
  grant proposals
  - Research report generation — cascade report <project> — compile all reviews, gaps, ideas, and
  drafts into a coherent research report

  ---
  13. Security & Packaging

  - API key encryption — Store keys in system keyring (keyring package) instead of plaintext .env
  - PyPI publishing — pip install cascade with proper versioning and changelog
  - Docker image — For reproducible environments
  - Homebrew formula — For macOS users: brew install cascade
  - Update checker — Notify users when a new version is available

  ---
  Priority Ranking

  ┌──────────┬────────────────────────────┬───────────────────────────────────────────┬────────┐
  │ Priority │          Feature           │                  Impact                   │ Effort │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P0       │ Testing infrastructure     │ Foundation for everything else            │ Medium │
  │          │ (#9)                       │                                           │        │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P0       │ Error handling & logging   │ Currently silently fails                  │ Low    │
  │          │ (#10)                      │                                           │        │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P0       │ Domain generalization (#7) │ Removes hardcoded limitations             │ Low    │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P1       │ PDF full-text processing   │ Transforms from abstract-reader to        │ High   │
  │          │ (#1)                       │ paper-reader                              │        │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P1       │ Citation graph & unused    │ Unlocks existing dead code + core         │ Medium │
  │          │ API (#2)                   │ research workflow                         │        │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P1       │ Semantic memory / RAG (#6) │ Dramatically improves context quality     │ Medium │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P1       │ Token budget management    │ Prevents silent truncation/failures       │ Low    │
  │          │ (#10)                      │                                           │        │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P2       │ Search improvements (#3)   │ Better paper discovery                    │ Medium │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P2       │ Project management (#4)    │ Multi-project research workflows          │ Medium │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P2       │ Advanced writing pipeline  │ End-to-end paper writing                  │ High   │
  │          │ (#5)                       │                                           │        │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P2       │ CLI/UX polish (#8)         │ Better day-to-day experience              │ Medium │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P3       │ Advanced research features │ Power-user workflows                      │ High   │
  │          │  (#11)                     │                                           │        │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P3       │ Collaboration (#12)        │ Team research                             │ High   │
  ├──────────┼────────────────────────────┼───────────────────────────────────────────┼────────┤
  │ P3       │ Packaging & distribution   │ Wider adoption                            │ Medium │
  │          │ (#13)                      │                                           │        │
  └──────────┴────────────────────────────┴───────────────────────────────────────────┴────────┘

  The biggest architectural insight: cascade currently operates at the abstract level — it searches
   abstracts, feeds abstracts to LLMs, and stores abstracts. The single most transformative upgrade
   is making it work with full paper text via PDF processing + vector embeddings, which would
  cascade improvements through every command.
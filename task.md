# Cascade: CLI → Web-Native Transition

## Phase 1: Planning & Design
- [x] Explore existing codebase structure
- [x] Understand backend modules and capabilities
- [x] Generate design mockup for the main interface
- [/] Write implementation plan
- [ ] Get user approval on implementation plan

## Phase 2: Backend — FastAPI Server
- [ ] Create FastAPI app with WebSocket support for streaming
- [ ] Build API routes: `/api/chat`, `/api/graph`, `/api/search`, `/api/papers`
- [ ] Wire existing engine/agent/graph modules to API endpoints
- [ ] Add SSE or WebSocket streaming for long-running LLM operations

## Phase 3: Frontend — Main Landing Page
- [ ] Design system: CSS variables, typography (Cormorant Garamond + JetBrains Mono), colors
- [ ] Build the central input area with auto-detect (link vs. question)
- [ ] Action mode pills (Graph Explorer, Deep Research, Literature Review)
- [ ] Implement streaming response display with markdown rendering

## Phase 4: Citation Graph Visualization
- [ ] Interactive graph renderer using D3.js force-directed layout
- [ ] Node detail panel (paper info, abstract, links)
- [ ] Graph controls (depth, zoom, filter)
- [ ] Graph export functionality

## Phase 5: Conversation Interface
- [ ] Streaming chat UI with LLM responses
- [ ] Paper cards inline (search results, related papers)
- [ ] Research artifacts display (gap analysis, lit review, ideation)

## Phase 6: Remove CLI
- [ ] Remove [cli.py](file:///Users/sardor/Desktop/Projects/cascade/cascade/cli.py) and [shell.py](file:///Users/sardor/Desktop/Projects/cascade/cascade/shell.py)
- [ ] Update [pyproject.toml](file:///Users/sardor/Desktop/Projects/cascade/pyproject.toml) to remove CLI entrypoint
- [ ] Add web server entrypoint

## Phase 7: Verification
- [ ] Verify API endpoints work
- [ ] Browser testing of the complete flow
- [ ] Verify graph visualization

"""FastAPI server — web-native API for Cascade research assistant."""

from __future__ import annotations

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cascade.api.chat import router as chat_router
from cascade.api.graph import router as graph_router
from cascade.api.search import router as search_router
from cascade.api.papers import router as papers_router

log = logging.getLogger(__name__)

app = FastAPI(
    title="Cascade",
    description="AI-powered research intelligence API",
    version="0.3.0",
)

# CORS — allow the Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(chat_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(papers_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}


def main():
    """Entry point for `cascade` command."""
    uvicorn.run(
        "cascade.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()

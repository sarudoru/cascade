"""Configuration management for Cascade."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Load .env from project root (or cwd) so keys are always available
# ---------------------------------------------------------------------------
_CASCADE_HOME = Path(os.getenv("CASCADE_HOME", str(Path.home() / ".cascade")))

_ENV_LOCATIONS = [
    Path.cwd() / ".env",
    Path(__file__).resolve().parent.parent / ".env",
    _CASCADE_HOME / ".env",
]

for _p in _ENV_LOCATIONS:
    if _p.exists():
        load_dotenv(_p)
        break


# ---------------------------------------------------------------------------
# Domain management (loaded from YAML — see domains.py)
# ---------------------------------------------------------------------------

from cascade.domains import load_domains as _load_domains  # noqa: E402

DOMAINS: dict = _load_domains()


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------

class Settings(BaseModel):
    """Global application settings loaded from env vars."""

    # API keys
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    github_token: str = Field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    semantic_scholar_api_key: str = Field(
        default_factory=lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    )

    # LLM defaults
    openai_model: str = Field(default="gpt-5.2")
    claude_model: str = Field(default="claude-opus-4-6")
    default_llm: str = Field(default="claude")  # "openai" | "claude"

    # Paths
    vault_path: Path = Field(
        default_factory=lambda: Path(
            os.getenv("CASCADE_VAULT_PATH", str(Path.cwd() / "vault"))
        )
    )
    db_path: Path = Field(
        default_factory=lambda: _CASCADE_HOME / "memory.db"
    )
    chroma_path: Path = Field(
        default_factory=lambda: _CASCADE_HOME / "chroma"
    )

    # Search defaults
    default_search_limit: int = 10

    # Embeddings
    embedding_model: str = Field(default="text-embedding-3-large")

    # Active domains
    active_domains: list[str] = Field(default=["cv-motion", "nlp-interp"])

    def get_domain_keywords(self) -> list[str]:
        """Return combined keyword list for all active domains."""
        kws: list[str] = []
        for d in self.active_domains:
            if d in DOMAINS:
                kws.extend(DOMAINS[d]["keywords"])
        return kws

    def get_arxiv_categories(self) -> list[str]:
        """Return combined arXiv category list."""
        cats: list[str] = []
        for d in self.active_domains:
            if d in DOMAINS:
                cats.extend(DOMAINS[d]["arxiv_categories"])
        return list(set(cats))

    def ensure_dirs(self) -> None:
        """Create necessary directories."""
        self.vault_path.mkdir(parents=True, exist_ok=True)
        for sub in ["papers", "reviews", "ideas", "drafts"]:
            (self.vault_path / sub).mkdir(exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Return a Settings instance (cached at module level)."""
    return _SETTINGS


_SETTINGS = Settings()

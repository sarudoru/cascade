"""GitHub REST API wrapper for searching code repositories."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from cascade.config import get_settings
from cascade.exceptions import SearchError

log = logging.getLogger(__name__)


@dataclass
class Repo:
    """Normalised GitHub repository representation."""

    name: str
    full_name: str
    description: str
    url: str
    stars: int
    language: str | None
    topics: list[str]
    last_updated: str
    forks: int
    open_issues: int

    @property
    def badge(self) -> str:
        return f"⭐ {self.stars}"


GITHUB_API = "https://api.github.com"

# Persistent HTTP session for connection pooling
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Return a shared HTTP session (connection-pooled)."""
    global _session
    if _session is None:
        _session = requests.Session()
    _session.headers.update(_headers())
    return _session


def _headers() -> dict[str, str]:
    """Build request headers with optional auth token."""
    h = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "cascade-research-assistant",
    }
    s = get_settings()
    if s.github_token:
        h["Authorization"] = f"token {s.github_token}"
    return h


def search_repos(
    query: str,
    max_results: int | None = None,
    language: str | None = None,
    sort: str = "stars",
    min_stars: int = 0,
) -> list[Repo]:
    """Search GitHub repositories.

    Parameters
    ----------
    query : str
        Search keywords.
    max_results : int, optional
        Maximum repos to return (capped at 100 per GitHub).
    language : str, optional
        Filter by programming language, e.g. "python".
    sort : str
        Sort by "stars", "forks", or "updated".
    min_stars : int
        Minimum star count filter.
    """
    s = get_settings()
    limit = min(max_results or s.default_search_limit, 100)

    # Build qualified query
    q_parts = [query]
    if language:
        q_parts.append(f"language:{language}")
    if min_stars > 0:
        q_parts.append(f"stars:>={min_stars}")
    q = " ".join(q_parts)

    try:
        session = _get_session()
        resp = session.get(
            f"{GITHUB_API}/search/repositories",
            params={
                "q": q,
                "sort": sort,
                "order": "desc",
                "per_page": limit,
            },
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise SearchError(f"GitHub API request failed: {e}") from e

    data = resp.json()

    repos: list[Repo] = []
    for item in data.get("items", []):
        repos.append(
            Repo(
                name=item.get("name", ""),
                full_name=item.get("full_name", ""),
                description=item.get("description") or "",
                url=item.get("html_url", ""),
                stars=item.get("stargazers_count", 0),
                language=item.get("language"),
                topics=item.get("topics", []),
                last_updated=item.get("updated_at", ""),
                forks=item.get("forks_count", 0),
                open_issues=item.get("open_issues_count", 0),
            )
        )

    return repos


def search_code_repos(
    query: str,
    max_results: int | None = None,
) -> list[Repo]:
    """Search for research code repos — prioritises Python repos with stars."""
    return search_repos(
        query=query,
        max_results=max_results,
        language="python",
        sort="stars",
        min_stars=5,
    )

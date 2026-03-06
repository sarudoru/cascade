"""Domain management — load, save, and manage research domains.

Domains are stored in ``~/.cascade/domains.yaml`` and define the keyword sets,
arXiv categories, and Obsidian tags used for domain-specific search filtering.
On first run, built-in defaults are written to the YAML file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cascade.exceptions import ConfigError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in defaults (written when no YAML file exists yet)
# ---------------------------------------------------------------------------

_BUILTIN_DOMAINS: dict[str, dict[str, Any]] = {
    "cv-motion": {
        "name": "Computer Vision — Human Motion Generation",
        "keywords": [
            "human motion generation",
            "motion synthesis",
            "motion diffusion",
            "skeletal animation",
            "action-conditioned motion",
            "text-to-motion",
            "motion capture",
            "pose estimation",
            "human dynamics",
            "motion prediction",
        ],
        "arxiv_categories": ["cs.CV", "cs.GR", "cs.LG"],
        "tags": ["#research/cv/motion-gen"],
    },
    "nlp-interp": {
        "name": "NLP — Mechanistic Interpretability",
        "keywords": [
            "mechanistic interpretability",
            "circuit analysis",
            "superposition",
            "feature visualization",
            "sparse autoencoders",
            "probing",
            "attention heads",
            "residual stream",
            "polysemanticity",
            "activation patching",
            "transformer circuits",
        ],
        "arxiv_categories": ["cs.CL", "cs.LG", "cs.AI"],
        "tags": ["#research/nlp/mech-interp"],
    },
}


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _default_path() -> Path:
    """Return the default domains YAML path (~/.cascade/domains.yaml)."""
    return Path.home() / ".cascade" / "domains.yaml"


def load_domains(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load domains from YAML, falling back to built-in defaults.

    If the YAML file does not exist, the built-in defaults are written
    to disk and returned.
    """
    filepath = path or _default_path()

    if not filepath.exists():
        log.info("No domains.yaml found — writing built-in defaults to %s", filepath)
        save_domains(_BUILTIN_DOMAINS, filepath)
        return dict(_BUILTIN_DOMAINS)

    try:
        import yaml

        text = filepath.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            log.warning("domains.yaml has unexpected format, using defaults")
            return dict(_BUILTIN_DOMAINS)
        return data
    except ImportError:
        raise ConfigError(
            "pyyaml is required for domain management. Install it: pip install pyyaml"
        )
    except Exception as e:
        log.error("Failed to load domains.yaml: %s", e)
        return dict(_BUILTIN_DOMAINS)


def save_domains(
    domains: dict[str, dict[str, Any]], path: Path | None = None
) -> None:
    """Write domains to the YAML file."""
    filepath = path or _default_path()
    filepath.parent.mkdir(parents=True, exist_ok=True)

    try:
        import yaml

        filepath.write_text(
            yaml.dump(domains, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    except ImportError:
        raise ConfigError(
            "pyyaml is required for domain management. Install it: pip install pyyaml"
        )


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def add_domain(
    name: str,
    display_name: str,
    keywords: list[str],
    arxiv_categories: list[str] | None = None,
    tags: list[str] | None = None,
    path: Path | None = None,
) -> None:
    """Add a new domain (or overwrite an existing one)."""
    domains = load_domains(path)
    domains[name] = {
        "name": display_name,
        "keywords": keywords,
        "arxiv_categories": arxiv_categories or [],
        "tags": tags or [f"#research/{name}"],
    }
    save_domains(domains, path)
    log.info("Added domain '%s'", name)


def remove_domain(name: str, path: Path | None = None) -> bool:
    """Remove a domain by key. Returns True if it existed."""
    domains = load_domains(path)
    if name not in domains:
        return False
    del domains[name]
    save_domains(domains, path)
    log.info("Removed domain '%s'", name)
    return True


def list_domains(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return all configured domains."""
    return load_domains(path)

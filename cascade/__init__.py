"""Cascade — AI-powered research intelligence."""

__version__ = "0.1.0"

import logging
import os
from pathlib import Path

_data_root = Path(os.getenv("CASCADE_HOME", str(Path.home() / ".cascade")))
_handlers: list[logging.Handler]
_log_file = _data_root / "cascade.log"

try:
    _data_root.mkdir(parents=True, exist_ok=True)
    _handlers = [logging.FileHandler(_log_file, encoding="utf-8")]
except OSError:
    # Fall back to stderr logging when filesystem writes are restricted.
    _handlers = [logging.StreamHandler()]

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_handlers,
)

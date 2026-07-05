"""
PDFQA Pipeline — Logging Configuration

Sets up dual-file + console logging:
  • logs/pipeline.log  — all events (INFO+)
  • logs/error.log     — errors only  (ERROR+)
  • console            — colorized, INFO+

Call ``setup_logging()`` once at application startup.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from config import PipelineConfig


# ---------------------------------------------------------------------------
# Custom colorized console formatter
# ---------------------------------------------------------------------------
class _ColorFormatter(logging.Formatter):
    """Adds ANSI colors to log-level names for console output."""

    _LEVEL_COLORS = {
        logging.DEBUG: "\033[36m",       # cyan
        logging.INFO: "\033[32m",        # green
        logging.WARNING: "\033[33m",     # yellow
        logging.ERROR: "\033[31m",       # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        color = self._LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname:<8}{self._RESET}"
        return super().format(record)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def setup_logging(cfg: Optional[PipelineConfig] = None) -> None:
    """Configure the root logger with file and console handlers.

    Safe to call multiple times — duplicate handlers are prevented.
    """
    if cfg is None:
        from config import CONFIG
        cfg = CONFIG

    cfg.ensure_directories()

    root = logging.getLogger()

    # Avoid adding handlers twice
    if root.handlers:
        return

    root.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt=cfg.log_format,
        datefmt=cfg.log_date_format,
    )

    # --- File handler: pipeline.log (all events) --------------------------
    pipeline_fh = logging.FileHandler(
        cfg.pipeline_log_path, encoding="utf-8",
    )
    pipeline_fh.setLevel(logging.INFO)
    pipeline_fh.setFormatter(formatter)
    root.addHandler(pipeline_fh)

    # --- File handler: error.log (errors only) ----------------------------
    error_fh = logging.FileHandler(
        cfg.error_log_path, encoding="utf-8",
    )
    error_fh.setLevel(logging.ERROR)
    error_fh.setFormatter(formatter)
    root.addHandler(error_fh)

    # --- Console handler (colorized) --------------------------------------
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        console.setFormatter(_ColorFormatter(
            fmt=cfg.log_format,
            datefmt=cfg.log_date_format,
        ))
    else:
        console.setFormatter(formatter)
    root.addHandler(console)

    root.info("Logging initialised — pipeline.log + error.log")


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger."""
    return logging.getLogger(name)

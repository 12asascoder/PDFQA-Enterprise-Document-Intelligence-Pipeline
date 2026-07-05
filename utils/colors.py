"""
PDFQA Pipeline — Terminal Color Utilities

Provides ANSI escape-code helpers for colorized, human-friendly
terminal output.  All helpers gracefully degrade to plain text when
the output stream is not a TTY.
"""

from __future__ import annotations

import os
import sys


# ---------------------------------------------------------------------------
# Auto-detect color support
# ---------------------------------------------------------------------------
def _supports_color() -> bool:
    """Return *True* when stdout is a real terminal that supports ANSI."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR_ENABLED: bool = _supports_color()


# ---------------------------------------------------------------------------
# ANSI constants
# ---------------------------------------------------------------------------
class _Ansi:
    """Raw ANSI escape codes."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


# Expose as module attribute
ANSI = _Ansi


# ---------------------------------------------------------------------------
# Color application helpers
# ---------------------------------------------------------------------------
def _wrap(code: str, text: str) -> str:
    if not _COLOR_ENABLED:
        return text
    return f"{code}{text}{ANSI.RESET}"


def bold(text: str) -> str:
    return _wrap(ANSI.BOLD, text)


def dim(text: str) -> str:
    return _wrap(ANSI.DIM, text)


def red(text: str) -> str:
    return _wrap(ANSI.RED, text)


def green(text: str) -> str:
    return _wrap(ANSI.GREEN, text)


def yellow(text: str) -> str:
    return _wrap(ANSI.YELLOW, text)


def blue(text: str) -> str:
    return _wrap(ANSI.BLUE, text)


def cyan(text: str) -> str:
    return _wrap(ANSI.CYAN, text)


def magenta(text: str) -> str:
    return _wrap(ANSI.MAGENTA, text)


def bright_green(text: str) -> str:
    return _wrap(ANSI.BRIGHT_GREEN, text)


def bright_red(text: str) -> str:
    return _wrap(ANSI.BRIGHT_RED, text)


def bright_cyan(text: str) -> str:
    return _wrap(ANSI.BRIGHT_CYAN, text)


def bright_yellow(text: str) -> str:
    return _wrap(ANSI.BRIGHT_YELLOW, text)


# ---------------------------------------------------------------------------
# Semantic helpers (used in pipeline output)
# ---------------------------------------------------------------------------
def success(text: str) -> str:
    """Green text with ✓ prefix."""
    return green(f"  ✓ {text}")


def error(text: str) -> str:
    """Red text with ✗ prefix."""
    return red(f"  ✗ {text}")


def warning(text: str) -> str:
    """Yellow text with ⚠ prefix."""
    return yellow(f"  ⚠ {text}")


def info(text: str) -> str:
    """Blue text with ℹ prefix."""
    return blue(f"  ℹ {text}")


def header(text: str) -> str:
    """Cyan bold text for section headers."""
    return _wrap(f"{ANSI.BOLD}{ANSI.CYAN}", text)


def separator(char: str = "=", width: int = 60) -> str:
    """Return a colorized separator line."""
    return cyan(char * width)


def worker_tag(worker_id: int) -> str:
    """Return a colorized worker tag like [Worker-1]."""
    return magenta(f"[Worker-{worker_id}]")


def controller_tag() -> str:
    """Return a colorized controller tag."""
    return bright_cyan("[Controller]")

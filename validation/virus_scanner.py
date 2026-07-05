"""
PDFQA Pipeline — Virus Scanner Abstraction

Provides a pluggable interface for virus scanning with a ClamAV
implementation and a no-op fallback for environments where ClamAV
is not installed.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of a virus scan."""
    clean: bool
    message: str


class BaseVirusScanner(ABC):
    """Abstract virus scanner interface."""

    @abstractmethod
    def scan(self, filepath: Path) -> ScanResult:
        """Scan *filepath* and return a ``ScanResult``."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if the scanner backend is reachable."""
        ...


class ClamAVScanner(BaseVirusScanner):
    """Virus scanner using ClamAV via ``pyclamd``."""

    def __init__(self) -> None:
        self._daemon = None
        try:
            import pyclamd  # type: ignore[import-untyped]
            self._daemon = pyclamd.ClamdUnixSocket()
            self._daemon.ping()
            logger.info("ClamAV daemon is available.")
        except Exception:
            self._daemon = None
            try:
                import pyclamd  # type: ignore[import-untyped]
                self._daemon = pyclamd.ClamdNetworkSocket()
                self._daemon.ping()
                logger.info("ClamAV network daemon is available.")
            except Exception:
                self._daemon = None

    def is_available(self) -> bool:
        return self._daemon is not None

    def scan(self, filepath: Path) -> ScanResult:
        if self._daemon is None:
            return ScanResult(
                clean=True,
                message="ClamAV unavailable — skipped",
            )
        try:
            result = self._daemon.scan_file(str(filepath))
            if result is None:
                return ScanResult(clean=True, message="Clean")
            # result is a dict like {filepath: ('FOUND', 'virus_name')}
            status = list(result.values())[0]
            if status[0] == "FOUND":
                return ScanResult(
                    clean=False,
                    message=f"Virus detected: {status[1]}",
                )
            return ScanResult(clean=True, message="Clean")
        except Exception as exc:
            logger.warning("ClamAV scan error for %s: %s", filepath.name, exc)
            return ScanResult(
                clean=True,
                message=f"Scan error (treated as clean): {exc}",
            )


class NoOpScanner(BaseVirusScanner):
    """Fallback scanner that always reports clean."""

    def is_available(self) -> bool:
        return True

    def scan(self, filepath: Path) -> ScanResult:
        return ScanResult(clean=True, message="Virus scan disabled/skipped")


def create_virus_scanner(enabled: bool = True) -> BaseVirusScanner:
    """Factory: return a ClamAV scanner if available, else NoOp.

    Parameters
    ----------
    enabled : bool
        If ``False``, always return :class:`NoOpScanner`.
    """
    if not enabled:
        logger.info("Virus scanning disabled via config.")
        return NoOpScanner()

    scanner = ClamAVScanner()
    if scanner.is_available():
        return scanner

    logger.warning(
        "ClamAV is not available — virus scanning will be skipped.  "
        "Install ClamAV (clamd) for full protection."
    )
    return NoOpScanner()

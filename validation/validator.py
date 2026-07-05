"""
PDFQA Pipeline — Document Validation Service

Every PDF must pass through a 10-check validation pipeline before it
is accepted for extraction.  Any single failure causes the file to be
skipped (processing continues with the next file).

Checks
------
1.  MIME type validation       (python-magic)
2.  Extension validation       (pathlib)
3.  File size validation       (os.stat)
4.  Readability check          (open + read)
5.  Permission validation      (os.access)
6.  Encryption detection       (PyMuPDF)
7.  Corruption detection       (PyMuPDF page iteration)
8.  SHA-256 duplicate detection (in-memory hash set)
9.  Virus scanning abstraction (ClamAV / NoOp)
10. Result logging
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import fitz  # type: ignore[import-untyped]  # PyMuPDF

try:
    import magic  # type: ignore[import-untyped]
    _HAS_MAGIC = True
except ImportError:
    _HAS_MAGIC = False

from config import PipelineConfig
from utils.file_utils import compute_sha256
from validation.virus_scanner import BaseVirusScanner, create_virus_scanner

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    """Outcome of a single validation check."""
    name: str
    passed: bool
    message: str = ""


@dataclass
class ValidationResult:
    """Aggregated result for one PDF file."""
    filepath: Path
    passed: bool
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def failed_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed]

    @property
    def summary(self) -> str:
        failed = self.failed_checks
        if not failed:
            return "All checks passed"
        names = ", ".join(c.name for c in failed)
        return f"Failed: {names}"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
class DocumentValidator:
    """Run a configurable 10-check pipeline on a PDF file.

    Thread-safe: the SHA-256 duplicate registry is protected by a lock.
    """

    def __init__(self, cfg: PipelineConfig) -> None:
        self._cfg = cfg
        self._hash_registry: Set[str] = set()
        self._hash_lock = threading.Lock()
        self._scanner: BaseVirusScanner = create_virus_scanner(
            enabled=cfg.virus_scan_enabled,
        )

    def validate(self, filepath: Path) -> ValidationResult:
        """Run all checks on *filepath* and return a :class:`ValidationResult`."""
        checks: List[CheckResult] = []

        # 1. MIME type
        checks.append(self._check_mime(filepath))
        # 2. Extension
        checks.append(self._check_extension(filepath))
        # 3. File size
        checks.append(self._check_size(filepath))
        # 4. Readability
        checks.append(self._check_readable(filepath))
        # 5. Permissions
        checks.append(self._check_permissions(filepath))

        # Short-circuit: if the file can't even be opened, skip deeper checks
        if not all(c.passed for c in checks):
            return ValidationResult(
                filepath=filepath,
                passed=False,
                checks=checks,
            )

        # 6. Encryption
        checks.append(self._check_encryption(filepath))
        # 7. Corruption
        checks.append(self._check_corruption(filepath))
        # 8. SHA-256 duplicate
        checks.append(self._check_duplicate(filepath))
        # 9. Virus scan
        checks.append(self._check_virus(filepath))

        passed = all(c.passed for c in checks)

        # 10. Log everything
        self._log_result(filepath, checks, passed)

        return ValidationResult(
            filepath=filepath,
            passed=passed,
            checks=checks,
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------
    def _check_mime(self, filepath: Path) -> CheckResult:
        name = "MIME type"
        if not _HAS_MAGIC:
            logger.debug("python-magic not available; MIME check skipped")
            return CheckResult(name, True, "python-magic unavailable — skipped")
        try:
            mime = magic.from_file(str(filepath), mime=True)
            if mime in self._cfg.valid_mime_types:
                return CheckResult(name, True, f"MIME: {mime}")
            return CheckResult(name, False, f"Invalid MIME: {mime}")
        except Exception as exc:
            return CheckResult(name, False, f"MIME check error: {exc}")

    def _check_extension(self, filepath: Path) -> CheckResult:
        name = "Extension"
        ext = filepath.suffix.lower()
        if ext in self._cfg.valid_extensions:
            return CheckResult(name, True, f"Extension: {ext}")
        return CheckResult(name, False, f"Invalid extension: {ext}")

    def _check_size(self, filepath: Path) -> CheckResult:
        name = "File size"
        try:
            size = filepath.stat().st_size
            if size < self._cfg.min_file_size_bytes:
                return CheckResult(
                    name, False,
                    f"Too small: {size} bytes (min {self._cfg.min_file_size_bytes})",
                )
            if size > self._cfg.max_file_size_bytes:
                return CheckResult(
                    name, False,
                    f"Too large: {size} bytes (max {self._cfg.max_file_size_bytes})",
                )
            return CheckResult(name, True, f"Size OK: {size} bytes")
        except OSError as exc:
            return CheckResult(name, False, f"Size check failed: {exc}")

    def _check_readable(self, filepath: Path) -> CheckResult:
        name = "Readability"
        try:
            with open(filepath, "rb") as fh:
                header_bytes = fh.read(1024)
            if header_bytes:
                return CheckResult(name, True, "File is readable")
            return CheckResult(name, False, "File is empty")
        except Exception as exc:
            return CheckResult(name, False, f"Cannot read file: {exc}")

    def _check_permissions(self, filepath: Path) -> CheckResult:
        name = "Permissions"
        if os.access(filepath, os.R_OK):
            return CheckResult(name, True, "Read permission OK")
        return CheckResult(name, False, "No read permission")

    def _check_encryption(self, filepath: Path) -> CheckResult:
        name = "Encryption"
        try:
            doc = fitz.open(str(filepath))
            encrypted = doc.is_encrypted
            doc.close()
            if encrypted:
                return CheckResult(name, False, "PDF is encrypted")
            return CheckResult(name, True, "Not encrypted")
        except Exception as exc:
            return CheckResult(name, False, f"Encryption check error: {exc}")

    def _check_corruption(self, filepath: Path) -> CheckResult:
        name = "Corruption"
        try:
            doc = fitz.open(str(filepath))
            page_count = len(doc)
            if page_count == 0:
                doc.close()
                return CheckResult(name, False, "PDF has 0 pages")
            # Try to access every page to detect corruption
            for page in doc:
                _ = page.number
            doc.close()
            return CheckResult(name, True, f"Valid — {page_count} pages")
        except Exception as exc:
            return CheckResult(name, False, f"Corrupt PDF: {exc}")

    def _check_duplicate(self, filepath: Path) -> CheckResult:
        name = "Duplicate (SHA-256)"
        try:
            digest = compute_sha256(filepath)
            with self._hash_lock:
                if digest in self._hash_registry:
                    return CheckResult(
                        name, False,
                        f"Duplicate detected: {digest[:16]}…",
                    )
                self._hash_registry.add(digest)
            return CheckResult(name, True, f"Unique: {digest[:16]}…")
        except Exception as exc:
            return CheckResult(name, False, f"Hash error: {exc}")

    def _check_virus(self, filepath: Path) -> CheckResult:
        name = "Virus scan"
        result = self._scanner.scan(filepath)
        return CheckResult(name, result.clean, result.message)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    @staticmethod
    def _log_result(
        filepath: Path,
        checks: List[CheckResult],
        passed: bool,
    ) -> None:
        level = logging.INFO if passed else logging.WARNING
        details = " | ".join(
            f"{c.name}:{'✓' if c.passed else '✗'}" for c in checks
        )
        logger.log(
            level,
            "Validation %s — %s — %s",
            "PASSED" if passed else "FAILED",
            filepath.name,
            details,
        )

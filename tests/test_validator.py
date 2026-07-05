"""
Tests for the DocumentValidator.

Uses temporary PDF files (valid and intentionally broken) to exercise
each of the 10 validation checks.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PipelineConfig
from validation.validator import DocumentValidator, ValidationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def cfg(tmp_path: Path) -> PipelineConfig:
    """Config with temp directories."""
    return PipelineConfig(
        project_root=tmp_path,
        dataset_dir=tmp_path / "dataset",
        extracted_dir=tmp_path / "extracted",
        logs_dir=tmp_path / "logs",
        virus_scan_enabled=False,  # no ClamAV in CI
    )


@pytest.fixture
def validator(cfg: PipelineConfig) -> DocumentValidator:
    cfg.ensure_directories()
    return DocumentValidator(cfg)


def _create_minimal_pdf(path: Path) -> Path:
    """Write a minimal valid PDF to *path*."""
    # Minimal valid PDF (1 blank page)
    try:
        import fitz
        doc = fitz.open()
        doc.new_page()
        doc.save(str(path))
        doc.close()
    except ImportError:
        # Fallback: write raw minimal PDF bytes
        pdf_bytes = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n"
            b"0000000009 00000 n \n0000000058 00000 n \n"
            b"0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\n"
            b"startxref\n190\n%%EOF\n"
        )
        path.write_bytes(pdf_bytes)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestDocumentValidator:
    """Test the 10-check validation pipeline."""

    def test_valid_pdf_passes(self, validator: DocumentValidator, tmp_path: Path):
        """A minimal valid PDF should pass all checks."""
        pdf = _create_minimal_pdf(tmp_path / "valid.pdf")
        result = validator.validate(pdf)
        assert result.passed, f"Valid PDF failed: {result.summary}"

    def test_invalid_extension(self, validator: DocumentValidator, tmp_path: Path):
        """A file with .txt extension should fail the extension check."""
        txt = tmp_path / "notapdf.txt"
        txt.write_text("Hello")
        result = validator.validate(txt)
        assert not result.passed
        failed_names = [c.name for c in result.failed_checks]
        assert "Extension" in failed_names

    def test_empty_file(self, validator: DocumentValidator, tmp_path: Path):
        """A 0-byte PDF should fail the size check."""
        pdf = tmp_path / "empty.pdf"
        pdf.write_bytes(b"")
        result = validator.validate(pdf)
        assert not result.passed

    def test_oversized_file(self, validator: DocumentValidator, tmp_path: Path, cfg: PipelineConfig):
        """A file larger than max_file_size should fail."""
        pdf = tmp_path / "big.pdf"
        # Write a file that exceeds max (we'll set a tiny max for testing)
        small_cfg = PipelineConfig(
            project_root=cfg.project_root,
            dataset_dir=cfg.dataset_dir,
            extracted_dir=cfg.extracted_dir,
            logs_dir=cfg.logs_dir,
            max_file_size_bytes=100,
            virus_scan_enabled=False,
        )
        small_validator = DocumentValidator(small_cfg)
        _create_minimal_pdf(pdf)
        result = small_validator.validate(pdf)
        # It should either fail on size or pass if the minimal pdf is < 100 bytes
        # Minimal PDF from fitz is > 100 bytes, so it should fail
        if pdf.stat().st_size > 100:
            assert not result.passed

    def test_duplicate_detection(self, validator: DocumentValidator, tmp_path: Path):
        """Two identical PDFs should trigger duplicate detection."""
        pdf1 = _create_minimal_pdf(tmp_path / "dup1.pdf")
        pdf2 = tmp_path / "dup2.pdf"
        pdf2.write_bytes(pdf1.read_bytes())

        r1 = validator.validate(pdf1)
        assert r1.passed

        r2 = validator.validate(pdf2)
        assert not r2.passed
        failed_names = [c.name for c in r2.failed_checks]
        assert "Duplicate (SHA-256)" in failed_names

    def test_corrupted_pdf(self, validator: DocumentValidator, tmp_path: Path):
        """Garbage bytes should fail corruption/MIME checks."""
        pdf = tmp_path / "corrupt.pdf"
        pdf.write_bytes(b"this is not a pdf at all 12345")
        result = validator.validate(pdf)
        assert not result.passed

    def test_permissions_check(self, validator: DocumentValidator, tmp_path: Path):
        """An unreadable file should fail the permissions check."""
        pdf = _create_minimal_pdf(tmp_path / "noperm.pdf")
        os.chmod(pdf, 0o000)
        try:
            result = validator.validate(pdf)
            assert not result.passed
        finally:
            os.chmod(pdf, 0o644)  # restore for cleanup

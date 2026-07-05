"""
Tests for the HybridExtractor — verifies pdfplumber-first / OCR-fallback logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PipelineConfig
from extraction.hybrid_extractor import HybridExtractor, ExtractionResult


@pytest.fixture
def cfg(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        project_root=tmp_path,
        dataset_dir=tmp_path / "dataset",
        extracted_dir=tmp_path / "extracted",
        logs_dir=tmp_path / "logs",
    )


def _create_text_pdf(path: Path, text: str = "Hello World") -> Path:
    """Create a PDF with selectable text using PyMuPDF."""
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
        doc.save(str(path))
        doc.close()
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not installed")
    return path


def _create_blank_pdf(path: Path, pages: int = 1) -> Path:
    """Create a PDF with blank (no text) pages."""
    try:
        import fitz
        doc = fitz.open()
        for _ in range(pages):
            doc.new_page()
        doc.save(str(path))
        doc.close()
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not installed")
    return path


class TestHybridExtractor:
    """Test the hybrid pdfplumber-first / OCR-fallback extraction logic."""

    def test_pdfplumber_extracts_text(self, cfg: PipelineConfig, tmp_path: Path):
        """A text-based PDF should be extracted via pdfplumber."""
        cfg.ensure_directories()
        pdf = _create_text_pdf(tmp_path / "text.pdf", "Test Document Content")
        extractor = HybridExtractor(cfg)
        result = extractor.extract(pdf)

        assert result.total_pages >= 1
        assert result.pdfplumber_pages >= 1
        assert "Test Document Content" in result.full_text

    def test_blank_pdf_triggers_ocr(self, cfg: PipelineConfig, tmp_path: Path):
        """A blank PDF page should trigger OCR fallback."""
        cfg.ensure_directories()
        pdf = _create_blank_pdf(tmp_path / "blank.pdf")
        extractor = HybridExtractor(cfg)
        result = extractor.extract(pdf)

        assert result.total_pages >= 1
        # The page should be recorded as OCR or empty
        for pr in result.pages:
            assert pr.method in ("ocr", "empty")

    def test_extraction_result_structure(self, cfg: PipelineConfig, tmp_path: Path):
        """ExtractionResult should have correct field types."""
        cfg.ensure_directories()
        pdf = _create_text_pdf(tmp_path / "struct.pdf")
        extractor = HybridExtractor(cfg)
        result = extractor.extract(pdf)

        assert isinstance(result, ExtractionResult)
        assert isinstance(result.filepath, Path)
        assert isinstance(result.pages, list)
        assert isinstance(result.full_text, str)
        assert result.duration_seconds >= 0

    def test_mixed_pages_use_hybrid(self, cfg: PipelineConfig, tmp_path: Path):
        """A PDF with both text and blank pages uses a mix of methods."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF (fitz) not installed")

        cfg.ensure_directories()
        pdf = tmp_path / "mixed.pdf"
        doc = fitz.open()
        # Page 0: text
        p0 = doc.new_page()
        p0.insert_text((72, 72), "Page with text", fontsize=12)
        # Page 1: blank
        doc.new_page()
        # Page 2: text
        p2 = doc.new_page()
        p2.insert_text((72, 72), "Another text page", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        extractor = HybridExtractor(cfg)
        result = extractor.extract(pdf)

        assert result.total_pages == 3
        assert result.pages[0].method == "pdfplumber"
        # Page 1 (blank) should attempt OCR or report empty
        assert result.pages[1].method in ("ocr", "empty")
        assert result.pages[2].method == "pdfplumber"

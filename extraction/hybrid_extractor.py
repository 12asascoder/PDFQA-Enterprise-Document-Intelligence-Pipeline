"""
PDFQA Pipeline — Hybrid Extraction Engine

Core extraction logic:

    for every page in the PDF:
        text = pdfplumber.extract_text(page)
        if text is None or text.strip() == "":
            text = OCR(page)
        merge all pages → final text

pdfplumber is ALWAYS tried first.  OCR activates ONLY when pdfplumber
returns ``None`` or empty text — on a **per-page** basis.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pdfplumber  # type: ignore[import-untyped]

from config import PipelineConfig
from ocr.ocr_engine import OCREngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class PageResult:
    """Extraction result for a single page."""
    page_number: int
    text: str
    method: str        # "pdfplumber" | "ocr" | "empty"
    has_text: bool = True


@dataclass
class ExtractionResult:
    """Aggregated extraction result for an entire PDF."""
    filepath: Path
    pages: List[PageResult] = field(default_factory=list)
    total_pages: int = 0
    pdfplumber_pages: int = 0
    ocr_pages: int = 0
    empty_pages: int = 0
    duration_seconds: float = 0.0

    @property
    def full_text(self) -> str:
        """Concatenate all page texts with page separators."""
        parts: List[str] = []
        for pr in self.pages:
            if pr.text.strip():
                parts.append(pr.text)
        return "\n\n".join(parts)

    @property
    def method_summary(self) -> str:
        return (
            f"pdfplumber={self.pdfplumber_pages}, "
            f"OCR={self.ocr_pages}, "
            f"empty={self.empty_pages}"
        )


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------
class HybridExtractor:
    """Intelligent per-page extraction: pdfplumber first, OCR fallback.

    Parameters
    ----------
    cfg : PipelineConfig
        Pipeline configuration.
    """

    def __init__(self, cfg: PipelineConfig) -> None:
        self._cfg = cfg
        self._ocr = OCREngine(cfg)

    def extract(self, pdf_path: Path) -> ExtractionResult:
        """Extract text from every page of *pdf_path*.

        Returns
        -------
        ExtractionResult
            Contains per-page text, method used, and statistics.
        """
        start = time.time()
        result = ExtractionResult(filepath=pdf_path)

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                result.total_pages = len(pdf.pages)
                logger.info(
                    "Extracting %s — %d pages",
                    pdf_path.name, result.total_pages,
                )

                for page_idx, page in enumerate(pdf.pages):
                    page_result = self._extract_page(
                        pdf_path, page, page_idx,
                    )
                    result.pages.append(page_result)

                    # Track stats
                    if page_result.method == "pdfplumber":
                        result.pdfplumber_pages += 1
                    elif page_result.method == "ocr":
                        result.ocr_pages += 1
                    else:
                        result.empty_pages += 1

        except Exception as exc:
            logger.error(
                "Extraction failed for %s: %s", pdf_path.name, exc,
            )

        result.duration_seconds = time.time() - start
        logger.info(
            "Extraction complete for %s — %s — %.1fs",
            pdf_path.name, result.method_summary, result.duration_seconds,
        )
        return result

    # ------------------------------------------------------------------
    # Per-page logic
    # ------------------------------------------------------------------
    def _extract_page(
        self,
        pdf_path: Path,
        page: pdfplumber.page.Page,
        page_idx: int,
    ) -> PageResult:
        """Try pdfplumber on *page*; fall back to OCR if empty."""

        # --- Step 1: Try pdfplumber (column-aware) --------------------
        try:
            text = self._extract_text_column_aware(page, page_idx, pdf_path.name)
        except Exception as exc:
            logger.debug(
                "pdfplumber error on page %d of %s: %s",
                page_idx, pdf_path.name, exc,
            )
            text = None

        if text is not None and text.strip():
            # pdfplumber succeeded — include any tables too
            table_text = self._extract_tables_from_page(page, page_idx, pdf_path.name)
            if table_text:
                text = text + "\n\n" + table_text
            return PageResult(
                page_number=page_idx,
                text=text,
                method="pdfplumber",
            )

        # --- Step 2: OCR fallback -------------------------------------
        logger.info(
            "No pdfplumber text on page %d of %s — switching to OCR",
            page_idx, pdf_path.name,
        )
        try:
            ocr_text = self._ocr.ocr_page(pdf_path, page_idx)
            if ocr_text and ocr_text.strip():
                return PageResult(
                    page_number=page_idx,
                    text=ocr_text,
                    method="ocr",
                )
        except Exception as exc:
            logger.warning(
                "OCR also failed for page %d of %s: %s",
                page_idx, pdf_path.name, exc,
            )

        # --- Step 3: Both failed — record as empty --------------------
        return PageResult(
            page_number=page_idx,
            text="",
            method="empty",
            has_text=False,
        )

    # ------------------------------------------------------------------
    # Column-aware text extraction
    # ------------------------------------------------------------------
    def _extract_text_column_aware(
        self,
        page: pdfplumber.page.Page,
        page_idx: int,
        filename: str,
    ) -> Optional[str]:
        """Extract text respecting multi-column layouts.

        Analyses character x-positions to detect a column gutter.  When a
        multi-column layout is found the page is cropped into left and right
        halves and each column's text is extracted independently, then
        concatenated in reading order (left first, then right).  For
        single-column pages the standard ``extract_text()`` is returned.
        """
        # Try to get character-level data for column detection
        try:
            chars = page.chars
        except Exception:
            chars = []

        if not chars:
            # No character data — fall back to default extraction
            return page.extract_text()

        # Collect all character x0 positions
        x0_positions = [float(c.get("x0", 0)) for c in chars if c.get("x0") is not None]
        if not x0_positions:
            return page.extract_text()

        # Determine the page width and find the column split point
        page_width = float(page.width)

        # Build a histogram of x0 positions in bins to find the gutter
        # The gutter is a region in the middle of the page with few characters
        num_bins = 100
        bin_width = page_width / num_bins
        bins = [0] * num_bins

        for x in x0_positions:
            bin_idx = min(int(x / bin_width), num_bins - 1)
            bins[bin_idx] += 1

        # Look for a gutter: a run of low-density bins in the middle third
        # of the page (between 25% and 75% of page width)
        middle_start = num_bins // 4
        middle_end = 3 * num_bins // 4

        # Calculate average density for reference
        total_chars = sum(bins)
        avg_density = total_chars / num_bins if num_bins > 0 else 0
        low_threshold = avg_density * 0.1  # bins with < 10% of avg are "empty"

        # Find the widest run of low-density bins in the middle region
        best_gutter_start = -1
        best_gutter_end = -1
        best_gutter_width = 0

        current_start = -1
        for i in range(middle_start, middle_end):
            if bins[i] <= low_threshold:
                if current_start == -1:
                    current_start = i
            else:
                if current_start != -1:
                    run_width = i - current_start
                    if run_width > best_gutter_width:
                        best_gutter_start = current_start
                        best_gutter_end = i
                        best_gutter_width = run_width
                    current_start = -1

        # Check if the final run extends to the end of the search region
        if current_start != -1:
            run_width = middle_end - current_start
            if run_width > best_gutter_width:
                best_gutter_start = current_start
                best_gutter_end = middle_end
                best_gutter_width = run_width

        # A gutter must span at least ~3% of the page width to be real
        min_gutter_bins = max(3, num_bins // 30)
        if best_gutter_width < min_gutter_bins:
            # No significant gutter found → single-column page
            return page.extract_text()

        # Calculate the split x-coordinate (middle of the gutter)
        split_x = (best_gutter_start + best_gutter_end) / 2 * bin_width

        logger.debug(
            "Multi-column detected on page %d of %s — split at x=%.1f",
            page_idx, filename, split_x,
        )

        # Crop left and right columns and extract text from each
        bbox = page.bbox  # (x0, top, x1, bottom)

        left_crop = page.crop((bbox[0], bbox[1], split_x, bbox[3]))
        right_crop = page.crop((split_x, bbox[1], bbox[2], bbox[3]))

        left_text = left_crop.extract_text() or ""
        right_text = right_crop.extract_text() or ""

        # Concatenate: left column first, then right column
        if left_text.strip() and right_text.strip():
            return left_text.strip() + "\n\n" + right_text.strip()
        elif left_text.strip():
            return left_text.strip()
        elif right_text.strip():
            return right_text.strip()
        else:
            return page.extract_text()

    # ------------------------------------------------------------------
    # Table extraction helper
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_tables_from_page(
        page: pdfplumber.page.Page,
        page_idx: int,
        filename: str,
    ) -> str:
        """Extract tables from a pdfplumber page and format as text."""
        try:
            tables = page.extract_tables()
            if not tables:
                return ""

            parts: List[str] = []
            for t_idx, table in enumerate(tables):
                if not table:
                    continue
                lines: List[str] = []
                lines.append(f"[Table {t_idx + 1} — Page {page_idx + 1}]")

                for row_idx, row in enumerate(table):
                    # Replace None cells with empty string
                    cleaned = [
                        (cell or "").replace("\n", " ").strip()
                        for cell in row
                    ]
                    if row_idx == 0:
                        # Treat first row as header
                        lines.append(" | ".join(cleaned))
                        lines.append("-" * 40)
                    else:
                        lines.append(" | ".join(cleaned))

                parts.append("\n".join(lines))

            return "\n\n".join(parts)

        except Exception as exc:
            logger.debug(
                "Table extraction failed for page %d of %s: %s",
                page_idx, filename, exc,
            )
            return ""

"""
PDFQA Pipeline — Layout Detector

Heuristic-based layout detection for PDF pages.  Identifies structural
elements such as headings, paragraphs, lists, tables, figures, columns,
headers, footers, and page numbers using character-level metadata from
pdfplumber and pattern-matching on extracted text.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

import pdfplumber  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


@dataclass
class LayoutElement:
    """A detected structural element on a page."""
    element_type: str          # heading, paragraph, list, table, figure, etc.
    page_number: int
    content_preview: str = ""  # first 80 chars of content
    confidence: float = 1.0    # 0.0–1.0


@dataclass
class PageLayout:
    """Layout analysis result for one page."""
    page_number: int
    elements: List[LayoutElement] = field(default_factory=list)
    has_tables: bool = False
    has_figures: bool = False
    has_columns: bool = False
    is_header_page: bool = False
    is_footer_page: bool = False
    has_page_number: bool = False

    @property
    def element_types(self) -> Set[str]:
        return {e.element_type for e in self.elements}


@dataclass
class DocumentLayout:
    """Layout analysis for the entire document."""
    filepath: Path
    pages: List[PageLayout] = field(default_factory=list)

    @property
    def summary(self) -> str:
        types: Set[str] = set()
        for p in self.pages:
            types.update(p.element_types)
        return f"Detected elements: {', '.join(sorted(types)) or 'none'}"


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
_RE_HEADING = re.compile(
    r"^(?:\d+\.?\s+)?[A-Z][A-Za-z\s:–—-]{3,80}$",
)
_RE_LIST_ITEM = re.compile(r"^\s*(?:[-•●▪◦▸►]|\d+[.)]\s|[a-z][.)]\s)")
_RE_PAGE_NUMBER = re.compile(
    r"^(?:\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*|Page\s+\d+.*)$",
    re.IGNORECASE,
)
_RE_FIGURE_REF = re.compile(
    r"(?:Figure|Fig\.?|Exhibit|Chart|Graph|Diagram)\s+\d+",
    re.IGNORECASE,
)


class LayoutDetector:
    """Detect layout elements in a PDF using heuristics."""

    def detect(self, pdf_path: Path) -> DocumentLayout:
        """Analyse every page and return a :class:`DocumentLayout`."""
        layout = DocumentLayout(filepath=pdf_path)

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    pl = self._analyse_page(page, page_idx)
                    layout.pages.append(pl)
        except Exception as exc:
            logger.error("Layout detection failed for %s: %s", pdf_path.name, exc)

        logger.info("Layout for %s: %s", pdf_path.name, layout.summary)
        return layout

    # ------------------------------------------------------------------
    # Page-level analysis
    # ------------------------------------------------------------------
    def _analyse_page(
        self,
        page: pdfplumber.page.Page,
        page_idx: int,
    ) -> PageLayout:
        pl = PageLayout(page_number=page_idx)

        text = page.extract_text() or ""
        lines = text.split("\n")

        # --- Detect tables ---
        try:
            tables = page.extract_tables()
            if tables:
                pl.has_tables = True
                for t_idx, _ in enumerate(tables):
                    pl.elements.append(LayoutElement(
                        "table", page_idx, f"Table {t_idx + 1}",
                    ))
        except Exception:
            pass

        # --- Detect figures (image objects) ---
        try:
            images = page.images
            if images:
                pl.has_figures = True
                pl.elements.append(LayoutElement(
                    "figure", page_idx,
                    f"{len(images)} image(s) detected",
                ))
        except Exception:
            pass

        # --- Detect figure references in text ---
        for line in lines:
            if _RE_FIGURE_REF.search(line):
                pl.elements.append(LayoutElement(
                    "figure_reference", page_idx,
                    line.strip()[:80],
                    confidence=0.8,
                ))

        # --- Line-level heuristics ---
        chars = []
        try:
            chars = page.chars or []
        except Exception:
            pass

        font_sizes: List[float] = []
        for ch in chars:
            if ch.get("size"):
                font_sizes.append(float(ch["size"]))
        median_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 12.0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Headings: larger font or pattern match
            if _RE_HEADING.match(stripped):
                pl.elements.append(LayoutElement(
                    "heading", page_idx, stripped[:80], 0.7,
                ))
            elif _RE_LIST_ITEM.match(stripped):
                pl.elements.append(LayoutElement(
                    "list_item", page_idx, stripped[:80],
                ))
            elif _RE_PAGE_NUMBER.match(stripped):
                pl.has_page_number = True
                pl.elements.append(LayoutElement(
                    "page_number", page_idx, stripped[:80],
                ))
            else:
                # Default to paragraph
                pl.elements.append(LayoutElement(
                    "paragraph", page_idx, stripped[:80], 0.6,
                ))

        # --- Header / footer detection ---
        if lines:
            first = lines[0].strip()
            last = lines[-1].strip()
            if len(first) < 80:
                pl.is_header_page = True
                pl.elements.append(LayoutElement("header", page_idx, first))
            if _RE_PAGE_NUMBER.match(last) or len(last) < 30:
                pl.is_footer_page = True
                pl.elements.append(LayoutElement("footer", page_idx, last))

        # --- Multi-column heuristic ---
        if chars:
            x_positions = sorted(set(int(c.get("x0", 0)) for c in chars))
            if len(x_positions) > 20:
                # Check for a gap in x-positions indicating columns
                gaps = [
                    x_positions[i + 1] - x_positions[i]
                    for i in range(len(x_positions) - 1)
                ]
                large_gaps = [g for g in gaps if g > 50]
                if large_gaps:
                    pl.has_columns = True
                    pl.elements.append(LayoutElement(
                        "multi_column", page_idx, "Columns detected",
                    ))

        return pl

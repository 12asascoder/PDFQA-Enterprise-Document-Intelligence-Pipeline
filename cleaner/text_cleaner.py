"""
PDFQA Pipeline — Text Cleaner

Post-extraction text normalisation to remove noise introduced by
pdfplumber or OCR.  Transformations applied:

1. Unicode normalisation (NFKC)
2. Remove repeated headers/footers (frequency analysis across pages)
3. Remove blank pages (< min_page_chars non-whitespace characters)
4. Fix OCR garbage (random symbol clusters, non-printable chars)
5. Fix broken words (hyphenated line-end splits)
6. Normalise extra whitespace
7. Remove page numbers at page boundaries
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from typing import List, Optional

from config import PipelineConfig

logger = logging.getLogger(__name__)


class TextCleaner:
    """Clean extracted text from PDFs.

    Parameters
    ----------
    cfg : PipelineConfig
        Pipeline configuration (``min_page_chars``, etc.).
    """

    def __init__(self, cfg: PipelineConfig) -> None:
        self._cfg = cfg

    def clean(self, raw_text: str, page_texts: Optional[List[str]] = None) -> str:
        """Apply the full cleaning pipeline.

        Parameters
        ----------
        raw_text : str
            The merged document text.
        page_texts : list[str] | None
            Optional list of per-page texts — used for header/footer
            frequency analysis.  If ``None``, the cleaner operates on
            *raw_text* only.
        """
        text = raw_text

        # 1. Unicode normalisation
        text = self._normalize_unicode(text)

        # 2. Remove repeated headers / footers
        if page_texts:
            text = self._remove_repeated_headers_footers(text, page_texts)

        # 3. Remove blank-page artifacts
        text = self._remove_blank_page_markers(text)

        # 4. Remove OCR garbage
        text = self._remove_ocr_garbage(text)

        # 5. Fix broken (hyphenated) words
        text = self._fix_broken_words(text)

        # 6. Normalise whitespace
        text = self._normalize_whitespace(text)

        # 7. Remove page numbers
        text = self._remove_page_numbers(text)

        return text.strip()

    # ------------------------------------------------------------------
    # Individual transformations
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_unicode(text: str) -> str:
        """Apply NFKC normalisation to unify code-point representations."""
        return unicodedata.normalize("NFKC", text)

    def _remove_repeated_headers_footers(
        self,
        text: str,
        page_texts: List[str],
    ) -> str:
        """Detect lines that appear on many pages and strip them.

        A line is considered a header/footer candidate if it appears on
        more than 40 % of pages (minimum 3 pages).
        """
        if len(page_texts) < 3:
            return text

        first_lines: Counter[str] = Counter()
        last_lines: Counter[str] = Counter()

        for pt in page_texts:
            lines = pt.strip().split("\n")
            if lines:
                fl = lines[0].strip()
                if fl:
                    first_lines[fl] += 1
                ll = lines[-1].strip()
                if ll:
                    last_lines[ll] += 1

        threshold = max(3, int(len(page_texts) * 0.4))

        to_remove = set()
        for line, count in first_lines.items():
            if count >= threshold:
                to_remove.add(line)
        for line, count in last_lines.items():
            if count >= threshold:
                to_remove.add(line)

        if not to_remove:
            return text

        logger.debug(
            "Removing %d repeated header/footer patterns", len(to_remove),
        )
        out_lines = []
        for line in text.split("\n"):
            if line.strip() not in to_remove:
                out_lines.append(line)
        return "\n".join(out_lines)

    def _remove_blank_page_markers(self, text: str) -> str:
        """Remove stretches of whitespace-only content between pages."""
        # Collapse runs of 3+ newlines (likely blank pages) into 2
        return re.sub(r"\n{4,}", "\n\n\n", text)

    @staticmethod
    def _remove_ocr_garbage(text: str) -> str:
        """Strip non-printable characters and symbol clusters."""
        # Remove control characters (except newline, tab, carriage return)
        text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", text)

        # Remove clusters of 3+ consecutive special characters
        text = re.sub(r"[^\w\s.,;:!?'\"-]{3,}", " ", text)

        return text

    @staticmethod
    def _fix_broken_words(text: str) -> str:
        """Rejoin words split across lines by hyphens.

        ``pro-\\ngramming`` → ``programming``
        """
        return re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Collapse multiple spaces/tabs into single spaces per line."""
        lines = text.split("\n")
        normalised = []
        for line in lines:
            cleaned = re.sub(r"[ \t]+", " ", line).strip()
            normalised.append(cleaned)
        return "\n".join(normalised)

    @staticmethod
    def _remove_page_numbers(text: str) -> str:
        """Remove standalone page-number lines."""
        page_num_re = re.compile(
            r"^\s*(?:[-–—]?\s*\d{1,4}\s*[-–—]?|[Pp]age\s+\d+\s*(?:of\s+\d+)?)\s*$",
        )
        lines = text.split("\n")
        return "\n".join(
            line for line in lines if not page_num_re.match(line)
        )

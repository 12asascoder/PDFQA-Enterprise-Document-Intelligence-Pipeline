"""
PDFQA Pipeline — Standalone Table Extractor

Extracts tables from a full PDF using pdfplumber and formats them
as readable text preserving rows, columns, and headers.  This module
can be used independently or as a complement to the hybrid extractor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pdfplumber  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


@dataclass
class TableData:
    """Parsed table from a PDF page."""
    page_number: int
    table_index: int
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)

    @property
    def formatted(self) -> str:
        """Return a plain-text representation of the table."""
        lines: List[str] = []
        lines.append(
            f"[Table {self.table_index + 1} — Page {self.page_number + 1}]"
        )
        if self.headers:
            lines.append(" | ".join(self.headers))
            lines.append("-" * max(40, len(lines[-1])))
        for row in self.rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)


class TableExtractor:
    """Extract all tables from a PDF document.

    Uses ``pdfplumber.page.extract_tables()`` for each page.
    """

    def extract_all(self, pdf_path: Path) -> List[TableData]:
        """Return every table found in *pdf_path*."""
        all_tables: List[TableData] = []

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    tables = self._extract_page_tables(page, page_idx)
                    all_tables.extend(tables)
        except Exception as exc:
            logger.error(
                "Table extraction failed for %s: %s", pdf_path.name, exc,
            )

        logger.info(
            "Found %d tables in %s", len(all_tables), pdf_path.name,
        )
        return all_tables

    @staticmethod
    def _extract_page_tables(
        page: pdfplumber.page.Page,
        page_idx: int,
    ) -> List[TableData]:
        """Extract tables from a single page."""
        try:
            raw_tables = page.extract_tables()
            if not raw_tables:
                return []
        except Exception:
            return []

        results: List[TableData] = []
        for t_idx, raw in enumerate(raw_tables):
            if not raw or len(raw) < 1:
                continue

            # Clean cells
            cleaned = [
                [(cell or "").replace("\n", " ").strip() for cell in row]
                for row in raw
            ]

            headers = cleaned[0] if cleaned else []
            rows = cleaned[1:] if len(cleaned) > 1 else []

            results.append(TableData(
                page_number=page_idx,
                table_index=t_idx,
                headers=headers,
                rows=rows,
            ))

        return results

    @staticmethod
    def tables_to_text(tables: List[TableData]) -> str:
        """Concatenate all tables into a single text block."""
        if not tables:
            return ""
        return "\n\n".join(t.formatted for t in tables)

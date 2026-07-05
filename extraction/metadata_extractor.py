"""
PDFQA Pipeline — Metadata Extractor

Extracts document-level metadata (title, author, creation date, etc.)
from PDF files using PyMuPDF.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz  # type: ignore[import-untyped]  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class DocumentMetadata:
    """Structured PDF metadata."""
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    creator: str = ""
    producer: str = ""
    creation_date: str = ""
    modification_date: str = ""
    page_count: int = 0
    file_size_bytes: int = 0

    @property
    def header_text(self) -> str:
        """Format metadata as a text block suitable for prepending to output."""
        lines = ["--- Document Metadata ---"]
        if self.title:
            lines.append(f"Title: {self.title}")
        if self.author:
            lines.append(f"Author: {self.author}")
        if self.subject:
            lines.append(f"Subject: {self.subject}")
        if self.keywords:
            lines.append(f"Keywords: {self.keywords}")
        if self.creation_date:
            lines.append(f"Created: {self.creation_date}")
        lines.append(f"Pages: {self.page_count}")
        lines.append("--- End Metadata ---")
        return "\n".join(lines)


class MetadataExtractor:
    """Extract metadata from a PDF using PyMuPDF (fitz)."""

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Return :class:`DocumentMetadata` for *pdf_path*."""
        meta = DocumentMetadata()

        try:

            doc = fitz.open(str(pdf_path))
            info = doc.metadata or {}

            meta.title = info.get("title", "") or ""
            meta.author = info.get("author", "") or ""
            meta.subject = info.get("subject", "") or ""
            meta.keywords = info.get("keywords", "") or ""
            meta.creator = info.get("creator", "") or ""
            meta.producer = info.get("producer", "") or ""
            meta.creation_date = info.get("creationDate", "") or ""
            meta.modification_date = info.get("modDate", "") or ""
            meta.page_count = len(doc)
            meta.file_size_bytes = pdf_path.stat().st_size

            doc.close()
            logger.debug("Metadata for %s: title=%r, pages=%d",
                         pdf_path.name, meta.title, meta.page_count)

        except Exception as exc:
            logger.warning(
                "Metadata extraction failed for %s: %s",
                pdf_path.name, exc,
            )
            try:
                meta.file_size_bytes = pdf_path.stat().st_size
            except OSError:
                pass

        return meta

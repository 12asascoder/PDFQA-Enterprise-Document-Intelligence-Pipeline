"""
PDFQA Pipeline — OCR Engine

Converts specific PDF pages to images, preprocesses them with OpenCV,
and runs Tesseract OCR to produce text.  Only pages that pdfplumber
fails to extract are sent through this path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pytesseract  # type: ignore[import-untyped]
from pdf2image import convert_from_path  # type: ignore[import-untyped]
from PIL import Image

from config import PipelineConfig
from ocr.image_preprocessor import ImagePreprocessor

logger = logging.getLogger(__name__)


class OCREngine:
    """Tesseract-based OCR with OpenCV preprocessing.

    Parameters
    ----------
    cfg : PipelineConfig
        Pipeline configuration (DPI, language, timeout).
    """

    def __init__(self, cfg: PipelineConfig) -> None:
        self._cfg = cfg
        self._preprocessor = ImagePreprocessor()

    def ocr_page(self, pdf_path: Path, page_number: int) -> str:
        """OCR a single page of *pdf_path* (0-indexed).

        Workflow:
        1. Convert page → PIL Image via ``pdf2image``
        2. Preprocess with OpenCV
        3. Run ``pytesseract.image_to_string``

        Returns
        -------
        str
            Extracted text (may be empty if OCR produces nothing).
        """
        try:
            image = self._render_page(pdf_path, page_number)
            if image is None:
                logger.warning(
                    "Could not render page %d of %s",
                    page_number, pdf_path.name,
                )
                return ""

            processed = self._preprocessor.preprocess(image)
            text = self._run_tesseract(processed)
            return text

        except Exception as exc:
            logger.error(
                "OCR failed for page %d of %s: %s",
                page_number, pdf_path.name, exc,
            )
            return ""

    def ocr_image(self, image: Image.Image) -> str:
        """OCR a standalone PIL image (used in testing / ad-hoc calls)."""
        processed = self._preprocessor.preprocess(image)
        return self._run_tesseract(processed)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _render_page(
        self, pdf_path: Path, page_number: int,
    ) -> Optional[Image.Image]:
        """Convert a single PDF page to a PIL Image."""
        try:

            images = convert_from_path(
                str(pdf_path),
                dpi=self._cfg.ocr_dpi,
                first_page=page_number + 1,   # pdf2image is 1-indexed
                last_page=page_number + 1,
                fmt="png",
            )
            if images:
                return images[0]
            return None
        except Exception as exc:
            logger.error(
                "pdf2image conversion failed for %s page %d: %s",
                pdf_path.name, page_number, exc,
            )
            return None

    def _run_tesseract(self, image: Image.Image) -> str:
        """Invoke Tesseract via pytesseract."""


        text: str = pytesseract.image_to_string(
            image,
            lang=self._cfg.ocr_language,
            timeout=self._cfg.ocr_timeout,
        )
        return text.strip()

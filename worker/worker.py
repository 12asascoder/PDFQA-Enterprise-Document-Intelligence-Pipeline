"""
PDFQA Pipeline — Extraction Worker (Consumer / Terminal 2)

Each worker runs in its own thread.  It dequeues PDF paths from the
shared task queue, extracts text using the hybrid engine (pdfplumber +
OCR fallback), detects layout, cleans the text, and saves the result
as a ``.txt`` file under ``extracted_files/``.

Workers display colorized status messages and continue processing
after individual failures.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from cleaner.text_cleaner import TextCleaner
from config import PipelineConfig
from extraction.hybrid_extractor import ExtractionResult, HybridExtractor
from extraction.layout_detector import LayoutDetector
from extraction.metadata_extractor import MetadataExtractor
from queue_manager.task_queue import TaskQueue
from utils.colors import (
    bright_green,
    bright_red,
    bright_yellow,
    error,
    info,
    success,
    warning,
    worker_tag,
)
from utils.file_utils import ensure_directory, pdf_to_txt_path

logger = logging.getLogger(__name__)


class ExtractionWorker:
    """Consumer thread — extracts, cleans, and saves text from PDFs.

    Parameters
    ----------
    worker_id : int
        Unique identifier for this worker (1-indexed).
    cfg : PipelineConfig
        Pipeline configuration.
    task_queue : TaskQueue
        Shared task queue.
    on_complete : callable | None
        Optional callback invoked after each file:
        ``on_complete(worker_id, pdf_name, success_flag)``.
    """

    def __init__(
        self,
        worker_id: int,
        cfg: PipelineConfig,
        task_queue: TaskQueue,
        on_complete: Optional[Callable] = None,
    ) -> None:
        self._id = worker_id
        self._cfg = cfg
        self._queue = task_queue
        self._on_complete = on_complete

        # Sub-components (each worker owns its own instances)
        self._extractor = HybridExtractor(cfg)
        self._layout = LayoutDetector()
        self._metadata = MetadataExtractor()
        self._cleaner = TextCleaner(cfg)

        # Stats
        self.processed: int = 0
        self.succeeded: int = 0
        self.failed: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Main loop — dequeue and process until shutdown sentinel."""
        tag = worker_tag(self._id)
        print(f"{tag} {bright_green('Worker Started')}")
        logger.info("Worker-%d started", self._id)

        while True:
            print(f"{tag} {info('Waiting …')}")
            pdf_path = self._queue.dequeue()

            if pdf_path is None:
                # Shutdown sentinel received
                print(f"{tag} {bright_yellow('Shutdown signal — exiting')}")
                logger.info("Worker-%d received shutdown signal", self._id)
                break

            self._process_file(pdf_path, tag)

        self._print_summary(tag)

    # ------------------------------------------------------------------
    # File processing
    # ------------------------------------------------------------------
    def _process_file(self, pdf_path: Path, tag: str) -> None:
        """Run the full extraction → layout → clean → save pipeline."""
        fname = pdf_path.name
        start = time.time()

        print(f"{tag} Received {bright_green(fname)}")
        logger.info("Worker-%d processing %s", self._id, fname)

        try:
            # 1. Hybrid extraction (pdfplumber + OCR)
            print(f"{tag} Running pdfplumber …")
            extraction: ExtractionResult = self._extractor.extract(pdf_path)

            # Log per-page method decisions
            for pr in extraction.pages:
                if pr.method == "ocr":
                    print(
                        f"{tag} {bright_yellow(f'No text on Page {pr.page_number + 1} → OCR')}"
                    )
                elif pr.method == "empty":
                    print(
                        f"{tag} {warning(f'Page {pr.page_number + 1} — empty after OCR')}"
                    )

            if extraction.ocr_pages > 0:
                print(f"{tag}{success(f'OCR ✓ ({extraction.ocr_pages} pages)')}")

            # 2. Layout detection
            layout = self._layout.detect(pdf_path)
            print(f"{tag}{success('Layout ✓')}")

            # 3. Metadata extraction
            metadata = self._metadata.extract(pdf_path)

            # 4. Text cleaning
            page_texts = [pr.text for pr in extraction.pages]
            raw_text = extraction.full_text
            cleaned = self._cleaner.clean(raw_text, page_texts)

            if not cleaned.strip():
                print(f"{tag}{warning(f'No extractable text in {fname}')}")
                logger.warning("Worker-%d: no text extracted from %s", self._id, fname)
                self._record_failure(fname)
                return

            # 5. Save .txt
            output_path = self._save_txt(pdf_path, metadata, cleaned)
            elapsed = time.time() - start
            print(f"{tag}{success(f'TXT Saved ✓ → {output_path.name}')}")
            print(
                f"{tag} {bright_green(f'File processed successfully ({elapsed:.1f}s)')}"
            )

            logger.info(
                "Worker-%d saved %s — %s — %.1fs",
                self._id, output_path.name,
                extraction.method_summary, elapsed,
            )

            self.processed += 1
            self.succeeded += 1
            self._queue.stats.record_complete()

            if self._on_complete:
                self._on_complete(self._id, fname, True)

        except Exception as exc:
            logger.error(
                "Worker-%d failed on %s: %s",
                self._id, fname, exc, exc_info=True,
            )
            print(f"{tag}{error(f'FAILED: {fname} — {exc}')}")
            self._record_failure(fname)

            if self._on_complete:
                self._on_complete(self._id, fname, False)

        finally:
            self._queue.task_done()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _save_txt(
        self,
        pdf_path: Path,
        metadata,
        cleaned_text: str,
    ) -> Path:
        """Write cleaned text to the output directory."""
        output_dir = ensure_directory(self._cfg.extracted_dir)
        output_path = pdf_to_txt_path(pdf_path, output_dir)

        # Compose final content with metadata header
        content_parts = []
        if metadata.title or metadata.author:
            content_parts.append(metadata.header_text)
            content_parts.append("")

        content_parts.append(cleaned_text)
        final = "\n".join(content_parts)

        output_path.write_text(final, encoding="utf-8")
        return output_path

    def _record_failure(self, filename: str) -> None:
        self.processed += 1
        self.failed += 1
        self._queue.stats.record_failure()

    def _print_summary(self, tag: str) -> None:
        print(
            f"{tag} Summary — processed={self.processed}, "
            f"succeeded={self.succeeded}, failed={self.failed}"
        )
        logger.info(
            "Worker-%d finished — processed=%d, succeeded=%d, failed=%d",
            self._id, self.processed, self.succeeded, self.failed,
        )

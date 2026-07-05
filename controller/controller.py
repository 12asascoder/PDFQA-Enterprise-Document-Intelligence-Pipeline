"""
PDFQA Pipeline — Controller (Producer / Terminal 1)

The controller discovers PDFs, validates each one, and enqueues valid
files into the task queue for workers to process.  It displays
colorized status updates for every file and final statistics.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import List

from config import PipelineConfig
from queue_manager.task_queue import TaskQueue
from utils.colors import (
    bright_cyan,
    bright_green,
    bright_red,
    controller_tag,
    cyan,
    error,
    header,
    info,
    separator,
    success,
    warning,
)
from utils.file_utils import get_pdf_files, human_readable_size
from validation.validator import DocumentValidator, ValidationResult

logger = logging.getLogger(__name__)


class PipelineController:
    """Producer thread — validates and enqueues PDFs.

    Parameters
    ----------
    cfg : PipelineConfig
        Pipeline configuration.
    task_queue : TaskQueue
        Thread-safe queue shared with workers.
    progress_callback : callable | None
        Optional callback invoked with ``(enqueued, skipped, total)``
        after each file is processed.
    """

    def __init__(
        self,
        cfg: PipelineConfig,
        task_queue: TaskQueue,
        progress_callback=None,
    ) -> None:
        self._cfg = cfg
        self._queue = task_queue
        self._validator = DocumentValidator(cfg)
        self._progress_callback = progress_callback

        # Counters
        self.total_files: int = 0
        self.enqueued: int = 0
        self.skipped: int = 0
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Discover, validate, and enqueue all PDFs.

        Call this from the controller thread.  After all files are
        processed, shutdown sentinels are sent to the queue.
        """
        self.start_time = time.time()
        tag = controller_tag()

        print(f"\n{tag} {header('Pipeline Controller Started')}")
        print(f"{tag} {info(f'Scanning {self._cfg.dataset_dir} for PDFs …')}")
        logger.info("Controller started — scanning %s", self._cfg.dataset_dir)

        pdf_files = get_pdf_files(self._cfg.dataset_dir)
        self.total_files = len(pdf_files)

        print(f"{tag} {bright_green(f'Found {self.total_files} PDF files')}\n")
        logger.info("Found %d PDF files", self.total_files)

        for idx, pdf_path in enumerate(pdf_files, 1):
            self._process_file(pdf_path, idx)

        # Send shutdown sentinels — one per worker
        self._queue.send_shutdown(self._cfg.worker_count)

        self.end_time = time.time()
        self._print_summary()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _process_file(self, pdf_path: Path, index: int) -> None:
        """Validate and enqueue a single PDF."""
        tag = controller_tag()
        fname = pdf_path.name

        print(separator())
        print(
            f"{tag} Processing [{index}/{self.total_files}] "
            f"{bright_cyan(fname)}"
        )

        # Run validation
        result: ValidationResult = self._validator.validate(pdf_path)

        if result.passed:
            print(f"{tag}{success('Validation ✓')}")
            self._queue.enqueue(pdf_path)
            self.enqueued += 1
            print(f"{tag}{success('Enqueued ✓')}")
            logger.info("Enqueued: %s", fname)
        else:
            print(f"{tag}{error(f'Validation FAILED — {result.summary}')}")
            for chk in result.failed_checks:
                print(f"{tag}{warning(f'{chk.name}: {chk.message}')}")
            self.skipped += 1
            logger.warning("Skipped: %s — %s", fname, result.summary)

        # Progress callback (for tqdm)
        if self._progress_callback:
            self._progress_callback(self.enqueued, self.skipped, self.total_files)

    def _print_summary(self) -> None:
        """Print final controller statistics."""
        elapsed = self.end_time - self.start_time
        tag = controller_tag()

        print(f"\n{separator('=')}")
        print(f"{tag} {header('Controller Summary')}")
        print(f"{tag}   Total files   : {self.total_files}")
        print(f"{tag}   Enqueued      : {bright_green(str(self.enqueued))}")
        print(f"{tag}   Skipped       : {bright_red(str(self.skipped))}")
        print(f"{tag}   Duration      : {elapsed:.1f}s")
        print(separator("="))

        logger.info(
            "Controller finished — total=%d, enqueued=%d, skipped=%d, "
            "duration=%.1fs",
            self.total_files, self.enqueued, self.skipped, elapsed,
        )

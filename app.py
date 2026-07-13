#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║          PDFQA Enterprise Document Intelligence Pipeline           ║
║                                                                    ║
║  End-to-end pipeline that downloads the pdfQA Benchmark dataset,   ║
║  validates every PDF, extracts text (pdfplumber + OCR fallback),   ║
║  detects layout, cleans text, and saves .txt files.                ║
║                                                                    ║
║  Usage:                                                            ║
║      pip install -r requirements.txt                               ║
║      python app.py                                                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so all imports resolve
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import CONFIG
from controller.controller import PipelineController
from downloader.dataset_downloader import DatasetDownloader
from pipeline.semantic_pipeline import SemanticPipeline
from queue_manager.task_queue import TaskQueue
from utils.colors import (
    bold,
    bright_cyan,
    bright_green,
    bright_red,
    bright_yellow,
    cyan,
    green,
    header,
    magenta,
    red,
    separator,
    yellow,
)
from utils.logger import setup_logging, get_logger
from worker.worker import ExtractionWorker

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
_BANNER = r"""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║    ██████╗ ██████╗ ███████╗ ██████╗  █████╗                        ║
║    ██╔══██╗██╔══██╗██╔════╝██╔═══██╗██╔══██╗                       ║
║    ██████╔╝██║  ██║█████╗  ██║   ██║███████║                       ║
║    ██╔═══╝ ██║  ██║██╔══╝  ██║▄▄ ██║██╔══██║                       ║
║    ██║     ██████╔╝██║     ╚██████╔╝██║  ██║                       ║
║    ╚═╝     ╚═════╝ ╚═╝      ╚══▀▀═╝ ╚═╝  ╚═╝                       ║
║                                                                    ║
║    Enterprise PDF Document Intelligence Pipeline   v1.0.0          ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""


def _print_config_summary() -> None:
    """Display active configuration."""
    print(header("\n  Configuration"))
    print(cyan(f"    Dataset dir    : {CONFIG.dataset_dir}"))
    print(cyan(f"    Output dir     : {CONFIG.extracted_dir}"))
    print(cyan(f"    Workers        : {CONFIG.worker_count}"))
    print(cyan(f"    OCR DPI        : {CONFIG.ocr_dpi}"))
    print(cyan(f"    OCR language   : {CONFIG.ocr_language}"))
    print(cyan(f"    Max file size  : {CONFIG.max_file_size_bytes // (1024*1024)} MB"))
    print(cyan(f"    Virus scanning : {'enabled' if CONFIG.virus_scan_enabled else 'disabled'}"))
    print()


def main() -> None:
    """Pipeline entry point."""
    pipeline_start = time.time()

    # --- Setup ------------------------------------------------------------
    CONFIG.ensure_directories()
    setup_logging(CONFIG)
    logger = get_logger("app")

    print(bright_cyan(_BANNER))
    _print_config_summary()

    # --- Step 1: Download dataset -----------------------------------------
    print(header("  Phase 1 — Dataset Download\n"))
    logger.info("=== Phase 1: Dataset Download ===")
    downloader = DatasetDownloader(CONFIG)
    try:
        downloader.download_dataset()
    except Exception as exc:
        logger.error("Dataset download failed: %s", exc, exc_info=True)
        print(red(f"\n  ✗ Download failed: {exc}"))
        print(yellow("  ⚠ Continuing with any existing files …\n"))

    # --- Step 2: Initialise queue and components --------------------------
    print(header("\n  Phase 2 — Pipeline Initialisation\n"))
    logger.info("=== Phase 2: Pipeline Initialisation ===")

    task_queue = TaskQueue(max_size=CONFIG.queue_max_size)

    # Progress bar (tqdm) updated by the controller callback
    try:
        from tqdm import tqdm
        from utils.file_utils import get_pdf_files

        total_estimate = len(get_pdf_files(CONFIG.dataset_dir))
        pbar = tqdm(
            total=total_estimate,
            desc="    Overall Progress",
            unit="file",
            ncols=100,
            leave=True,
        )
    except ImportError:
        pbar = None

    def _progress_callback(enqueued: int, skipped: int, total: int) -> None:
        if pbar is not None:
            pbar.n = enqueued + skipped
            pbar.total = total
            pbar.refresh()

    # Worker-complete callback
    completed_lock = threading.Lock()
    completed_count = 0

    def _on_worker_complete(worker_id: int, fname: str, ok: bool) -> None:
        nonlocal completed_count
        with completed_lock:
            completed_count += 1

    # --- Step 3: Launch workers (consumers) -------------------------------
    print(header("  Phase 3 — Launching Workers\n"))
    logger.info("=== Phase 3: Launching %d workers ===", CONFIG.worker_count)

    workers: list[ExtractionWorker] = []
    worker_threads: list[threading.Thread] = []

    for wid in range(1, CONFIG.worker_count + 1):
        w = ExtractionWorker(
            worker_id=wid,
            cfg=CONFIG,
            task_queue=task_queue,
            on_complete=_on_worker_complete,
        )
        workers.append(w)
        t = threading.Thread(
            target=w.run,
            name=f"Worker-{wid}",
            daemon=True,
        )
        worker_threads.append(t)
        t.start()

    # --- Step 4: Run controller (producer) --------------------------------
    print(header("\n  Phase 4 — Controller (Validation & Enqueue)\n"))
    logger.info("=== Phase 4: Controller ===")

    controller = PipelineController(
        cfg=CONFIG,
        task_queue=task_queue,
        progress_callback=_progress_callback,
    )

    # Run controller in a dedicated thread so we can join cleanly
    controller_thread = threading.Thread(
        target=controller.run,
        name="Controller",
        daemon=True,
    )
    controller_thread.start()
    controller_thread.join()

    # --- Step 5: Wait for workers to finish -------------------------------
    print(header("\n  Phase 5 — Waiting for Workers to Finish\n"))
    logger.info("=== Phase 5: Waiting for workers ===")

    for t in worker_threads:
        t.join()

    if pbar is not None:
        pbar.n = pbar.total
        pbar.refresh()
        pbar.close()

    # --- Step 6: Final statistics -----------------------------------------
    _print_final_stats(controller, workers, task_queue, time.time() - pipeline_start)
    
    # --- Step 7: Semantic Pipeline (Embeddings, Search, KG) ---------------
    print(header("\n  Phase 7 — Semantic Enrichment\n"))
    semantic = SemanticPipeline(CONFIG)
    semantic.process_all()

    pipeline_end = time.time()
    total_elapsed = pipeline_end - pipeline_start

    logger.info("Pipeline completed in %.1fs", total_elapsed)


def _print_final_stats(
    controller: PipelineController,
    workers: list,
    task_queue: TaskQueue,
    elapsed: float,
) -> None:
    """Print a comprehensive summary of the pipeline run."""
    total_succeeded = sum(w.succeeded for w in workers)
    total_failed = sum(w.failed for w in workers)

    print(bright_cyan("""
╔══════════════════════════════════════════════════════════════════════╗
║                      PIPELINE COMPLETE                             ║
╚══════════════════════════════════════════════════════════════════════╝
"""))
    print(f"  {bold('Total PDF files')}       : {controller.total_files}")
    print(f"  {bold('Validated & enqueued')}  : {bright_green(str(controller.enqueued))}")
    print(f"  {bold('Validation skipped')}   : {bright_yellow(str(controller.skipped))}")
    print(f"  {bold('Extraction succeeded')}: {bright_green(str(total_succeeded))}")
    print(f"  {bold('Extraction failed')}   : {bright_red(str(total_failed))}")
    print(f"  {bold('Total duration')}       : {elapsed:.1f}s")
    print(f"  {bold('Output directory')}     : {CONFIG.extracted_dir}")
    print()

    # Count output files
    txt_files = list(CONFIG.extracted_dir.glob("*.txt"))
    print(f"  {bright_green(f'✓ {len(txt_files)} .txt files saved')}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(yellow("\n\n  ⚠ Pipeline interrupted by user.\n"))
        sys.exit(130)
    except Exception as exc:
        print(red(f"\n  ✗ Fatal error: {exc}\n"))
        import traceback
        traceback.print_exc()
        sys.exit(1)

"""
PDFQA Pipeline — Thread-Safe Task Queue

Wraps ``queue.Queue`` with a thin API that tracks statistics and
provides sentinel-based graceful shutdown for consumer threads.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Sentinel object — workers exit when they receive this
_SENTINEL = object()


@dataclass
class QueueStats:
    """Live statistics for the task queue."""

    enqueued: int = 0
    completed: int = 0
    failed: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_enqueue(self) -> None:
        with self._lock:
            self.enqueued += 1

    def record_complete(self) -> None:
        with self._lock:
            self.completed += 1

    def record_failure(self) -> None:
        with self._lock:
            self.failed += 1

    @property
    def pending(self) -> int:
        with self._lock:
            return self.enqueued - self.completed - self.failed


class TaskQueue:
    """Thread-safe queue for distributing PDF paths to workers.

    Parameters
    ----------
    max_size : int
        Maximum queue depth.  ``0`` means unlimited.
    """

    def __init__(self, max_size: int = 0) -> None:
        self._queue: queue.Queue[Optional[Path]] = queue.Queue(
            maxsize=max_size,
        )
        self.stats = QueueStats()

    # ------------------------------------------------------------------
    # Producer API
    # ------------------------------------------------------------------
    def enqueue(self, pdf_path: Path) -> None:
        """Add a PDF path to the queue (blocks if full)."""
        self._queue.put(pdf_path)
        self.stats.record_enqueue()

    def send_shutdown(self, worker_count: int) -> None:
        """Send one sentinel per worker so each exits its loop."""
        for _ in range(worker_count):
            self._queue.put(_SENTINEL)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Consumer API
    # ------------------------------------------------------------------
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Path]:
        """Block until an item is available.

        Returns
        -------
        Path | None
            The next PDF path, or ``None`` if a shutdown sentinel was
            received (the worker should exit).
        """
        item = self._queue.get(timeout=timeout)
        if item is _SENTINEL:
            return None
        return item  # type: ignore[return-value]

    def task_done(self) -> None:
        """Signal that a dequeued task has been processed."""
        self._queue.task_done()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def is_empty(self) -> bool:
        return self._queue.empty()

    @property
    def qsize(self) -> int:
        return self._queue.qsize()

    def join(self) -> None:
        """Block until every enqueued item has been marked done."""
        self._queue.join()

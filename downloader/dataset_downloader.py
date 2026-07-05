"""
PDFQA Pipeline — HuggingFace Dataset Downloader

Automatically downloads every PDF from the pdfQA-Benchmark dataset.
Supports:
  • Skipping when the dataset already exists locally
  • Resumable downloads (partial-file detection + HTTP Range headers)
  • Per-file tqdm progress bars
  • Retry with exponential backoff
  • Integrity verification via content-length comparison
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

import requests
from tqdm import tqdm

from config import PipelineConfig
from utils.colors import bright_green, bright_yellow, cyan, header, info, success, warning
from utils.file_utils import ensure_directory, human_readable_size

logger = logging.getLogger(__name__)


class DatasetDownloader:
    """Downloads PDFs from HuggingFace ``pdfqa/pdfQA-Benchmark``."""

    def __init__(self, cfg: PipelineConfig) -> None:
        self._cfg = cfg
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "PDFQA-Pipeline/1.0",
        })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def download_dataset(self) -> int:
        """Download the full dataset.  Returns the number of files downloaded.

        If the dataset directory already contains PDF files the download
        is skipped entirely.
        """
        existing = list(self._cfg.dataset_dir.rglob("*.pdf"))
        if existing:
            msg = (
                f"Dataset found — {len(existing)} PDFs already present "
                f"in {self._cfg.dataset_dir}.  Skipping download."
            )
            print(bright_green(f"\n  ✓ {msg}\n"))
            logger.info(msg)
            return 0

        print(header("\n  Downloading pdfQA-Benchmark dataset …\n"))
        logger.info("Starting dataset download from HuggingFace.")

        total_downloaded = 0
        for subdir in self._cfg.hf_subdirectories:
            count = self._download_subdirectory(subdir)
            total_downloaded += count

        print(success(
            f"Download complete — {total_downloaded} files saved to "
            f"{self._cfg.dataset_dir}"
        ))
        logger.info("Dataset download finished.  Files: %d", total_downloaded)
        return total_downloaded

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _download_subdirectory(self, subdir: str) -> int:
        """List and download every file in a single HF subdirectory."""
        url = self._cfg.hf_tree_url(subdir)
        logger.info("Listing files in %s", subdir)
        print(info(f"Listing {subdir} …"))

        try:
            file_list = self._list_files(url)
        except Exception:
            logger.exception("Failed to list files for %s", subdir)
            print(warning(f"Could not list files in {subdir} — skipping"))
            return 0

        if not file_list:
            logger.warning("No files found in %s", subdir)
            return 0

        downloaded = 0
        for file_info in file_list:
            file_path: str = file_info["path"]
            file_size: int = file_info.get("size", 0)

            # Derive local path preserving subdirectory structure
            # e.g. real-pdfQA/01.2_Input_Files_PDF/ClimRetrieve/report.pdf
            #  →   dataset/ClimRetrieve/report.pdf
            relative = file_path.split(self._cfg.hf_dataset_subpath + "/", 1)
            if len(relative) == 2:
                local_rel = relative[1]
            else:
                local_rel = Path(file_path).name

            local_path = self._cfg.dataset_dir / local_rel
            ensure_directory(local_path.parent)

            if local_path.exists() and local_path.stat().st_size == file_size:
                logger.debug("Already downloaded: %s", local_path.name)
                downloaded += 1
                continue

            ok = self._download_file(file_path, local_path, file_size)
            if ok:
                downloaded += 1

        return downloaded

    def _list_files(self, url: str) -> List[Dict[str, Any]]:
        """Query the HF API and return a list of file metadata dicts."""
        resp = self._session.get(url, timeout=self._cfg.download_timeout)
        resp.raise_for_status()
        entries = resp.json()
        # Keep only actual files (skip sub-directories)
        return [e for e in entries if e.get("type") == "file"]

    def _download_file(
        self,
        repo_path: str,
        local_path: Path,
        expected_size: int,
    ) -> bool:
        """Download a single file with retries and resume support."""
        download_url = self._cfg.hf_download_url(quote(repo_path, safe="/"))

        for attempt in range(1, self._cfg.download_max_retries + 1):
            try:
                return self._stream_download(
                    download_url, local_path, expected_size,
                )
            except Exception as exc:
                wait = self._cfg.download_retry_backoff ** attempt
                logger.warning(
                    "Download attempt %d/%d failed for %s: %s — "
                    "retrying in %.1fs",
                    attempt, self._cfg.download_max_retries,
                    local_path.name, exc, wait,
                )
                if attempt < self._cfg.download_max_retries:
                    time.sleep(wait)

        logger.error("Giving up on %s after %d retries", local_path.name,
                      self._cfg.download_max_retries)
        return False

    def _stream_download(
        self,
        url: str,
        local_path: Path,
        expected_size: int,
    ) -> bool:
        """Stream *url* into *local_path*, resuming if a partial file exists."""
        headers: Dict[str, str] = {}
        mode = "wb"
        initial_bytes = 0

        partial = local_path.with_suffix(local_path.suffix + ".part")
        if partial.exists():
            initial_bytes = partial.stat().st_size
            headers["Range"] = f"bytes={initial_bytes}-"
            mode = "ab"
            logger.info("Resuming %s from byte %d", local_path.name, initial_bytes)

        resp = self._session.get(
            url, headers=headers, stream=True,
            timeout=self._cfg.download_timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()

        total = expected_size or int(
            resp.headers.get("content-length", 0)
        ) + initial_bytes

        desc = f"    ↓ {local_path.name[:50]}"
        with (
            open(partial, mode) as fh,
            tqdm(
                total=total,
                initial=initial_bytes,
                unit="B",
                unit_scale=True,
                desc=desc,
                leave=False,
                ncols=100,
            ) as pbar,
        ):
            for chunk in resp.iter_content(
                chunk_size=self._cfg.download_chunk_size,
            ):
                if chunk:
                    fh.write(chunk)
                    pbar.update(len(chunk))

        # Rename .part → final
        partial.rename(local_path)

        # Integrity check
        actual = local_path.stat().st_size
        if expected_size and actual != expected_size:
            logger.warning(
                "Size mismatch for %s: expected %s, got %s",
                local_path.name,
                human_readable_size(expected_size),
                human_readable_size(actual),
            )

        logger.info(
            "Downloaded %s (%s)", local_path.name,
            human_readable_size(actual),
        )
        return True

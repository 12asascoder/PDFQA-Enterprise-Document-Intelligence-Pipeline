"""
PDFQA Pipeline — Central Configuration Module

All pipeline-wide settings are defined here. Modify values to tune
the pipeline for your environment. Paths are resolved relative to the
project root so the config stays portable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Resolve project root (directory that contains *this* file)
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline configuration."""

    # ------------------------------------------------------------------
    # Directory layout
    # ------------------------------------------------------------------
    project_root: Path = PROJECT_ROOT
    dataset_dir: Path = PROJECT_ROOT / "pdfQA-Benchmark" / "real-pdfQA" / "01.2_Input_Files_PDF"
    extracted_dir: Path = PROJECT_ROOT / "extracted_files"
    logs_dir: Path = PROJECT_ROOT / "logs"
    storage_data_dir: Path = PROJECT_ROOT / "storage_data"

    # ------------------------------------------------------------------
    # Semantic & Search settings
    # ------------------------------------------------------------------
    db_path: Path = storage_data_dir / "pdfqa.db"
    faiss_index_dir: Path = storage_data_dir / "faiss_index"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_batch_size: int = 32
    chunk_target_tokens: int = 512
    chunk_overlap_tokens: int = 64

    # ------------------------------------------------------------------
    # HuggingFace dataset
    # ------------------------------------------------------------------
    hf_dataset_repo: str = "pdfqa/pdfQA-Benchmark"
    hf_dataset_branch: str = "main"
    hf_dataset_subpath: str = "real-pdfQA/01.2_Input_Files_PDF"
    hf_api_base: str = "https://huggingface.co/api/datasets"
    hf_resolve_base: str = "https://huggingface.co/datasets"

    # Subdirectories inside the dataset that contain PDFs
    hf_subdirectories: List[str] = field(default_factory=lambda: [
        "ClimRetrieve",
        "ClimateFinanceBench",
        "FeTaQA",
        "FinQA",
        "FinanceBench",
        "NaturalQuestions",
        "PaperTab",
        "PaperText",
        "Tat-QA",
    ])

    # ------------------------------------------------------------------
    # Download settings
    # ------------------------------------------------------------------
    download_chunk_size: int = 8192          # bytes per read during download
    download_max_retries: int = 3
    download_retry_backoff: float = 2.0      # exponential backoff base (s)
    download_timeout: int = 120              # request timeout in seconds

    # ------------------------------------------------------------------
    # Worker / queue settings
    # ------------------------------------------------------------------
    worker_count: int = 4
    queue_max_size: int = 0                  # 0 = unlimited

    # ------------------------------------------------------------------
    # Validation settings
    # ------------------------------------------------------------------
    max_file_size_bytes: int = 500 * 1024 * 1024   # 500 MB
    min_file_size_bytes: int = 100                  # skip tiny/empty files
    valid_mime_types: List[str] = field(default_factory=lambda: [
        "application/pdf",
    ])
    valid_extensions: List[str] = field(default_factory=lambda: [
        ".pdf",
    ])

    # ------------------------------------------------------------------
    # Virus scanning
    # ------------------------------------------------------------------
    virus_scan_enabled: bool = True

    # ------------------------------------------------------------------
    # OCR settings
    # ------------------------------------------------------------------
    ocr_dpi: int = 300
    ocr_language: str = "eng"
    ocr_timeout: int = 120                   # per-page timeout in seconds

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = "INFO"
    log_format: str = (
        "[%(asctime)s] [%(levelname)-8s] [%(name)-20s] %(message)s"
    )
    log_date_format: str = "%Y-%m-%d %H:%M:%S"

    # ------------------------------------------------------------------
    # Text cleaning
    # ------------------------------------------------------------------
    min_page_chars: int = 10     # pages with fewer non-ws chars → blank

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def ensure_directories(self) -> None:
        """Create all required directories if they do not exist."""
        for directory in (
            self.dataset_dir,
            self.extracted_dir,
            self.logs_dir,
            self.storage_data_dir,
            self.faiss_index_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def pipeline_log_path(self) -> Path:
        return self.logs_dir / "pipeline.log"

    @property
    def error_log_path(self) -> Path:
        return self.logs_dir / "error.log"

    def hf_tree_url(self, subdir: str) -> str:
        """Return the HF API URL to list files in *subdir*."""
        path = f"{self.hf_dataset_subpath}/{subdir}"
        return (
            f"{self.hf_api_base}/{self.hf_dataset_repo}"
            f"/tree/{self.hf_dataset_branch}/{path}"
        )

    def hf_download_url(self, file_path: str) -> str:
        """Return the HF resolve URL to download a file by its repo path."""
        return (
            f"{self.hf_resolve_base}/{self.hf_dataset_repo}"
            f"/resolve/{self.hf_dataset_branch}/{file_path}"
        )


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly
# ---------------------------------------------------------------------------
CONFIG = PipelineConfig()

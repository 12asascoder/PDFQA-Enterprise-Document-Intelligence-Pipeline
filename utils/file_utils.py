"""
PDFQA Pipeline — File Utility Functions

Reusable helpers for file I/O, hashing, and path manipulation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List


def compute_sha256(filepath: Path, chunk_size: int = 65536) -> str:
    """Compute the SHA-256 hex digest of *filepath* using streaming reads.

    Parameters
    ----------
    filepath : Path
        Absolute or relative path to the file.
    chunk_size : int
        Bytes per read (default 64 KB).

    Returns
    -------
    str
        Lowercase hex digest string.
    """
    sha = hashlib.sha256()
    with open(filepath, "rb") as fh:
        while True:
            data = fh.read(chunk_size)
            if not data:
                break
            sha.update(data)
    return sha.hexdigest()


def ensure_directory(path: Path) -> Path:
    """Create *path* (and parents) if it does not exist. Returns *path*."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_pdf_files(directory: Path) -> List[Path]:
    """Recursively discover all ``.pdf`` files under *directory*.

    Returns a sorted list of ``Path`` objects.
    """
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.rglob("*.pdf") if p.is_file()
    )


def pdf_to_txt_path(pdf_path: Path, output_dir: Path) -> Path:
    """Derive the ``.txt`` output path for a given PDF.

    The output file name mirrors the PDF stem::

        dataset/ClimRetrieve/report.pdf  →  extracted_files/report.txt

    Parameters
    ----------
    pdf_path : Path
        Source PDF path.
    output_dir : Path
        Root directory for extracted text files.

    Returns
    -------
    Path
        Destination ``.txt`` path.
    """
    return output_dir / f"{pdf_path.stem}.txt"


def safe_filename(name: str) -> str:
    """Sanitise a filename by replacing problematic characters."""
    keep = {" ", ".", "-", "_"}
    return "".join(c if (c.isalnum() or c in keep) else "_" for c in name)


def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable string (e.g. ``14.2 MB``)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0  # type: ignore[assignment]
    return f"{size_bytes:.1f} PB"

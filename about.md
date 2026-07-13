# PDFQA Enterprise Document Intelligence Pipeline — Complete Documentation

> **Version:** 1.0.0  
> **Language:** Python 3.10+  
> **License:** Private  

---

## Table of Contents

1. [Overview](#overview)  
2. [Architecture](#architecture)  
3. [Pipeline Phases](#pipeline-phases)  
4. [Project Structure](#project-structure)  
5. [Module Deep Dives](#module-deep-dives)  
   - [app.py — Entry Point](#apppy--entry-point)  
   - [config.py — Central Configuration](#configpy--central-configuration)  
   - [downloader/ — Dataset Downloader](#downloader--dataset-downloader)  
   - [controller/ — Pipeline Controller](#controller--pipeline-controller)  
   - [queue_manager/ — Task Queue](#queue_manager--task-queue)  
   - [worker/ — Extraction Worker](#worker--extraction-worker)  
   - [validation/ — Document Validation](#validation--document-validation)  
   - [extraction/ — Text Extraction Engine](#extraction--text-extraction-engine)  
   - [ocr/ — OCR Engine & Preprocessor](#ocr--ocr-engine--preprocessor)  
   - [cleaner/ — Text Cleaner](#cleaner--text-cleaner)  
   - [utils/ — Utilities](#utils--utilities)  
   - [tests/ — Test Suite](#tests--test-suite)  
6. [Data Flow](#data-flow)  
7. [Multi-Column Extraction](#multi-column-extraction)  
8. [Dependencies](#dependencies)  
9. [Configuration Reference](#configuration-reference)  
10. [Running the Pipeline](#running-the-pipeline)  
11. [Output Format](#output-format)  
12. [Error Handling & Logging](#error-handling--logging)  
13. [Testing](#testing)  

---

## Overview

The **PDFQA Pipeline** is an enterprise-grade, end-to-end system for extracting clean, structured text from PDF documents. It downloads PDFs from the [pdfQA-Benchmark](https://huggingface.co/datasets/pdfqa/pdfQA-Benchmark) dataset hosted on HuggingFace, validates each document through a rigorous 10-check pipeline, extracts text using a hybrid approach (pdfplumber + OCR fallback), detects page layouts, cleans the extracted text, and writes the output as `.txt` files.

### Key Capabilities

| Feature | Description |
|---|---|
| **Hybrid Extraction** | pdfplumber is tried first on every page; Tesseract OCR activates only when pdfplumber returns empty |
| **Column-Aware Extraction** | Detects multi-column layouts via character x-position histograms and extracts each column independently |
| **10-Check Validation** | MIME type, extension, size, readability, permissions, encryption, corruption, SHA-256 dedup, virus scan, logging |
| **Multi-Threaded** | Producer–consumer architecture with configurable worker threads |
| **OCR Preprocessing** | Grayscale → adaptive threshold → denoise → deskew → sharpen → orientation correction |
| **Text Cleaning** | Unicode normalisation, header/footer removal, hyphen rejoining, whitespace normalisation, page number stripping |
| **Resumable Downloads** | HTTP Range header support for interrupted downloads |
| **Virus Scanning** | ClamAV integration with graceful no-op fallback |

---

## Architecture

The pipeline follows a **multi-threaded producer–consumer** pattern:

```
┌─────────────────────────────────────────────────────────────────────┐
│                          app.py (Main)                              │
│  Orchestrates all 6 phases, spawns threads, collects statistics     │
└──────────┬──────────────────────────────────────────────────────────┘
           │
   ┌───────▼───────┐
   │  Phase 1:     │    DatasetDownloader
   │  Download     │    HuggingFace API → local PDFs
   └───────┬───────┘
           │
   ┌───────▼───────┐
   │  Phase 2:     │    TaskQueue, ExtractionWorker instances
   │  Initialise   │    tqdm progress bar setup
   └───────┬───────┘
           │
   ┌───────▼───────┐
   │  Phase 3:     │    N daemon threads launched
   │  Workers      │    Each runs ExtractionWorker.run()
   └───────┬───────┘
           │
   ┌───────▼───────┐
   │  Phase 4:     │    PipelineController (producer thread)
   │  Controller   │    Discovers → Validates → Enqueues PDFs
   └───────┬───────┘
           │
   ┌───────▼───────┐
   │  Phase 5:     │    Main thread joins all worker threads
   │  Wait         │    Workers process queue until sentinel
   └───────┬───────┘
           │
   ┌───────▼───────┐
   │  Phase 6:     │    Final statistics printed to terminal
   │  Statistics   │    Pipeline duration, success/fail counts
   └───────────────┘
```

### Producer–Consumer Model

```
Controller (Producer)                     Workers (Consumers)
─────────────────────                     ────────────────────
 Discover PDFs                             Worker-1  ──┐
      │                                    Worker-2  ──┤
 Validate each PDF                         Worker-3  ──┤  dequeue → extract
      │                                    Worker-4  ──┘  → clean → save
 Enqueue valid PDFs ──→ [ TaskQueue ] ──→
      │
 Send N sentinels ────→ (shutdown)
```

---

## Pipeline Phases

### Phase 1 — Dataset Download
- Downloads the `pdfQA-Benchmark` dataset from HuggingFace
- **Skips** if PDFs already exist locally
- Supports **resume** via HTTP Range headers and `.part` files
- **Retries** with exponential backoff (configurable)
- **Integrity verification** via content-length comparison
- Per-file tqdm progress bars

### Phase 2 — Pipeline Initialisation
- Creates the `TaskQueue` (thread-safe `queue.Queue` wrapper)
- Instantiates `ExtractionWorker` objects (one per worker thread)
- Sets up the `tqdm` overall progress bar
- Registers progress and completion callbacks

### Phase 3 — Launching Workers
- Spawns `worker_count` daemon threads (default: 4)
- Each thread runs `ExtractionWorker.run()`, which loops on `queue.dequeue()`
- Workers are independent — each owns its own `HybridExtractor`, `LayoutDetector`, `MetadataExtractor`, and `TextCleaner` instances

### Phase 4 — Controller (Validation & Enqueue)
- Runs `PipelineController.run()` in a dedicated thread
- Recursively discovers all `.pdf` files under the dataset directory
- Validates each PDF through the **10-check validation pipeline**
- Valid files are enqueued; invalid files are skipped with reason logged
- After all files are processed, sends one shutdown sentinel per worker

### Phase 5 — Waiting for Workers
- Main thread joins all worker threads
- Workers exit when they receive a `None` sentinel from the queue
- Progress bar finalised

### Phase 6 — Final Statistics
- Prints a summary table:  
  Total files, validated & enqueued, skipped, extraction succeeded/failed, duration, output directory, `.txt` files saved

---

## Project Structure

```
PDFQA_PIPELINE/
├── app.py                        # Entry point — orchestrates all phases
├── config.py                     # Central configuration (PipelineConfig dataclass)
├── requirements.txt              # Python dependencies
├── pyrightconfig.json            # Type checker config
├── .gitignore                    # Git exclusions
├── README.md                     # Project readme
│
├── downloader/
│   ├── __init__.py
│   └── dataset_downloader.py     # HuggingFace dataset download with resume
│
├── controller/
│   ├── __init__.py
│   └── controller.py             # Producer — validates and enqueues PDFs
│
├── queue_manager/
│   ├── __init__.py
│   └── task_queue.py             # Thread-safe queue with sentinel shutdown
│
├── worker/
│   ├── __init__.py
│   └── worker.py                 # Consumer — extract → layout → clean → save
│
├── validation/
│   ├── __init__.py
│   ├── validator.py              # 10-check document validation pipeline
│   └── virus_scanner.py          # ClamAV / NoOp virus scanner abstraction
│
├── extraction/
│   ├── __init__.py
│   ├── hybrid_extractor.py       # Core extraction: pdfplumber + OCR + column detection
│   ├── layout_detector.py        # Heuristic layout analysis (headings, lists, columns, etc.)
│   ├── metadata_extractor.py     # PDF metadata via PyMuPDF (title, author, dates)
│   └── table_extractor.py        # Standalone table extraction and formatting
│
├── ocr/
│   ├── __init__.py
│   ├── ocr_engine.py             # Tesseract OCR — renders page → preprocess → OCR
│   └── image_preprocessor.py     # OpenCV pipeline: grayscale → threshold → denoise → deskew
│
├── cleaner/
│   ├── __init__.py
│   └── text_cleaner.py           # Post-extraction text normalisation (7 transformations)
│
├── utils/
│   ├── __init__.py
│   ├── colors.py                 # ANSI terminal color helpers
│   ├── file_utils.py             # SHA-256, file discovery, path helpers
│   └── logger.py                 # Dual-file + console logging setup
│
├── tests/
│   ├── __init__.py
│   ├── test_cleaner.py           # TextCleaner unit tests
│   ├── test_extractor.py         # HybridExtractor unit tests
│   └── test_validator.py         # DocumentValidator unit tests
│
├── pdfQA-Benchmark/              # Downloaded dataset (gitignored)
├── extracted_files/              # Output .txt files (gitignored)
└── logs/                         # pipeline.log + error.log (gitignored)
```

---

## Module Deep Dives

---

### `app.py` — Entry Point

**File:** [`app.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/app.py)  
**Purpose:** Orchestrates the full 6-phase pipeline lifecycle.

#### Key Functions

| Function | Description |
|---|---|
| `main()` | Pipeline entry point. Runs phases 1–6 sequentially. Sets up logging, downloads dataset, creates queue/workers, launches controller, waits for completion, prints stats. |
| `_print_config_summary()` | Displays the active configuration (dataset dir, output dir, worker count, OCR settings, etc.) |
| `_print_final_stats(controller, workers, task_queue, elapsed)` | Prints a boxed summary with total files, enqueued, skipped, succeeded, failed, duration, and output file count. |

#### Threading Model
- **Controller thread:** Runs `PipelineController.run()` — validates and enqueues PDFs
- **Worker threads:** `CONFIG.worker_count` daemon threads (default 4), each running `ExtractionWorker.run()`
- **Main thread:** Orchestrates setup, joins controller thread, then joins all worker threads

#### Callbacks
- `_progress_callback(enqueued, skipped, total)` — Updates the tqdm progress bar
- `_on_worker_complete(worker_id, fname, ok)` — Increments a thread-safe completion counter

---

### `config.py` — Central Configuration

**File:** [`config.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/config.py)  
**Purpose:** Single-source-of-truth for all pipeline settings.

#### `PipelineConfig` (frozen dataclass)

| Section | Field | Default | Description |
|---|---|---|---|
| **Directories** | `project_root` | Auto-detected | Root directory of the project |
| | `dataset_dir` | `pdfQA-Benchmark/real-pdfQA/01.2_Input_Files_PDF` | Where downloaded PDFs are stored |
| | `extracted_dir` | `extracted_files/` | Where output `.txt` files are saved |
| | `logs_dir` | `logs/` | Where log files are written |
| **HuggingFace** | `hf_dataset_repo` | `pdfqa/pdfQA-Benchmark` | HF dataset repository identifier |
| | `hf_dataset_branch` | `main` | Git branch to pull from |
| | `hf_subdirectories` | 9 subdirs | ClimRetrieve, ClimateFinanceBench, FeTaQA, FinQA, FinanceBench, NaturalQuestions, PaperTab, PaperText, Tat-QA |
| **Download** | `download_chunk_size` | `8192` | Bytes per read chunk |
| | `download_max_retries` | `3` | Max retry attempts |
| | `download_retry_backoff` | `2.0` | Exponential backoff base (seconds) |
| | `download_timeout` | `120` | HTTP request timeout (seconds) |
| **Workers** | `worker_count` | `4` | Number of consumer threads |
| | `queue_max_size` | `0` | Queue depth limit (0 = unlimited) |
| **Validation** | `max_file_size_bytes` | `500 MB` | Maximum allowed PDF size |
| | `min_file_size_bytes` | `100` | Minimum allowed PDF size |
| | `valid_mime_types` | `["application/pdf"]` | Accepted MIME types |
| | `valid_extensions` | `[".pdf"]` | Accepted file extensions |
| **Virus Scan** | `virus_scan_enabled` | `True` | Enable ClamAV scanning |
| **OCR** | `ocr_dpi` | `300` | DPI for page-to-image rendering |
| | `ocr_language` | `eng` | Tesseract language model |
| | `ocr_timeout` | `120` | Per-page OCR timeout (seconds) |
| **Logging** | `log_level` | `INFO` | Root logger level |
| | `log_format` | `[timestamp] [level] [module] message` | Log line format |
| **Cleaning** | `min_page_chars` | `10` | Pages with fewer non-whitespace chars are treated as blank |

#### Helper Methods
- `ensure_directories()` — Creates `dataset_dir`, `extracted_dir`, `logs_dir` if missing
- `pipeline_log_path` / `error_log_path` — Property accessors for log file paths
- `hf_tree_url(subdir)` — Constructs the HF API URL to list files in a subdirectory
- `hf_download_url(file_path)` — Constructs the HF resolve URL to download a file

#### Singleton
`CONFIG = PipelineConfig()` — Module-level singleton used across the codebase via `from config import CONFIG`.

---

### `downloader/` — Dataset Downloader

**File:** [`dataset_downloader.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/downloader/dataset_downloader.py)  
**Purpose:** Automatically downloads PDFs from the HuggingFace `pdfQA-Benchmark` dataset.

#### `DatasetDownloader`

| Method | Description |
|---|---|
| `download_dataset()` | Main entry. Skips if PDFs already exist locally. Iterates through all `hf_subdirectories` and downloads files from each. Returns total count of downloaded files. |
| `_download_subdirectory(subdir)` | Lists files via HF API, skips already-downloaded files (size match), downloads the rest. |
| `_list_files(url)` | Queries the HF tree API, parses JSON, filters to `type == "file"`. |
| `_download_file(repo_path, local_path, expected_size)` | Retry loop with exponential backoff. Delegates to `_stream_download()`. |
| `_stream_download(url, local_path, expected_size)` | Streams content to a `.part` file with tqdm progress. Supports **resume** via HTTP `Range` header if a partial file exists. Renames `.part` → final on completion. Verifies integrity via content-length comparison. |

#### Resume Logic
1. Check if `<filename>.pdf.part` exists
2. If yes, read its size → set `Range: bytes=<size>-` header, open in append mode
3. Stream remaining bytes
4. Rename `.part` → `.pdf`

---

### `controller/` — Pipeline Controller

**File:** [`controller.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/controller/controller.py)  
**Purpose:** The **producer** in the producer–consumer pattern. Discovers PDFs, validates them, and enqueues valid files for workers.

#### `PipelineController`

| Method | Description |
|---|---|
| `run()` | Main loop. Scans `dataset_dir` for PDFs, validates each, enqueues valid files, sends shutdown sentinels. |
| `_process_file(pdf_path, index)` | Validates a single PDF. If passed → enqueue + log. If failed → skip + print reasons. Invokes progress callback. |
| `_print_summary()` | Prints controller statistics: total, enqueued, skipped, duration. |

#### Tracked Counters
- `total_files` — Total PDF files discovered
- `enqueued` — Files that passed validation and were sent to the queue
- `skipped` — Files that failed validation

---

### `queue_manager/` — Task Queue

**File:** [`task_queue.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/queue_manager/task_queue.py)  
**Purpose:** Thread-safe wrapper around `queue.Queue` with statistics tracking and sentinel-based shutdown.

#### `QueueStats` (dataclass)
Tracks `enqueued`, `completed`, `failed` counts with a threading lock. Exposes a `pending` property.

#### `TaskQueue`

| Method | Role | Description |
|---|---|---|
| `enqueue(pdf_path)` | Producer | Add a PDF path to the queue (blocks if full). Increments `stats.enqueued`. |
| `send_shutdown(worker_count)` | Producer | Sends one `_SENTINEL` object per worker so each exits its processing loop. |
| `dequeue(timeout)` | Consumer | Blocks until an item is available. Returns `None` if sentinel received (worker should exit). |
| `task_done()` | Consumer | Signals that a dequeued task has been processed. |
| `is_empty()` | Inspection | Check if queue is empty. |
| `qsize` | Inspection | Current queue depth. |
| `join()` | Sync | Block until every enqueued item has been marked done. |

#### Sentinel Shutdown Pattern
Workers loop calling `dequeue()`. When the controller finishes, it calls `send_shutdown(N)` which enqueues N `_SENTINEL` objects. Each worker receives one, recognises `None`, and exits its loop.

---

### `worker/` — Extraction Worker

**File:** [`worker.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/worker/worker.py)  
**Purpose:** The **consumer** in the producer–consumer pattern. Each worker thread runs the full extraction pipeline on individual PDFs.

#### `ExtractionWorker`

Each worker **owns its own instances** of all sub-components (no sharing between threads):
- `HybridExtractor` — pdfplumber + OCR text extraction
- `LayoutDetector` — Page layout heuristics
- `MetadataExtractor` — PDF metadata via PyMuPDF
- `TextCleaner` — Post-extraction text normalisation

#### Processing Pipeline (per file)

```
PDF File
  │
  ├─→ 1. HybridExtractor.extract()
  │      └─→ Per-page: pdfplumber → (column detection) → text
  │      └─→ Fallback: OCR if pdfplumber returns empty
  │      └─→ Table extraction appended
  │
  ├─→ 2. LayoutDetector.detect()
  │      └─→ Headings, lists, tables, figures, columns, headers/footers
  │
  ├─→ 3. MetadataExtractor.extract()
  │      └─→ Title, author, dates, page count
  │
  ├─→ 4. TextCleaner.clean()
  │      └─→ Unicode NFKC → remove headers/footers → fix hyphens
  │      └─→ Normalise whitespace → remove page numbers
  │
  └─→ 5. Save .txt
         └─→ Metadata header + cleaned text → extracted_files/<stem>.txt
```

#### Stats per Worker
- `processed` — Total files attempted
- `succeeded` — Files extracted and saved successfully
- `failed` — Files that encountered errors

---

### `validation/` — Document Validation

**File:** [`validator.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/validation/validator.py)  
**Purpose:** 10-check validation pipeline that every PDF must pass before extraction.

#### `DocumentValidator`

The validator is **thread-safe** — the SHA-256 duplicate registry uses a `threading.Lock`.

#### Validation Checks (in order)

| # | Check | Library | What it does |
|---|---|---|---|
| 1 | **MIME type** | `python-magic` | Verifies the file's magic bytes match `application/pdf`. Gracefully skips if `python-magic` is not installed. |
| 2 | **Extension** | `pathlib` | Ensures the file extension is `.pdf`. |
| 3 | **File size** | `os.stat` | Rejects files smaller than 100 bytes or larger than 500 MB. |
| 4 | **Readability** | `open()` | Tries to read the first 1024 bytes. Catches I/O errors. |
| 5 | **Permissions** | `os.access` | Checks for `R_OK` (read permission). |
| — | *Short-circuit* | — | If checks 1–5 fail, checks 6–9 are skipped entirely. |
| 6 | **Encryption** | `PyMuPDF` | Opens with `fitz.open()` and checks `doc.is_encrypted`. Encrypted PDFs are rejected. |
| 7 | **Corruption** | `PyMuPDF` | Iterates every page in the document. If iteration fails or page count is 0, the PDF is marked corrupt. |
| 8 | **SHA-256 Dedup** | `hashlib` | Computes a full-file SHA-256 digest and checks against an in-memory set. Duplicates are rejected. |
| 9 | **Virus scan** | `pyclamd` | Scans via ClamAV daemon (Unix socket or network). Falls back to `NoOpScanner` if ClamAV is unavailable. |
| 10 | **Logging** | `logging` | Logs the complete validation result (all check outcomes) at INFO or WARNING level. |

#### Data Structures
- `CheckResult(name, passed, message)` — Outcome of one check
- `ValidationResult(filepath, passed, checks)` — Aggregated result with `failed_checks` and `summary` properties

---

#### Virus Scanner (`virus_scanner.py`)

**File:** [`virus_scanner.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/validation/virus_scanner.py)

| Class | Description |
|---|---|
| `BaseVirusScanner` | Abstract base with `scan(filepath) → ScanResult` and `is_available() → bool` |
| `ClamAVScanner` | Attempts connection via Unix socket, then network socket. Scans via `pyclamd.scan_file()`. |
| `NoOpScanner` | Always returns `ScanResult(clean=True)`. Used when ClamAV is not installed or scanning is disabled. |
| `create_virus_scanner(enabled)` | Factory function. Returns `ClamAVScanner` if available, else `NoOpScanner`. |

---

### `extraction/` — Text Extraction Engine

#### Hybrid Extractor (`hybrid_extractor.py`)

**File:** [`hybrid_extractor.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/extraction/hybrid_extractor.py)  
**Purpose:** Core extraction logic — the most critical module in the pipeline.

##### Extraction Strategy

```
For every page in the PDF:
    text = _extract_text_column_aware(page)    # pdfplumber with column detection
    if text is None or text.strip() == "":
        text = OCR(page)                        # Tesseract fallback
    if text is still empty:
        mark page as "empty"
```

##### `HybridExtractor`

| Method | Description |
|---|---|
| `extract(pdf_path)` | Opens the PDF, iterates pages, calls `_extract_page()` for each. Returns `ExtractionResult` with per-page results and statistics. |
| `_extract_page(pdf_path, page, page_idx)` | Tries column-aware pdfplumber extraction first. Falls back to OCR if empty. Falls back to "empty" if OCR also fails. Appends table text if tables are found. |
| `_extract_text_column_aware(page, page_idx, filename)` | **Column detection** — analyses character x-positions to find a column gutter. If multi-column, crops the page into left/right halves and extracts each independently. See [Multi-Column Extraction](#multi-column-extraction) for details. |
| `_extract_tables_from_page(page, page_idx, filename)` | Static method. Extracts tables via `pdfplumber.extract_tables()` and formats them as pipe-delimited text with headers. |

##### Data Structures
- `PageResult(page_number, text, method, has_text)` — Result for one page. `method` is `"pdfplumber"`, `"ocr"`, or `"empty"`.
- `ExtractionResult(filepath, pages, total_pages, pdfplumber_pages, ocr_pages, empty_pages, duration_seconds)` — Full document result with `full_text` property that concatenates all page texts.

---

#### Layout Detector (`layout_detector.py`)

**File:** [`layout_detector.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/extraction/layout_detector.py)  
**Purpose:** Heuristic-based structural analysis of PDF pages.

##### Detected Elements

| Element Type | Detection Method |
|---|---|
| `heading` | Regex: `^(?:\d+\.?\s+)?[A-Z][A-Za-z\s:–—-]{3,80}$` |
| `list_item` | Regex: bullet characters (`•●▪◦▸►`) or numbered patterns (`1.`, `a)`) |
| `page_number` | Regex: standalone numbers or `Page N` patterns |
| `figure_reference` | Regex: `Figure|Fig|Exhibit|Chart|Graph|Diagram` followed by a number |
| `table` | Detected via `pdfplumber.extract_tables()` |
| `figure` | Detected via `page.images` (image objects embedded in the page) |
| `header` / `footer` | First/last lines of the page if short enough |
| `multi_column` | Character x-position gap analysis (gaps > 50px) |
| `paragraph` | Default — any line that doesn't match the above patterns |

##### Data Structures
- `LayoutElement(element_type, page_number, content_preview, confidence)`
- `PageLayout(page_number, elements, has_tables, has_figures, has_columns, is_header_page, is_footer_page, has_page_number)`
- `DocumentLayout(filepath, pages)` — with `summary` property listing all detected element types

---

#### Metadata Extractor (`metadata_extractor.py`)

**File:** [`metadata_extractor.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/extraction/metadata_extractor.py)  
**Purpose:** Extracts document-level metadata from PDFs using PyMuPDF.

##### `DocumentMetadata` Fields
- `title`, `author`, `subject`, `keywords`, `creator`, `producer`
- `creation_date`, `modification_date`
- `page_count`, `file_size_bytes`
- `header_text` property — formats metadata as a text block for prepending to output files

---

#### Table Extractor (`table_extractor.py`)

**File:** [`table_extractor.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/extraction/table_extractor.py)  
**Purpose:** Standalone table extraction that can be used independently or alongside the hybrid extractor.

##### `TableData`
- `page_number`, `table_index`, `headers`, `rows`
- `formatted` property — pipe-delimited text representation

##### `TableExtractor`
- `extract_all(pdf_path)` — Returns all tables from the entire PDF
- `tables_to_text(tables)` — Concatenates all tables into a single text block

---

### `ocr/` — OCR Engine & Preprocessor

#### OCR Engine (`ocr_engine.py`)

**File:** [`ocr_engine.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/ocr/ocr_engine.py)  
**Purpose:** Converts PDF pages to images and runs Tesseract OCR.

##### `OCREngine` Workflow

```
PDF Page (page_number)
  │
  ├─→ _render_page()          # pdf2image: convert_from_path() at configured DPI
  │     └─→ PIL.Image
  │
  ├─→ _preprocessor.preprocess()  # OpenCV image pipeline
  │     └─→ PIL.Image (cleaned)
  │
  └─→ _run_tesseract()        # pytesseract.image_to_string()
        └─→ str (extracted text)
```

##### Key Configuration
- **DPI:** `ocr_dpi` (default 300) — Higher DPI = better OCR accuracy but slower
- **Language:** `ocr_language` (default `eng`) — Tesseract language pack
- **Timeout:** `ocr_timeout` (default 120s) — Per-page timeout

---

#### Image Preprocessor (`image_preprocessor.py`)

**File:** [`image_preprocessor.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/ocr/image_preprocessor.py)  
**Purpose:** 6-stage OpenCV pipeline to maximise Tesseract OCR accuracy.

##### Preprocessing Stages

| Stage | Method | Technique | Why |
|---|---|---|---|
| 1 | `_to_grayscale()` | `cv2.cvtColor(RGB2GRAY)` | Reduces noise, simplifies thresholding |
| 2 | `_adaptive_threshold()` | Gaussian adaptive threshold (block=11, C=2) | Binarises text vs. background, handles uneven lighting |
| 3 | `_denoise()` | `cv2.fastNlMeansDenoising(h=10)` | Removes speckle noise from scanned pages |
| 4 | `_deskew()` | `cv2.minAreaRect()` + `warpAffine` | Straightens rotated scans (skips if angle < 0.5°) |
| 5 | `_sharpen()` | Unsharp mask (`GaussianBlur` + `addWeighted`) | Enhances edge contrast for character recognition |
| 6 | `_correct_orientation()` | `pytesseract.image_to_osd()` | Auto-detects and corrects page rotation (90°, 180°, 270°) |

Each stage has **individual error handling** — if one stage fails, it silently skips and passes the image unchanged to the next stage.

---

### `cleaner/` — Text Cleaner

**File:** [`text_cleaner.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/cleaner/text_cleaner.py)  
**Purpose:** 7-stage post-extraction text normalisation to remove noise.

##### Cleaning Stages

| Stage | Method | What it does |
|---|---|---|
| 1 | `_normalize_unicode()` | NFKC normalisation — unifies code-point representations (e.g., ﬁ → fi) |
| 2 | `_remove_repeated_headers_footers()` | Frequency analysis across pages. Lines appearing on >40% of pages (min 3) are stripped. Uses first-line/last-line counters. |
| 3 | `_remove_blank_page_markers()` | Collapses runs of 4+ newlines into 3 (removes blank-page artifacts) |
| 4 | `_remove_ocr_garbage()` | Strips non-printable characters and clusters of 3+ consecutive special characters |
| 5 | `_fix_broken_words()` | Rejoins hyphenated line-end splits: `pro-\ngramming` → `programming` |
| 6 | `_normalize_whitespace()` | Collapses multiple spaces/tabs into single spaces per line |
| 7 | `_remove_page_numbers()` | Removes standalone page-number lines (e.g., `— 42 —`, `Page 7 of 50`) |

---

### `utils/` — Utilities

#### Colors (`colors.py`)

**File:** [`colors.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/utils/colors.py)  
**Purpose:** ANSI escape-code helpers for colorized terminal output.

- **Auto-detection:** Respects `NO_COLOR` and `FORCE_COLOR` environment variables; checks `stdout.isatty()`
- **Color functions:** `red()`, `green()`, `yellow()`, `blue()`, `cyan()`, `magenta()`, `bold()`, `dim()`, and bright variants
- **Semantic helpers:** `success()` (green ✓), `error()` (red ✗), `warning()` (yellow ⚠), `info()` (blue ℹ), `header()` (cyan bold)
- **Tags:** `worker_tag(id)` → `[Worker-1]`, `controller_tag()` → `[Controller]`

#### File Utils (`file_utils.py`)

**File:** [`file_utils.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/utils/file_utils.py)

| Function | Description |
|---|---|
| `compute_sha256(filepath)` | Streaming SHA-256 hash computation (64 KB chunks) |
| `ensure_directory(path)` | `mkdir -p` equivalent — creates directory and parents |
| `get_pdf_files(directory)` | Recursively discovers all `.pdf` files, returns sorted list |
| `pdf_to_txt_path(pdf_path, output_dir)` | Derives output `.txt` path: `report.pdf` → `report.txt` |
| `safe_filename(name)` | Sanitises filenames by replacing problematic characters |
| `human_readable_size(size_bytes)` | Converts bytes to `14.2 MB` format |

#### Logger (`logger.py`)

**File:** [`logger.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/utils/logger.py)  
**Purpose:** Dual-file + console logging with colorized console output.

| Handler | Level | Destination |
|---|---|---|
| `pipeline.log` | INFO+ | All events |
| `error.log` | ERROR+ | Errors only |
| Console | INFO+ | Colorized via `_ColorFormatter` |

- Safe to call `setup_logging()` multiple times (duplicate handler prevention)
- `get_logger(name)` — Returns a named child logger

---

### `tests/` — Test Suite

**Directory:** [`tests/`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/tests)

| File | What it tests |
|---|---|
| `test_cleaner.py` | `TextCleaner` — unicode normalisation, broken word fixing, whitespace normalisation, page number removal |
| `test_extractor.py` | `HybridExtractor` — pdfplumber extraction, OCR fallback logic, table extraction |
| `test_validator.py` | `DocumentValidator` — all 10 validation checks, edge cases, thread safety |

Run with: `pytest tests/`

---

## Data Flow

```
HuggingFace API
      │
      ▼
┌─────────────────────┐
│ DatasetDownloader    │ → pdfQA-Benchmark/<subdir>/*.pdf
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ PipelineController   │ → Discovers PDFs recursively
│ (Producer Thread)    │
│                      │
│  ┌────────────────┐  │
│  │ DocumentValidator │ → 10-check pipeline
│  │  ├─ MIME        │  │
│  │  ├─ Extension   │  │
│  │  ├─ Size        │  │
│  │  ├─ Readability │  │
│  │  ├─ Permissions │  │
│  │  ├─ Encryption  │  │
│  │  ├─ Corruption  │  │
│  │  ├─ SHA-256     │  │
│  │  ├─ Virus Scan  │  │
│  │  └─ Logging     │  │
│  └────────────────┘  │
│          │            │
│    pass? │ fail?      │
│     ▼    └──→ skip    │
│ TaskQueue.enqueue()   │
└─────────┬─────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────┐
│ TaskQueue (thread-safe)                               │
│  [pdf1.pdf] [pdf2.pdf] [pdf3.pdf] ... [SENTINEL]     │
└──────────┬───────────────────────────────────────────┘
           │
     ┌─────┼─────┬─────┐
     ▼     ▼     ▼     ▼
  Worker-1  W-2  W-3  W-4    (N consumer threads)
     │
     ▼
┌──────────────────────────┐
│ Per-File Pipeline:       │
│                          │
│ 1. HybridExtractor       │
│    ├─ Column detection   │
│    ├─ pdfplumber text    │
│    ├─ OCR fallback       │
│    └─ Table extraction   │
│                          │
│ 2. LayoutDetector        │
│    └─ Structural analysis│
│                          │
│ 3. MetadataExtractor     │
│    └─ Title, author, etc.│
│                          │
│ 4. TextCleaner           │
│    ├─ Unicode NFKC       │
│    ├─ Header/footer strip│
│    ├─ Hyphen fix         │
│    ├─ Whitespace norm    │
│    └─ Page number strip  │
│                          │
│ 5. Save .txt             │
│    └─ metadata + text    │
└──────────────────────────┘
           │
           ▼
   extracted_files/<stem>.txt
```

---

## Multi-Column Extraction

This is a critical feature that prevents two-column PDF text from being merged into a single line.

### The Problem

pdfplumber's default `extract_text()` reads text left-to-right across the full page width. For a two-column layout, this produces:

```
BXP is committed to strong corporate governance policies and practices The Board of Directors and the Sustainability Committee support efforts to
```

Instead of the correct reading order where the left column is read entirely first, then the right column.

### The Solution — `_extract_text_column_aware()`

The method in [`hybrid_extractor.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/extraction/hybrid_extractor.py) uses a **histogram-based gutter detection** algorithm:

#### Step 1: Build X-Position Histogram
- Extract all character objects from the page via `page.chars`
- Collect every character's `x0` (left edge) position
- Divide the page width into 100 bins
- Count characters in each bin

#### Step 2: Find the Gutter
- Search the **middle region** of the page (25%–75% of width)
- Calculate the average character density across all bins
- Identify bins with density ≤ 10% of average as "empty" (part of the gutter)
- Find the **widest contiguous run** of empty bins

#### Step 3: Validate
- The gutter must span at least ~3% of the page width (≥ 3 bins out of 100)
- If no significant gutter is found → single-column page → use default `extract_text()`

#### Step 4: Split and Extract
- Calculate the split x-coordinate at the gutter's midpoint
- **Crop** the page into left half: `(0, 0, split_x, page_height)` and right half: `(split_x, 0, page_width, page_height)`
- Extract text from each half independently via `cropped.extract_text()`
- Concatenate: left column text + `\n\n` + right column text

### Result

```
BXP is committed to strong corporate governance policies and practices
designed to make the Board of Directors effective in exercising its oversight
role. Our Board of Directors oversee management performance on behalf
...

The Board of Directors and the Sustainability Committee support efforts to
implement our sustainability strategy through our corporate sustainability
program. Our Board-level Sustainability Committee, chaired by BXP Director
...
```

---

## Dependencies

### Python Packages (`requirements.txt`)

| Category | Package | Minimum Version | Purpose |
|---|---|---|---|
| PDF Processing | `pdfplumber` | 0.11.0 | Primary text extraction engine |
| | `PyMuPDF` (`fitz`) | 1.24.0 | Encryption/corruption detection, metadata |
| OCR | `pytesseract` | 0.3.10 | Python wrapper for Tesseract OCR |
| | `pdf2image` | 1.17.0 | Converts PDF pages to PIL Images |
| Image Processing | `opencv-python` | 4.10.0 | OCR preprocessing pipeline |
| | `Pillow` | 10.0.0 | Image manipulation |
| Validation | `python-magic` | 0.4.27 | MIME type detection via file magic bytes |
| Virus Scanning | `pyclamd` | 0.4.0 | ClamAV daemon interface (optional) |
| Networking | `requests` | 2.32.0 | HTTP client for HuggingFace downloads |
| Progress | `tqdm` | 4.66.0 | Progress bars |
| Testing | `pytest` | 8.0.0 | Test runner |

### System-Level Prerequisites

| OS | Command |
|---|---|
| **macOS** | `brew install tesseract poppler libmagic` |
| **Ubuntu** | `sudo apt-get install tesseract-ocr poppler-utils libmagic1` |
| **Windows** | `choco install tesseract poppler` |

---

## Configuration Reference

All configuration is in [`config.py`](file:///Users/arnavpuggal/Desktop/RSS/PDFQA_PIPELINE/config.py) via the `PipelineConfig` frozen dataclass. Modify values directly in the file to tune the pipeline.

See the [config.py section](#configpy--central-configuration) above for a complete field-by-field reference.

---

## Running the Pipeline

### Quick Start

```bash
# 1. Install system dependencies
brew install tesseract poppler libmagic    # macOS

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install Python packages
pip install -r requirements.txt

# 4. Run the pipeline
python app.py
```

### What Happens

1. ASCII banner is displayed
2. Configuration summary is printed
3. Dataset is downloaded from HuggingFace (or skipped if already present)
4. Worker threads are spawned
5. Controller discovers, validates, and enqueues PDFs
6. Workers process the queue (extraction → layout → clean → save)
7. Final statistics are printed
8. Output `.txt` files are in `extracted_files/`

---

## Output Format

Each output `.txt` file contains:

```
--- Document Metadata ---
Title: Example Report
Author: John Doe
Created: D:20220101120000
Pages: 42
--- End Metadata ---

[Extracted and cleaned text content follows...]
```

- **Metadata header** — Only included if the PDF has title or author metadata
- **Cleaned text** — Unicode-normalised, headers/footers removed, hyphens rejoined, whitespace normalised, page numbers stripped
- **Tables** — Formatted as pipe-delimited text blocks with headers
- **Multi-column text** — Left column first, then right column (separated by blank lines)

---

## Error Handling & Logging

### Log Files

| File | Content |
|---|---|
| `logs/pipeline.log` | All events at INFO level and above |
| `logs/error.log` | Only ERROR level events |

### Error Handling Strategy

- **Per-file isolation:** If one PDF fails, the worker logs the error and continues with the next file. No single failure crashes the pipeline.
- **Graceful degradation:** 
  - pdfplumber fails → OCR fallback
  - OCR fails → page marked as "empty"
  - ClamAV unavailable → NoOp scanner (always clean)
  - `python-magic` unavailable → MIME check skipped
  - Image preprocessing stages fail individually → silently skipped
- **Retry with backoff:** Downloads retry up to 3 times with exponential backoff
- **Thread safety:** SHA-256 duplicate registry and queue statistics use `threading.Lock`

### Console Output
All terminal output uses ANSI color codes:
- 🟢 **Green** — Success messages, validation passed, file saved
- 🔴 **Red** — Errors, validation failures
- 🟡 **Yellow** — Warnings, OCR fallback, skipped files
- 🔵 **Blue** — Informational messages
- 🟣 **Magenta** — Worker tags (`[Worker-1]`)
- 🔵 **Cyan** — Controller tag, headers, separators

---

## Testing

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run a specific test file
pytest tests/test_cleaner.py
pytest tests/test_extractor.py
pytest tests/test_validator.py
```

### Test Coverage

| Module | Test File | Covers |
|---|---|---|
| `TextCleaner` | `test_cleaner.py` | Unicode normalisation, broken word fixing, whitespace normalisation, page number removal, header/footer dedup |
| `HybridExtractor` | `test_extractor.py` | pdfplumber extraction, OCR fallback logic, table extraction, per-page method tracking |
| `DocumentValidator` | `test_validator.py` | All 10 validation checks, edge cases (encrypted PDFs, corrupt files, duplicates), thread safety |

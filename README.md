# 📄 PDFQA Enterprise Document Intelligence Pipeline

> **Production-ready**, end-to-end PDF processing pipeline that downloads the
> [pdfQA-Benchmark](https://huggingface.co/datasets/pdfqa/pdfQA-Benchmark) dataset
> from Hugging Face, validates every PDF, intelligently extracts text, performs
> OCR only when required, detects layout and tables, cleans text, and saves a
> `.txt` file for every processed PDF.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                           app.py (Main)                             │
│  1. Download dataset   2. Discover PDFs   3. Launch threads          │
└────────┬─────────────────────────────────────────┬───────────────────┘
         │                                         │
   ┌─────▼──────┐                          ┌──────▼─────────┐
   │ Controller  │──── queue.Queue ────────▶│  Worker (× N)  │
   │ (Producer)  │     (thread-safe)        │  (Consumer)    │
   │             │                          │                │
   │ • Discover  │                          │ • pdfplumber   │
   │ • Validate  │                          │ • OCR fallback │
   │ • Enqueue   │                          │ • Tables       │
   │ • Progress  │                          │ • Layout       │
   │ • Stats     │                          │ • Metadata     │
   └─────────────┘                          │ • Clean        │
                                            │ • Save .txt    │
                                            └────────────────┘
```

### Pipeline Flow

```
Download → Discover → Validate → Enqueue → Extract → OCR* → Layout → Clean → Save
                                                      ↑
                                            * OCR only when pdfplumber
                                              returns None/empty (per page)
```

### Hybrid Extraction Logic (per page)

```python
for every page in the PDF:
    text = pdfplumber.extract_text(page)
    if text is None or text.strip() == "":
        text = OCR(page)        # OpenCV preprocessing + Tesseract
    else:
        use pdfplumber output   # No OCR needed
    merge all pages → final text
```

---

## 📁 Project Structure

```
PDFQA_PIPELINE/
│
├── app.py                          # Main entry point
├── config.py                       # Central configuration
├── requirements.txt                # Python dependencies
├── README.md                       # This file
│
├── controller/
│   ├── __init__.py
│   └── controller.py               # Producer — validates & enqueues PDFs
│
├── worker/
│   ├── __init__.py
│   └── worker.py                   # Consumer — extracts, cleans, saves .txt
│
├── downloader/
│   ├── __init__.py
│   └── dataset_downloader.py       # HuggingFace dataset downloader
│
├── validation/
│   ├── __init__.py
│   ├── validator.py                # 10-check validation pipeline
│   └── virus_scanner.py            # ClamAV abstraction + NoOp fallback
│
├── extraction/
│   ├── __init__.py
│   ├── hybrid_extractor.py         # pdfplumber-first + OCR fallback
│   ├── table_extractor.py          # Table extraction & formatting
│   ├── layout_detector.py          # Layout element detection
│   └── metadata_extractor.py       # PDF metadata extraction
│
├── ocr/
│   ├── __init__.py
│   ├── ocr_engine.py               # Tesseract OCR with pdf2image
│   └── image_preprocessor.py       # OpenCV preprocessing pipeline
│
├── cleaner/
│   ├── __init__.py
│   └── text_cleaner.py             # Post-extraction text normalisation
│
├── queue_manager/
│   ├── __init__.py
│   └── task_queue.py               # Thread-safe task queue
│
├── utils/
│   ├── __init__.py
│   ├── logger.py                   # Logging setup (pipeline.log + error.log)
│   ├── colors.py                   # ANSI terminal colors
│   └── file_utils.py               # File I/O helpers
│
├── tests/
│   ├── __init__.py
│   ├── test_validator.py           # Validation tests
│   ├── test_cleaner.py             # Text cleaning tests
│   └── test_extractor.py           # Extraction tests
│
├── logs/                           # Generated at runtime
│   ├── pipeline.log                # All events (INFO+)
│   └── error.log                   # Errors only (ERROR+)
│
├── dataset/                        # Downloaded PDFs
│   ├── ClimRetrieve/
│   ├── FinanceBench/
│   └── ...
│
└── extracted_files/                # Output .txt files
    ├── report1.txt
    ├── 3M_2022_10K.txt
    └── ...
```

---

## 🚀 Installation

### 1. System Dependencies

**macOS** (Homebrew):
```bash
brew install tesseract poppler libmagic
```

**Ubuntu / Debian**:
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils libmagic1
```

**Windows** (Chocolatey):
```powershell
choco install tesseract poppler
```

### 2. Python Dependencies

```bash
# Python 3.12+ required
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 3. Optional: ClamAV (Virus Scanning)

```bash
# macOS
brew install clamav

# Ubuntu
sudo apt-get install clamav clamav-daemon
sudo freshclam
sudo systemctl start clamav-daemon
```

If ClamAV is not installed, the pipeline will log a warning and skip virus scanning.

### 4. Downloading the Dataset

If anyone wants to download the whole dataset, just download it using the following steps and place it in the `pdfQA-Benchmark` folder.

[pdfQA-Benchmark Dataset](https://huggingface.co/datasets/pdfqa/pdfQA-Benchmark/tree/main/real-pdfQA/01.2_Input_Files_PDF)

#### Method 1 (Recommended): Git LFS

**Step 1: Install Git LFS**
- **macOS (Homebrew)**: `brew install git-lfs`
- **Ubuntu**: `sudo apt install git-lfs`
- **Windows**: Download from [git-lfs.com](https://git-lfs.com/)

**Step 2: Initialize Git LFS**
```bash
git lfs install
```

**Step 3: Clone the Dataset**
Open Terminal, navigate to where you want the dataset (e.g., `cd ~/Documents`), then run:
```bash
git clone https://huggingface.co/datasets/pdfqa/pdfQA-Benchmark
```
Git LFS will automatically download all PDF files. After completion, you'll have:
```text
pdfQA-Benchmark/
└── real-pdfQA/
    └── 01.2_Input_Files_PDF/
        ├── ClimRetrieve/
        ├── ClimateFinanceBench/
        ├── FeTaQA/
        ├── FinQA/
        ├── FinanceBench/
        ├── NaturalQuestions/
        ├── PaperTab/
        ├── PaperText/
        └── Tat-QA/
```

#### Method 2 (Recommended if you only want the PDFs)

Install the Hugging Face CLI:
```bash
pip install -U "huggingface_hub[cli]"
```
Now download only the PDF folder (this downloads only the `01.2_Input_Files_PDF` directory instead of the entire repository):
```bash
huggingface-cli download pdfqa/pdfQA-Benchmark \
    --repo-type dataset \
    --local-dir pdfQA-Benchmark \
    --include "real-pdfQA/01.2_Input_Files_PDF/**"
```

#### Method 3 (Python)

You can also use Python to download it:
```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="pdfqa/pdfQA-Benchmark",
    repo_type="dataset",
    local_dir="pdfQA-Benchmark",
    allow_patterns=["real-pdfQA/01.2_Input_Files_PDF/*"]
)
```

#### Verifying the Download
After downloading using any method, you should see multiple PDF files inside the respective subdirectories under `pdfQA-Benchmark/real-pdfQA/01.2_Input_Files_PDF/`.

---

## ▶️ Execution

```bash
cd PDFQA_PIPELINE
python app.py
```

**That's it.** The pipeline will:

1. ✅ Check for existing dataset → download if needed
2. ✅ Discover all PDF files
3. ✅ Launch worker threads
4. ✅ Validate each PDF (10 checks)
5. ✅ Extract text (pdfplumber + OCR fallback)
6. ✅ Detect layout elements
7. ✅ Clean extracted text
8. ✅ Save `.txt` files to `extracted_files/`
9. ✅ Display colorised progress in the terminal
10. ✅ Print final statistics

---

## ⚙️ Configuration

All settings are in [`config.py`](config.py):

| Setting | Default | Description |
|---|---|---|
| `worker_count` | `4` | Number of parallel extraction threads |
| `ocr_dpi` | `300` | DPI for OCR image rendering |
| `ocr_language` | `"eng"` | Tesseract language code |
| `max_file_size_bytes` | `500 MB` | Maximum PDF file size |
| `min_file_size_bytes` | `100` | Minimum file size (skip empty) |
| `virus_scan_enabled` | `True` | Enable/disable ClamAV scanning |
| `download_max_retries` | `3` | Retry count for failed downloads |
| `download_timeout` | `120` | HTTP request timeout (seconds) |
| `min_page_chars` | `10` | Minimum chars to consider a page non-blank |

---

## 🔍 Validation Pipeline

Every PDF passes through **10 checks** before extraction:

| # | Check | Method |
|---|---|---|
| 1 | MIME type | `python-magic` (magic bytes) |
| 2 | Extension | `.pdf` only |
| 3 | File size | Configurable min/max |
| 4 | Readability | Can the file be opened? |
| 5 | Permissions | `os.access(R_OK)` |
| 6 | Encryption | PyMuPDF `is_encrypted` |
| 7 | Corruption | PyMuPDF page iteration |
| 8 | SHA-256 dedup | In-memory hash registry |
| 9 | Virus scan | ClamAV (graceful skip) |
| 10 | Logging | All results to pipeline.log |

Failed files are **skipped** — processing continues.

---

## 🖥️ Terminal Output

### Controller (Terminal 1)
```
[Controller] Pipeline Controller Started
[Controller] Found 150 PDF files

============================================================
[Controller] Processing [1/150] 3M_2022_10K.pdf
[Controller]  ✓ Validation ✓
[Controller]  ✓ Enqueued ✓
============================================================
```

### Workers (Terminal 2)
```
[Worker-1] Worker Started
[Worker-1] Received 3M_2022_10K.pdf
[Worker-1] Running pdfplumber …
[Worker-1] No text on Page 3 → OCR
[Worker-1]  ✓ OCR ✓ (1 pages)
[Worker-1]  ✓ Layout ✓
[Worker-1]  ✓ TXT Saved ✓ → 3M_2022_10K.txt
[Worker-1] File processed successfully (2.3s)
[Worker-1] Waiting …
```

---

## 📊 Logging

| File | Level | Content |
|---|---|---|
| `logs/pipeline.log` | INFO+ | All events: downloads, validation, extraction, timing |
| `logs/error.log` | ERROR+ | Errors only: failed files, exceptions, tracebacks |

Each log entry includes: timestamp, level, module, file name, duration, and method used.

---

## 🧪 Testing

```bash
cd PDFQA_PIPELINE
python -m pytest tests/ -v
```

Tests cover:
- **Validation**: Valid PDF, invalid extension, empty file, oversized, duplicates, corruption, permissions
- **Text Cleaning**: Unicode normalisation, broken words, whitespace, page numbers, headers
- **Extraction**: pdfplumber text, blank PDF → OCR, mixed pages

---

## 🔧 Troubleshooting

| Issue | Solution |
|---|---|
| `tesseract not found` | Install: `brew install tesseract` (macOS) or `apt-get install tesseract-ocr` (Ubuntu) |
| `poppler not found` | Install: `brew install poppler` (macOS) or `apt-get install poppler-utils` (Ubuntu) |
| `python-magic` errors | Install libmagic: `brew install libmagic` (macOS) or `apt-get install libmagic1` (Ubuntu) |
| Download failures | Check internet connection. The pipeline retries 3× with backoff. Delete partial `.part` files to restart. |
| Memory issues (large PDFs) | Reduce `worker_count` in `config.py` or increase system RAM |
| ClamAV warnings | Non-fatal. Install ClamAV or set `virus_scan_enabled = False` in config |

---

## 📈 Performance Notes

- **Worker count**: 4 workers is optimal for most machines. Increase for high-core-count systems.
- **OCR is slow**: OCR pages take 5–30× longer than pdfplumber. The hybrid approach minimises OCR usage.
- **Large datasets**: The FinanceBench subset alone has 200+ PDFs. Full processing may take 30–60 minutes.
- **Disk space**: Expect ~500 MB for the dataset + ~50 MB for extracted text files.
- **Resume support**: Re-run `python app.py` — already-downloaded files are skipped.

---

## 🔮 Future Enhancements

- [ ] GPU-accelerated OCR (Tesseract 5 / EasyOCR)
- [ ] Parallel page-level OCR within a single PDF
- [ ] PDF-to-Markdown conversion
- [ ] Embedding generation for vector search
- [ ] REST API wrapper (FastAPI)
- [ ] Docker container for reproducible deployment
- [ ] Support for additional datasets
- [ ] LLM-based table structure inference
- [ ] Incremental processing (skip already-extracted files)
- [ ] HTML/XML output format options

---

## 📝 License

This project processes the [pdfQA-Benchmark](https://huggingface.co/datasets/pdfqa/pdfQA-Benchmark) dataset, which is released under the **MIT License**.

---

*Built with enterprise-grade engineering practices: type hints, dataclasses, SOLID principles, PEP 8, logging, modular architecture, and comprehensive testing.*

# 📄 PDFQA Enterprise Document Intelligence Pipeline

> **Production-ready**, end-to-end PDF processing pipeline that downloads the
> [pdfQA-Benchmark](https://huggingface.co/datasets/pdfqa/pdfQA-Benchmark) dataset
> from Hugging Face, validates every PDF, intelligently extracts text, performs
> OCR only when required, detects layout, and saves `.txt` files.
> 
> **✨ NEW:** Now featuring a complete **Semantic Intelligence Layer** with chunking, 
> hybrid search (BM25 + FAISS), knowledge graph extraction, and a **FastAPI** server!

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
   │ • Enqueue   │                          │ • Layout       │
   │ • Progress  │                          │ • Clean        │
   │ • Stats     │                          │ • Save .txt    │
   └─────┬───────┘                          └──────┬─────────┘
         │                                         │
         └────────────────────┬────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │ Phase 7: Semantic │
                    │ Enrichment        │
                    └─────────┬─────────┘
                              │
   ┌──────────────────────────▼────────────────────────────┐
   │  • Parse Hierarchy     • Semantic Chunking            │
   │  • Embeddings (ST)     • Knowledge Graph (spaCy)      │
   │  • SQLite Storage      • FAISS / BM25 Indexing        │
   └──────────────────────────┬────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   FastAPI Server  │
                    │ (Hybrid Search)   │
                    └───────────────────┘
```

### Pipeline Flow

```
Download → Discover → Validate → Enqueue → Extract → OCR* → Clean → Save → Parse → Chunk → Embed → Store
                                                      ↑
                                            * OCR only when pdfplumber
                                              returns None/empty (per page)
```

---

## 📁 Project Structure

```
PDFQA_PIPELINE/
│
├── app.py                          # Main entry point (Runs Phases 1-7)
├── config.py                       # Central configuration
├── requirements.txt                # Python dependencies
├── README.md                       # This file
│
├── controller/                     # Producer — validates & enqueues PDFs
├── worker/                         # Consumer — extracts, cleans, saves .txt
├── downloader/                     # HuggingFace dataset downloader
├── validation/                     # 10-check validation pipeline & Virus scanning
├── extraction/                     # Hybrid Extractor (pdfplumber + OCR), Layout
├── cleaner/                        # Post-extraction text normalisation
├── ocr/                            # Tesseract OCR & OpenCV preprocessing
├── queue_manager/                  # Thread-safe task queue
├── utils/                          # Logging, colors, file I/O
│
├── storage/                        # ✨ NEW: Persistence Layer
│   ├── database.py                 # SQLite WAL mode connection manager
│   ├── models.py                   # Plain Dataclasses (Document, Chunk, Entity, etc.)
│   └── repository.py               # CRUD operations
│
├── semantic/                       # ✨ NEW: Intelligence Layer
│   ├── document_parser.py          # Builds Section hierarchy from flat text
│   ├── chunker.py                  # Structure-aware semantic chunking
│   ├── document_representation.py  # Canonical JSON builder
│   ├── embeddings.py               # sentence-transformers batch embedding
│   ├── knowledge_graph.py          # spaCy NER and relationship extraction
│   └── metadata_enricher.py        # TF-based keyword and doc type extraction
│
├── search/                         # ✨ NEW: Search Engine
│   ├── bm25_index.py               # Lexical search (rank_bm25)
│   ├── vector_store.py             # Semantic search (faiss-cpu)
│   ├── hybrid_search.py            # Reciprocal Rank Fusion (RRF)
│   ├── reranker.py                 # Cross-encoder reranking
│   ├── query_engine.py             # Intent classification & routing
│   └── context_expander.py         # Parent/Child adjacent chunk retrieval
│
├── api/                            # ✨ NEW: REST Server
│   ├── server.py                   # FastAPI application
│   ├── routes_search.py            # Hybrid search endpoints
│   ├── routes_documents.py         # Document retrieval endpoints
│   └── routes_graph.py             # Knowledge Graph endpoints
│
├── dataset/                        # Downloaded PDFs
└── extracted_files/                # Output .txt files
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

*(Optional)* Run `python -m spacy download en_core_web_sm` to pre-download the spaCy NER model for the Knowledge Graph.

### 3. Optional: ClamAV (Virus Scanning)

```bash
# macOS
brew install clamav

# Ubuntu
sudo apt-get install clamav clamav-daemon
sudo freshclam
sudo systemctl start clamav-daemon
```

If ClamAV is not installed, the pipeline will log a warning and skip virus scanning gracefully.

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

### 1. Run the Processing Pipeline

```bash
cd PDFQA_PIPELINE
source venv/bin/activate
python app.py
```

The pipeline will:
1. ✅ Download missing dataset files
2. ✅ Discover all PDFs
3. ✅ Validate each PDF (10 security & integrity checks)
4. ✅ Extract text via Hybrid Engine (pdfplumber + OCR)
5. ✅ Save `.txt` files
6. ✅ **[NEW] Phase 7:** Parse into hierarchical sections, chunk, embed, extract knowledge graph, and save to SQLite/FAISS.

### 2. Run the API Server

Once the pipeline has processed the documents, you can query them using the FastAPI server:

```bash
source venv/bin/activate
python -m api.server
```

The server runs on `http://0.0.0.0:8000`. 
Interactive API documentation:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## ⚙️ Configuration

All settings are in [`config.py`](config.py). Key parameters include:

| Setting | Default | Description |
|---|---|---|
| `worker_count` | `4` | Parallel extraction threads |
| `chunk_target_tokens`| `512` | Token length per semantic chunk |
| `chunk_overlap_tokens`| `64` | Overlap for semantic continuity |
| `embedding_model` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `db_path` | `storage_data/pdfqa.db` | SQLite database path |
| `faiss_index_dir` | `storage_data/faiss_index`| FAISS vector store path |

---

## 🔍 Hybrid Search Engine

The new search engine is highly advanced:
1. **Query Intent Routing:** Analyzes queries (e.g., "compare X and Y", "what is Z") to adjust the blend of lexical vs semantic retrieval (`alpha` value).
2. **Dual Retrieval:** Queries the BM25 Index (exact keywords) and FAISS Vector Store (semantic meaning) concurrently.
3. **Reciprocal Rank Fusion (RRF):** Intelligently merges the rankings from both retrievers.
4. **Cross-Encoder Reranking:** Re-scores the top hits using a cross-encoder model for maximum precision.
5. **Context Expansion:** Fetches adjacent chunks and parent headings from the SQLite database to provide LLMs with complete surrounding context.

---

## 📊 Knowledge Graph

During **Phase 7**, the pipeline runs Named Entity Recognition (NER) via spaCy to identify critical entities (Organizations, People, Tech, Locations). It maps co-occurrences within sentences to build a dense Knowledge Graph of relationships. 
This is stored relationally in SQLite and queryable via the `/api/v1/graph/` endpoints.

---

## 📝 License

This project processes the [pdfQA-Benchmark](https://huggingface.co/datasets/pdfqa/pdfQA-Benchmark) dataset, which is released under the **MIT License**.

---

*Built with enterprise-grade engineering practices: type hints, dataclasses, SOLID principles, PEP 8, logging, modular architecture, and comprehensive testing.*

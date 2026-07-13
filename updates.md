# PDFQA Pipeline — Semantic Intelligence Update Log

This document serves as a comprehensive overview of all architectural enhancements, new methodologies, and shifting paradigms introduced to the PDFQA pipeline. The primary directive for this update was to **extend** the existing extraction pipeline with production-grade semantic document understanding, hybrid search, and knowledge graph capabilities—without altering or breaking the core extraction logic.

---

## 1. The Core Objective

The original system was a robust **Data Ingestion & Extraction Engine**. It successfully took raw PDFs, ran them through security checks, and extracted text via a hybrid `pdfplumber` + `Tesseract OCR` approach, outputting flat `.txt` files.

The new system transforms this into an **Agentic Document Intelligence Platform**. It takes those flat `.txt` files, understands their hierarchical structure, embeds them into dense vector space, extracts entity relationships, and serves them via a high-performance REST API.

---

## 2. Pipeline Flow Comparison

### Previous Flow (The Ingestion Phase)
1. **Download:** Fetch datasets from Hugging Face.
2. **Discover & Validate:** Identify PDFs and run 10-point security/integrity checks.
3. **Enqueue:** Send valid PDFs to a thread-safe Queue.
4. **Extract:** Workers pop PDFs, attempt `pdfplumber`, fallback to `OCR` if empty.
5. **Clean & Save:** Normalize text and save as a flat `extracted_files/report.txt`.
*(The process ended here).*

### New Flow (The Intelligence Phase - Added as Phase 7)
The new flow retains Steps 1–5 identically, and then triggers **Phase 7: Semantic Enrichment**:
6. **Hierarchical Parsing:** Reads the `.txt` file and infers headers, paragraphs, and sections based on regex and whitespace heuristics.
7. **Structure-Aware Chunking:** Splits the sections into 512-token chunks with 64-token overlap, ensuring sentences aren't awkwardly broken in half.
8. **Embeddings:** Passes the chunks through a `sentence-transformers` model (`all-MiniLM-L6-v2`) to generate semantic vectors.
9. **Knowledge Graph (NER):** Runs `spaCy` over the text to extract Named Entities (Organizations, People, Locations, Tech) and maps their relationships.
10. **Storage & Indexing:** 
    - Saves all metadata, text, and entities to a **SQLite** relational database.
    - Saves the vectors to a **FAISS** index.
    - Builds an in-memory **BM25** index for keyword search.
11. **API Serving:** Exposes all this data via a `FastAPI` server supporting Hybrid Search, Knowledge Graph traversal, and Context Expansion.

---

## 3. Advanced Methodologies Implemented

To ensure this is a "production-grade" system, several advanced AI/Search methodologies were implemented:

### A. Structure-Aware Chunking
* **Old way:** Splitting text every 1,000 characters (often cutting words or sentences in half).
* **New Methodology:** The `Chunker` respects document boundaries. It tries to split at the end of paragraphs or sentences. It also implements an **overlap window** (e.g., 64 tokens) so that if a concept bridges two chunks, the context is not lost.

### B. Reciprocal Rank Fusion (RRF) Hybrid Search
* **What it is:** Instead of relying just on keyword matching (which misses synonyms) or just vector matching (which struggles with exact part numbers or names), we use both.
* **Methodology:** The system runs a lexical search via **BM25** and a semantic search via **FAISS** simultaneously. It then mathematically fuses the two ranked lists using RRF: `Score = 1 / (k + rank)`. This guarantees that results appearing highly in *both* lists rise to the absolute top.

### C. Dynamic Intent Routing (Auto-Alpha)
* **What it is:** An engine that analyzes the user's question before searching.
* **Methodology:** The `QueryEngine` uses regex/heuristics to classify the intent of a query. If the user asks for "Summary of...", it relies heavily on Semantic search (FAISS). If the user asks for "Error code 404", it relies heavily on Lexical search (BM25). It adjusts the hybrid `alpha` weighting parameter automatically.

### D. Cross-Encoder Reranking
* **What it is:** A secondary AI pass to double-check the search results.
* **Methodology:** FAISS (Bi-encoders) are fast but slightly inaccurate because they compare vectors independently. Once FAISS retrieves the Top 10 results, we pass the query and the text together into a `Cross-Encoder` (`ms-marco-MiniLM-L-6-v2`). The cross-encoder reads them *together* and gives a highly accurate relevance score, re-ordering the final Top 5 results for the user.

### E. Context Expansion
* **What it is:** Giving LLMs the "bigger picture".
* **Methodology:** When a specific chunk hits as highly relevant, it might be an isolated bullet point. The `ContextExpander` intercepts the result, queries SQLite, and fetches the chunk *before* and the chunk *after* it, as well as the parent Section Title, stitching them together so the LLM has complete context.

### F. Emergency Raw Text Fallback
* **Methodology:** If the semantic pipeline hasn't run yet (e.g., the FAISS index is empty), the API automatically falls back to a brute-force case-insensitive text search across the raw `.txt` files to ensure a search query never fails outright.

---

## 4. Definitions Reference

- **FAISS (Facebook AI Similarity Search):** A library that allows us to search through millions of dense vectors in milliseconds using L2 distance or inner product.
- **BM25:** A highly optimized search algorithm (an evolution of TF-IDF) that ranks documents based on the exact frequency and rarity of the search terms.
- **SQLite WAL Mode:** Write-Ahead Logging. We enabled this in the DB connection so that the API server can read from the database at the exact same time the extraction workers are writing to it, preventing database locks.
- **spaCy NER:** Named Entity Recognition. An NLP model trained to read a sentence and tag words as `ORG` (Organization), `PERSON`, `GPE` (Geopolitical Entity), etc.
- **FastAPI:** A modern, high-performance web framework for building APIs with Python, featuring automatic Swagger UI documentation generation.

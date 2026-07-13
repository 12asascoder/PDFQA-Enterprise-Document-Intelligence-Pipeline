"""
PDFQA Pipeline — Semantic Pipeline Orchestrator

Runs as Phase 7 of the main pipeline. Takes the `.txt` files extracted in
Phases 1-6, parses them into hierarchical sections, chunks them, generates
embeddings, extracts a knowledge graph, enriches metadata, and saves
everything to SQLite and FAISS.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from config import PipelineConfig
from search.bm25_index import BM25Index
from search.vector_store import FAISSVectorStore
from semantic.chunker import SemanticChunker
from semantic.document_parser import IntelligentDocumentParser
from semantic.document_representation import UnifiedDocumentBuilder
from semantic.embeddings import EmbeddingGenerator
from semantic.knowledge_graph import KnowledgeGraphBuilder
from semantic.metadata_enricher import MetadataEnricher
from storage.database import Database
from storage.models import Document
from storage.repository import (
    ChunkRepository,
    DocumentRepository,
    EmbeddingRepository,
    EntityRepository,
    RelationshipRepository,
    SectionRepository,
)
from utils.colors import bright_green, cyan, header, success, warning
from utils.file_utils import compute_sha256

logger = logging.getLogger(__name__)


class SemanticPipeline:
    """Orchestrates the post-extraction semantic enrichment."""

    def __init__(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg
        
        # 1. Init Database
        self.db = Database(cfg.db_path)
        self.db.initialize()
        
        # 2. Init Repositories
        self.doc_repo = DocumentRepository(self.db)
        self.section_repo = SectionRepository(self.db)
        self.chunk_repo = ChunkRepository(self.db)
        self.emb_repo = EmbeddingRepository(self.db)
        self.entity_repo = EntityRepository(self.db)
        self.rel_repo = RelationshipRepository(self.db)
        
        # 3. Init Semantic Tools
        self.parser = IntelligentDocumentParser()
        self.builder = UnifiedDocumentBuilder()
        self.chunker = SemanticChunker(
            target_tokens=cfg.chunk_target_tokens,
            overlap_tokens=cfg.chunk_overlap_tokens
        )
        self.embedder = EmbeddingGenerator(
            model_name=cfg.embedding_model,
            batch_size=cfg.embedding_batch_size
        )
        self.kg_builder = KnowledgeGraphBuilder(
            entity_repo=self.entity_repo,
            rel_repo=self.rel_repo
        )
        self.enricher = MetadataEnricher()
        
        # 4. Init Search Indexes
        self.vector_store = FAISSVectorStore(
            index_dir=cfg.faiss_index_dir,
            dimensions=384  # Adjust based on model
        )
        self.bm25_index = BM25Index()

    def process_all(self) -> None:
        """Process all `.txt` files in the extracted_dir."""
        print(header("\n  Phase 7 — Semantic Enrichment Pipeline …\n"))
        logger.info("Starting Semantic Pipeline on %s", self.cfg.extracted_dir)
        
        txt_files = sorted(self.cfg.extracted_dir.glob("*.txt"))
        if not txt_files:
            print(warning("No .txt files found to process."))
            return

        self.vector_store.load_or_create()
        
        processed_count = 0
        total_chunks = 0
        
        for file_path in txt_files:
            try:
                chunks_added = self._process_file(file_path)
                if chunks_added > 0:
                    processed_count += 1
                    total_chunks += chunks_added
                    print(success(f"Enriched: {file_path.name} ({chunks_added} chunks)"))
                else:
                    logger.debug("Skipped or 0 chunks: %s", file_path.name)
            except Exception as exc:
                logger.error("Failed to process %s: %s", file_path.name, exc, exc_info=True)
                print(warning(f"Failed: {file_path.name} — {exc}"))

        # Build BM25 after all documents are processed
        all_chunks = []
        for doc in self.doc_repo.get_all():
            if doc.id is not None:
                all_chunks.extend(self.chunk_repo.get_by_doc(doc.id))
                
        if all_chunks:
            self.bm25_index.build(all_chunks)
            
        # Save FAISS
        self.vector_store.save()

        print(success(f"Semantic Pipeline Complete! Processed {processed_count} files, generated {total_chunks} embeddings."))
        
        # Print DB stats
        stats = self.db.table_counts()
        print(cyan(f"  Database Stats: {stats}"))

    def _process_file(self, file_path: Path) -> int:
        """Process a single file through the semantic pipeline."""
        
        # 1. Deduplication / Check if already processed
        sha256 = compute_sha256(file_path)
        existing_doc = self.doc_repo.get_by_filename(file_path.name)
        
        if existing_doc and existing_doc.sha256 == sha256 and existing_doc.status == "indexed":
            # Already fully processed
            return 0
            
        # 2. Initialize Document
        text = file_path.read_text(encoding="utf-8")
        
        doc = Document(
            filename=file_path.name,
            sha256=sha256,
            file_size_bytes=file_path.stat().st_size,
            status="parsing"
        )
        
        doc_id = self.doc_repo.upsert(doc)
        doc.id = doc_id
        
        # Clear existing relations if re-processing
        self.section_repo.delete_by_doc(doc_id)
        self.chunk_repo.delete_by_doc(doc_id)
        self.emb_repo.delete_by_doc(doc_id)
        self.entity_repo.delete_by_doc(doc_id)
        self.rel_repo.delete_by_doc(doc_id)

        # 3. Parse Sections
        sections = self.parser.parse(text, doc_id)
        
        # 4. Enrich Metadata
        doc = self.enricher.enrich(doc, sections)
        self.doc_repo.upsert(doc)  # save enriched metadata
        
        # Save sections to DB to get their IDs
        for sec in sections:
            sec.id = self.section_repo.insert(sec)
            
        # 5. Build Unified Representation
        rep = self.builder.build(doc, sections)
        doc.metadata = {"unified_representation": rep}
        self.doc_repo.upsert(doc)
        
        # 6. Chunking
        chunks = self.chunker.chunk_sections(sections)
        if not chunks:
            self.doc_repo.update_status(doc_id, "indexed")
            return 0
            
        for c in chunks:
            c.id = self.chunk_repo.insert(c)
            
        # 7. Embeddings
        embeddings = self.embedder.generate_for_chunks(chunks)
        self.emb_repo.insert_many(embeddings)
        
        # Update FAISS
        self.vector_store.add_embeddings(embeddings)
        
        # 8. Knowledge Graph
        self.kg_builder.process_chunks(chunks, doc_id)
        
        # Done
        self.doc_repo.update_status(doc_id, "indexed")
        
        return len(chunks)

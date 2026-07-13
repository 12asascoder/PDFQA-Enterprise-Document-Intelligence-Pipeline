"""
PDFQA Pipeline — Hybrid Search Engine

Combines results from BM25 (lexical) and FAISS (semantic) using
Reciprocal Rank Fusion (RRF). Fetches full chunk context from SQLite.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from search.bm25_index import BM25Index
from search.vector_store import FAISSVectorStore
from semantic.embeddings import EmbeddingGenerator
from storage.models import SearchResult
from storage.repository import ChunkRepository, DocumentRepository, SectionRepository

logger = logging.getLogger(__name__)


class HybridSearchEngine:
    """Combines BM25 and Vector search results via Reciprocal Rank Fusion."""

    def __init__(
        self,
        bm25: BM25Index,
        vector_store: FAISSVectorStore,
        embedder: EmbeddingGenerator,
        chunk_repo: ChunkRepository,
        doc_repo: DocumentRepository,
        section_repo: SectionRepository,
        rrf_k: int = 60
    ) -> None:
        self.bm25 = bm25
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunk_repo = chunk_repo
        self.doc_repo = doc_repo
        self.section_repo = section_repo
        self.rrf_k = rrf_k

    def search(
        self,
        query: str,
        top_k: int = 10,
        alpha: float = 0.5,  # 0.0 = BM25 only, 1.0 = Vector only, 0.5 = Equal blend
        doc_ids: Optional[List[int]] = None
    ) -> List[SearchResult]:
        """Perform a hybrid search and return enriched results."""
        
        bm25_results: List[SearchResult] = []
        vector_results: List[SearchResult] = []
        
        fetch_k = top_k * 2  # Fetch more for better RRF intersection
        
        # 1. Lexical Search
        if alpha < 1.0:
            bm25_results = self.bm25.search(query, top_k=fetch_k, doc_ids=doc_ids)
            
        # 2. Semantic Search
        if alpha > 0.0:
            try:
                query_vec = self.embedder.embed_query(query)
                vector_results = self.vector_store.search(query_vec, top_k=fetch_k, doc_ids=doc_ids)
            except Exception as exc:
                logger.error("Vector search failed: %s", exc)
                
        # 3. Combine via Reciprocal Rank Fusion
        fused = self._reciprocal_rank_fusion(bm25_results, vector_results, alpha)
        
        # Take top_k
        top_results = fused[:top_k]
        
        # 4. Enrich with database content
        enriched_results = self._enrich_results(top_results)
        
        return enriched_results

    def _reciprocal_rank_fusion(
        self,
        bm25_results: List[SearchResult],
        vector_results: List[SearchResult],
        alpha: float
    ) -> List[SearchResult]:
        """
        Merge results using RRF: score = 1 / (k + rank)
        We also weight the RRF scores by (1-alpha) for BM25 and alpha for Vector.
        """
        rrf_scores: Dict[int, float] = {}  # chunk_id -> rrf_score
        source_map: Dict[int, str] = {}    # chunk_id -> source ('bm25', 'vector', 'hybrid')
        
        # Weight multipliers based on alpha (0.0 to 1.0)
        bm25_weight = (1.0 - alpha) * 2.0  # scale so 0.5 = 1.0, 1.0 = 1.0
        vector_weight = alpha * 2.0
        
        # Process BM25
        for rank, res in enumerate(bm25_results, start=1):
            score = 1.0 / (self.rrf_k + rank) * bm25_weight
            rrf_scores[res.chunk_id] = rrf_scores.get(res.chunk_id, 0.0) + score
            source_map[res.chunk_id] = "bm25"
            
        # Process Vector
        for rank, res in enumerate(vector_results, start=1):
            score = 1.0 / (self.rrf_k + rank) * vector_weight
            rrf_scores[res.chunk_id] = rrf_scores.get(res.chunk_id, 0.0) + score
            
            if res.chunk_id in source_map:
                source_map[res.chunk_id] = "hybrid"
            else:
                source_map[res.chunk_id] = "vector"
                
        # Sort by combined RRF score
        sorted_chunks = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        merged: List[SearchResult] = []
        for chunk_id, score in sorted_chunks:
            # We don't have the content yet, just return a shell SearchResult
            # We assume doc_id can be pulled from the chunk later, but we need it here if possible.
            # We can grab doc_id from whichever result provided it.
            doc_id = next((r.doc_id for r in bm25_results + vector_results if r.chunk_id == chunk_id), 0)
            
            merged.append(SearchResult(
                chunk_id=chunk_id,
                doc_id=doc_id,
                score=score,
                retrieval_source=source_map[chunk_id]
            ))
            
        return merged

    def _enrich_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Fetch Chunk, Section, and Document text from SQLite to populate results."""
        enriched = []
        
        for res in results:
            chunk = self.chunk_repo.get_by_id(res.chunk_id)
            if not chunk:
                continue
                
            res.content = chunk.content
            res.page_number = chunk.page_number
            
            # Fetch document
            doc = self.doc_repo.get_by_id(chunk.doc_id)
            if doc:
                res.document_title = doc.title or doc.filename
                res.filename = doc.filename
                
            # Fetch section
            if chunk.section_id is not None:
                section = self.section_repo.get_by_id(chunk.section_id)
                if section:
                    res.section_title = section.title
                    # In a real app, we might include the whole section content as context
                    # For now, let's just keep the title.
            
            enriched.append(res)
            
        return enriched

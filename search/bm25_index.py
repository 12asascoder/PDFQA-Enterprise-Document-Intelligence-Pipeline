"""
PDFQA Pipeline — BM25 Search Index

In-memory inverted index for lexical search using BM25 Okapi.
Re-built at startup from the database.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple, Optional

try:
    from rank_bm25 import BM25Okapi  # type: ignore
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False

from storage.models import Chunk, SearchResult

logger = logging.getLogger(__name__)


class BM25Index:
    """In-memory BM25 lexical search index."""

    def __init__(self) -> None:
        self._bm25: Optional[BM25Okapi] = None
        self._corpus_ids: List[int] = []       # maps BM25 array index to chunk.id
        self._corpus_docs: List[int] = []      # maps BM25 array index to doc_id
        self._is_built = False

        if not _HAS_BM25:
            logger.warning("rank-bm25 not installed. Lexical search disabled.")

    def build(self, chunks: List[Chunk]) -> None:
        """Build the index from a list of Chunks."""
        if not _HAS_BM25 or not chunks:
            self._bm25 = None
            self._corpus_ids = []
            self._corpus_docs = []
            self._is_built = True
            return

        logger.info("Building BM25 index for %d chunks", len(chunks))
        
        # Tokenize (simple whitespace + lowercasing for BM25)
        # For production, a better tokenizer (e.g. NLTK or regex word boundaries) is ideal.
        tokenized_corpus = []
        self._corpus_ids = []
        self._corpus_docs = []

        for c in chunks:
            if c.id is None:
                continue
            
            # Basic tokenization
            tokens = c.content.lower().split()
            tokenized_corpus.append(tokens)
            
            self._corpus_ids.append(c.id)
            self._corpus_docs.append(c.doc_id)

        self._bm25 = BM25Okapi(tokenized_corpus)
        self._is_built = True
        logger.info("BM25 index built successfully.")

    def search(
        self,
        query: str,
        top_k: int = 10,
        doc_ids: Optional[List[int]] = None
    ) -> List[SearchResult]:
        """Search the BM25 index and return SearchResults.
        
        Parameters
        ----------
        query: str
            The search query.
        top_k: int
            Number of top results to return.
        doc_ids: Optional[List[int]]
            If provided, filter results to only these document IDs.
        """
        if not self._is_built or self._bm25 is None:
            return []

        tokenized_query = query.lower().split()
        
        # Get scores for all documents in the corpus
        doc_scores = self._bm25.get_scores(tokenized_query)
        
        # Filter and sort
        scored_indices: List[Tuple[int, float]] = []
        
        for idx, score in enumerate(doc_scores):
            if score <= 0.0:
                continue
                
            # Apply document filter if requested
            if doc_ids and self._corpus_docs[idx] not in doc_ids:
                continue
                
            scored_indices.append((idx, score))

        # Sort by score descending
        scored_indices.sort(key=lambda x: x[1], reverse=True)
        
        # Take top_k
        top_indices = scored_indices[:top_k]
        
        # Construct SearchResults (content to be filled by the HybridSearch engine)
        results: List[SearchResult] = []
        for idx, score in top_indices:
            chunk_id = self._corpus_ids[idx]
            doc_id = self._corpus_docs[idx]
            
            # Normalize BM25 score roughly (BM25 is unbounded, but we cap/normalize for RRF)
            # The actual RRF in HybridSearch will ignore the absolute score and use ranks anyway.
            
            results.append(SearchResult(
                chunk_id=chunk_id,
                doc_id=doc_id,
                score=score,
                retrieval_source="bm25"
            ))
            
        return results

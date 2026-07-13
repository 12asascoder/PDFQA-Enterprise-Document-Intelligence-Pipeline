"""
PDFQA Pipeline — Cross-Encoder Reranker

Re-scores initial hybrid search results using a more accurate (but slower)
cross-encoder model.
"""

from __future__ import annotations

import logging
from typing import List

try:
    from sentence_transformers import CrossEncoder  # type: ignore
    _HAS_CE = True
except ImportError:
    _HAS_CE = False

from storage.models import SearchResult

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Reranks search results for higher precision."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name
        self._model = None
        
        if not _HAS_CE:
            logger.warning("sentence-transformers not installed. Reranking disabled.")

    def _load_model(self):
        if self._model is None and _HAS_CE:
            logger.info("Loading reranker model: %s", self.model_name)
            self._model = CrossEncoder(self.model_name)

    def rerank(self, query: str, results: List[SearchResult], top_k: int = 10) -> List[SearchResult]:
        """Rerank a list of SearchResults against the query."""
        if not _HAS_CE or not results:
            return results[:top_k]

        self._load_model()
        if self._model is None:
            return results[:top_k]
        
        # Prepare inputs for cross-encoder: list of (query, document) tuples
        model_inputs = [[query, r.content] for r in results]
        
        # Get scores
        try:
            scores = self._model.predict(model_inputs)
            
            # Update scores and sort
            for res, score in zip(results, scores):
                # Cross-encoder scores are logits (unbounded).
                res.score = float(score)
                
            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]
            
        except Exception as exc:
            logger.error("Reranking failed: %s. Returning original results.", exc)
            return results[:top_k]

"""
PDFQA Pipeline — FAISS Vector Store

Manages the FAISS index for vector similarity search.
Supports saving/loading to disk and mapping FAISS integer IDs to database chunk IDs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import faiss  # type: ignore
    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False

from storage.models import Embedding, SearchResult

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """FAISS-based vector search index."""

    def __init__(self, index_dir: Path, dimensions: int = 384) -> None:
        self.index_dir = index_dir
        self.dimensions = dimensions
        
        self.index_path = self.index_dir / "index.faiss"
        self.mapping_path = self.index_dir / "mapping.json"
        
        self._index: Optional[faiss.Index] = None
        
        # Maps FAISS index integer -> chunk_id and doc_id
        # e.g., { 0: {"chunk_id": 42, "doc_id": 1}, ... }
        self._id_mapping: Dict[int, Dict[str, int]] = {}
        
        if not _HAS_FAISS:
            logger.warning("faiss-cpu not installed. Vector search disabled.")

    def load_or_create(self) -> None:
        """Load index from disk if it exists, else create an empty one."""
        if not _HAS_FAISS:
            return

        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        if self.index_path.exists() and self.mapping_path.exists():
            logger.info("Loading FAISS index from %s", self.index_path)
            self._index = faiss.read_index(str(self.index_path))
            
            with open(self.mapping_path, "r") as f:
                raw_mapping = json.load(f)
                # JSON keys are strings, convert back to int
                self._id_mapping = {int(k): v for k, v in raw_mapping.items()}
                
            logger.info("Loaded %d vectors into FAISS.", self._index.ntotal)
        else:
            logger.info("Creating new FAISS IndexFlatL2 with %d dims", self.dimensions)
            # IndexFlatIP (Inner Product) is better for cosine similarity if normalized
            # IndexFlatL2 is standard Euclidean distance
            self._index = faiss.IndexFlatL2(self.dimensions)
            self._id_mapping = {}

    def save(self) -> None:
        """Save the index and mapping to disk."""
        if not _HAS_FAISS or self._index is None:
            return

        logger.info("Saving FAISS index to %s", self.index_path)
        faiss.write_index(self._index, str(self.index_path))
        
        with open(self.mapping_path, "w") as f:
            json.dump(self._id_mapping, f)

    def add_embeddings(self, embeddings: List[Embedding]) -> None:
        """Add a batch of Embeddings to the index."""
        if not _HAS_FAISS or self._index is None or not embeddings:
            return

        # Prepare numpy array of vectors
        vectors = []
        for emb in embeddings:
            # Reconstruct float32 array from bytes
            vec = np.frombuffer(emb.vector_blob, dtype=np.float32)
            if len(vec) != self.dimensions:
                logger.error("Dimension mismatch: expected %d, got %d", self.dimensions, len(vec))
                continue
            vectors.append(vec)

        if not vectors:
            return

        vectors_np = np.vstack(vectors)
        
        # FAISS ntotal is the next available ID
        start_id = self._index.ntotal
        
        # Add to FAISS
        self._index.add(vectors_np)
        
        # Update mapping
        for i, emb in enumerate(embeddings):
            if emb.chunk_id is not None:
                self._id_mapping[start_id + i] = {
                    "chunk_id": emb.chunk_id,
                    "doc_id": emb.doc_id
                }

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        doc_ids: Optional[List[int]] = None
    ) -> List[SearchResult]:
        """Search the FAISS index.
        
        Parameters
        ----------
        query_vector: np.ndarray
            The 1D query vector.
        top_k: int
            Number of results to retrieve. We may retrieve more internally if filtering.
        doc_ids: Optional[List[int]]
            If provided, filter results to these doc_ids.
        """
        if not _HAS_FAISS or self._index is None or self._index.ntotal == 0:
            return []

        # Ensure 2D array
        if len(query_vector.shape) == 1:
            query_vector = np.expand_dims(query_vector, axis=0)
            
        query_vector = query_vector.astype(np.float32)

        # If filtering, fetch more to ensure we have enough post-filter
        fetch_k = top_k * 5 if doc_ids else top_k
        fetch_k = min(fetch_k, self._index.ntotal)

        distances, indices = self._index.search(query_vector, fetch_k)
        
        results: List[SearchResult] = []
        
        # Distances from L2 search: smaller is better.
        # We'll convert to a similarity score (larger is better).
        # Cosine similarity is usually bound [-1, 1], but L2 distances are [0, inf).
        # A simple conversion: score = 1 / (1 + distance)
        
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
                
            idx = int(idx)
            mapping = self._id_mapping.get(idx)
            if not mapping:
                continue
                
            chunk_id = mapping["chunk_id"]
            doc_id = mapping["doc_id"]
            
            # Apply filter
            if doc_ids and doc_id not in doc_ids:
                continue
                
            similarity_score = 1.0 / (1.0 + float(dist))
            
            results.append(SearchResult(
                chunk_id=chunk_id,
                doc_id=doc_id,
                score=similarity_score,
                retrieval_source="vector"
            ))
            
            if len(results) >= top_k:
                break
                
        return results

    def remove_by_doc(self, doc_id: int) -> None:
        """
        FAISS IndexFlatL2 doesn't support direct deletion easily without rebuilding.
        In a production scenario, we'd use an IDMap (IndexIDMap) to remove ids, 
        or rebuild the index periodically.
        For simplicity here, we leave them in FAISS and let the doc_ids filter or 
        database joins ignore them.
        """
        pass

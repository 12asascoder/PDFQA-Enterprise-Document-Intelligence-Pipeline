"""
PDFQA Pipeline — Multi-Level Embeddings Generator

Uses `sentence-transformers` to generate embeddings for Chunks.
Includes batching for performance.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np

# We wrap the import in a try-except to avoid breaking the main pipeline if not installed.
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
    _HAS_ST = True
except ImportError:
    _HAS_ST = False

from storage.models import Chunk, Embedding

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generates dense vector embeddings for chunks."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

        if not _HAS_ST:
            logger.warning("sentence-transformers not installed. Embeddings will not be generated.")

    def _load_model(self):
        if self._model is None and _HAS_ST:
            logger.info("Loading embedding model: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)

    def generate_for_chunks(self, chunks: List[Chunk]) -> List[Embedding]:
        """Generate embeddings for a list of Chunks."""
        if not _HAS_ST:
            return []

        self._load_model()
        if self._model is None:
            return []
            
        if not chunks:
            return []

        texts = [c.content for c in chunks]
        embeddings: List[Embedding] = []

        logger.info("Generating embeddings for %d chunks in batches of %d", len(chunks), self.batch_size)
        
        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]
            batch_chunks = chunks[i:i + self.batch_size]
            
            # encode returns a numpy array of shape (batch_size, dimensions)
            vectors = self._model.encode(batch_texts, convert_to_numpy=True, show_progress_bar=False)
            
            for chunk, vec in zip(batch_chunks, vectors):
                # We store the vector as bytes for SQLite BLOB storage
                # Convert float32 numpy array to bytes
                vec_bytes = vec.astype(np.float32).tobytes()
                
                emb = Embedding(
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    level="chunk",
                    model_name=self.model_name,
                    dimensions=len(vec),
                    vector_blob=vec_bytes
                )
                embeddings.append(emb)

        return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string for searching."""
        if not _HAS_ST:
            raise RuntimeError("sentence-transformers not installed")
            
        self._load_model()
        if self._model is None:
            raise RuntimeError("SentenceTransformer failed to load")
            
        # Returns a 1D numpy array
        return self._model.encode(query, convert_to_numpy=True)

"""
PDFQA Pipeline — Semantic Chunker

Splits hierarchical `Section` content into optimal chunks for embedding
and retrieval. Respects section boundaries (chunks do not cross sections)
and overlaps context to maintain semantic continuity.
"""

from __future__ import annotations

import hashlib
import logging
from typing import List

from storage.models import Chunk, Section

logger = logging.getLogger(__name__)


class SemanticChunker:
    """Chunks section content while respecting structural boundaries."""

    def __init__(
        self,
        target_tokens: int = 512,
        overlap_tokens: int = 64,
        chars_per_token: float = 4.0,  # Rough heuristic
    ) -> None:
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.chars_per_token = chars_per_token
        
        self.target_chars = int(target_tokens * chars_per_token)
        self.overlap_chars = int(overlap_tokens * chars_per_token)

    def chunk_sections(self, sections: List[Section]) -> List[Chunk]:
        """Convert a list of Sections into a list of Chunks."""
        chunks: List[Chunk] = []
        chunk_idx = 0

        for sec in sections:
            if not sec.content.strip():
                continue
                
            # Treat short sections as a single chunk
            if len(sec.content) <= self.target_chars + self.overlap_chars:
                chunks.append(self._create_chunk(sec, sec.content, chunk_idx, 0))
                chunk_idx += 1
                continue

            # Split larger sections with overlap
            text = sec.content
            start = 0
            
            while start < len(text):
                # Calculate end bound
                end = start + self.target_chars
                
                if end >= len(text):
                    # Last chunk
                    chunk_text = text[start:]
                    chunks.append(self._create_chunk(sec, chunk_text, chunk_idx, start))
                    chunk_idx += 1
                    break
                
                # Attempt to snap to the nearest paragraph break or sentence end
                # Look backwards from 'end' for a newline or period
                newline_idx = text.rfind("\n", start + self.target_chars // 2, end)
                if newline_idx != -1:
                    end = newline_idx + 1
                else:
                    period_idx = text.rfind(". ", start + self.target_chars // 2, end)
                    if period_idx != -1:
                        end = period_idx + 2
                
                chunk_text = text[start:end]
                chunks.append(self._create_chunk(sec, chunk_text, chunk_idx, start))
                chunk_idx += 1
                
                # Advance start position, minus overlap
                start = end - self.overlap_chars
                
                # Prevent infinite loops if overlap is too large
                if start <= 0 or end - start <= 0:
                    start = end

        return chunks

    def _create_chunk(self, section: Section, text: str, chunk_index: int, start_char: int) -> Chunk:
        content = text.strip()
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        
        # Estimate tokens
        tokens = int(len(content) / self.chars_per_token)
        
        return Chunk(
            doc_id=section.doc_id,
            section_id=section.id,
            content=content,
            content_hash=h,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=start_char + len(content),
            token_count=tokens,
            page_number=section.page_start,
            metadata_json=section.metadata_json  # Inherit section metadata (e.g. heading context)
        )

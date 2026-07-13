"""
PDFQA Pipeline — Context Expander

Expands the context of a matched chunk by fetching adjacent chunks
and parent section content from the database. This provides richer
context for the LLM.
"""

from __future__ import annotations

import logging
from typing import List

from storage.models import SearchResult
from storage.repository import ChunkRepository, SectionRepository

logger = logging.getLogger(__name__)


class ContextExpander:
    """Expands context for search results."""

    def __init__(self, chunk_repo: ChunkRepository, section_repo: SectionRepository) -> None:
        self.chunk_repo = chunk_repo
        self.section_repo = section_repo

    def expand(self, results: List[SearchResult]) -> List[SearchResult]:
        """Fetch adjacent chunks and append/prepend to result content."""
        for res in results:
            adj = self.chunk_repo.get_adjacent(res.chunk_id)
            
            expanded_content = []
            
            # Prepend previous chunk
            if adj.get("previous"):
                expanded_content.append(adj["previous"].content)
                
            # Add main chunk
            expanded_content.append(res.content)
            
            # Append next chunk
            if adj.get("next"):
                expanded_content.append(adj["next"].content)
                
            # Update the result content with the expanded window
            res.content = "\n\n".join(expanded_content)
            
            # Optionally fetch the entire parent section if it's small enough
            # We skip this for now to avoid blowing up the context window,
            # but we can populate the parent_section_content field.
            chunk = self.chunk_repo.get_by_id(res.chunk_id)
            if chunk and chunk.section_id is not None:
                parent = self.section_repo.get_by_id(chunk.section_id)
                if parent:
                    res.parent_section_content = parent.content

        return results

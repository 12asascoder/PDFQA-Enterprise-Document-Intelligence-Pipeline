"""
PDFQA Pipeline — Unified Document Representation

Builds a single canonical JSON representation of a document and its
structural hierarchy. This representation is stored in the Document's
`metadata_json` field for easy portability and export.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from storage.models import Document, Section

logger = logging.getLogger(__name__)


class UnifiedDocumentBuilder:
    """Builds a unified JSON representation of a Document and its Sections."""

    def __init__(self) -> None:
        pass

    def build(self, doc: Document, sections: List[Section]) -> Dict[str, Any]:
        """
        Merge Document and Section data into a canonical dictionary.
        This dict can be serialized to JSON.
        """
        # Create a mapping of section_id to section children for nesting
        tree = self._build_tree(sections)

        representation = {
            "document": {
                "id": doc.id,
                "filename": doc.filename,
                "sha256": doc.sha256,
                "title": doc.title,
                "author": doc.author,
                "doc_type": doc.doc_type,
                "language": doc.language,
                "metadata": doc.metadata,
                "stats": {
                    "page_count": doc.page_count,
                    "file_size_bytes": doc.file_size_bytes,
                    "section_count": len(sections),
                },
            },
            "hierarchy": tree
        }

        return representation

    def _build_tree(self, sections: List[Section]) -> List[Dict[str, Any]]:
        """Construct a nested tree of sections based on parent_section_id."""
        
        # If the sections don't have DB IDs yet, we can't reliably build a tree.
        # But we can fallback to flat if necessary.
        has_ids = all(s.id is not None for s in sections)
        
        if not has_ids:
            # Flat list if no IDs
            return [self._section_to_dict(s) for s in sections]

        # Map by ID
        sec_map = {s.id: self._section_to_dict(s) for s in sections if s.id is not None}
        
        tree: List[Dict[str, Any]] = []
        
        for s in sections:
            if s.id is None:
                continue
            
            node = sec_map[s.id]
            if s.parent_section_id is None:
                # Root level
                tree.append(node)
            else:
                # Child
                parent = sec_map.get(s.parent_section_id)
                if parent:
                    if "children" not in parent:
                        parent["children"] = []
                    parent["children"].append(node)
                else:
                    # Parent not found (dangling), add to root
                    tree.append(node)
                    
        return tree

    def _section_to_dict(self, section: Section) -> Dict[str, Any]:
        """Convert a Section dataclass to a dictionary."""
        return {
            "id": section.id,
            "type": section.section_type,
            "title": section.title,
            "content": section.content,
            "level": section.level,
            "order_index": section.order_index,
            "metadata": section.metadata,
            # 'children' will be populated by _build_tree
        }

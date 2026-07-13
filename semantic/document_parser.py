"""
PDFQA Pipeline — Intelligent Document Parser

Parses cleaned plain text (from the existing extraction pipeline) into a
hierarchical structure of `Section` objects.  Uses regex heuristics to
detect headings, lists, equations, captions, and paragraphs.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from storage.models import Section

logger = logging.getLogger(__name__)

# Heuristics for structural elements in plain text
_RE_HEADING_1 = re.compile(r"^(?:[IVX]+|\d+)\.\s+[A-Z][A-Za-z0-9\s:–—-]{3,100}$")  # e.g., "1. Introduction" or "I. Executive Summary"
_RE_HEADING_2 = re.compile(r"^(?:\d+\.\d+)\s+[A-Z][A-Za-z0-9\s:–—-]{3,100}$")    # e.g., "1.1 Background"
_RE_HEADING_3 = re.compile(r"^(?:\d+\.\d+\.\d+)\s+[A-Z][A-Za-z0-9\s:–—-]{3,100}$") # e.g., "1.1.1 History"
_RE_HEADING_CAPS = re.compile(r"^[A-Z0-9\s:–—-]{5,80}$") # e.g., "EXECUTIVE SUMMARY"

_RE_LIST_ITEM = re.compile(r"^\s*(?:[-•●▪◦▸►]|\d+[.)]\s|[a-z][.)]\s)")
_RE_FIGURE_CAPTION = re.compile(r"^(?:Figure|Fig\.?|Table|Exhibit)\s+\d+.*", re.IGNORECASE)


class IntelligentDocumentParser:
    """Parses flat text into a hierarchy of Section objects."""

    def __init__(self) -> None:
        pass

    def parse(self, text: str, doc_id: int) -> List[Section]:
        """
        Parse raw text into a list of Sections.
        The returned sections have `doc_id`, `section_type`, `title`,
        `content`, `level`, and `order_index` populated.
        (Note: `parent_section_id` and DB `id` are resolved upon DB insertion).
        """
        lines = text.split("\n")
        sections: List[Section] = []
        
        # We maintain a stack of current active headings to build hierarchy
        # Stack items: (level_int, Section)
        # level 0 = Document root, 1 = H1, 2 = H2, 3 = H3
        
        # Create a root section for anything before the first heading
        current_section = Section(
            doc_id=doc_id,
            section_type="paragraph",
            title="Document Root",
            content="",
            order_index=0,
            level=0
        )
        sections.append(current_section)
        
        active_headings = {0: current_section}
        current_level = 0
        order_idx = 1
        
        current_block: List[str] = []
        current_type = "paragraph"

        def commit_block():
            nonlocal current_block, current_type, order_idx
            if not current_block:
                return
            
            content = "\n".join(current_block).strip()
            if content:
                # If the block itself is just a heading, it starts a new section.
                # But here, blocks are content *under* a heading.
                # We append it to the current_section's content, or create a subsection.
                # For simplicity, we create a new Section object for each logical block,
                # acting as a child of the current active heading.
                
                # To maintain hierarchy in the DB, blocks are sections with higher level
                # than their parent heading.
                
                sec = Section(
                    doc_id=doc_id,
                    section_type=current_type,
                    title=active_headings[current_level].title,
                    content=content,
                    order_index=order_idx,
                    level=current_level + 1
                )
                sections.append(sec)
                order_idx += 1
            
            current_block = []
            current_type = "paragraph"

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Determine line type
            match_level = -1
            line_type = "paragraph"
            
            if _RE_HEADING_1.match(stripped):
                match_level = 1
                line_type = "heading"
            elif _RE_HEADING_2.match(stripped):
                match_level = 2
                line_type = "heading"
            elif _RE_HEADING_3.match(stripped):
                match_level = 3
                line_type = "heading"
            elif _RE_HEADING_CAPS.match(stripped) and not _RE_FIGURE_CAPTION.match(stripped):
                match_level = 1
                line_type = "heading"
            elif _RE_LIST_ITEM.match(stripped):
                line_type = "list_item"
            elif _RE_FIGURE_CAPTION.match(stripped):
                line_type = "caption"
            
            if match_level > 0:
                # We found a heading. Commit previous content block.
                commit_block()
                
                # Create a new heading section
                heading_sec = Section(
                    doc_id=doc_id,
                    section_type="heading",
                    title=stripped[:255],
                    content=stripped,
                    order_index=order_idx,
                    level=match_level
                )
                sections.append(heading_sec)
                order_idx += 1
                
                current_level = match_level
                active_headings[current_level] = heading_sec
                
                # Clear deeper levels
                for k in list(active_headings.keys()):
                    if k > current_level:
                        del active_headings[k]
                        
            else:
                # Accumulate block content
                if line_type != current_type and current_block:
                    # Switch from paragraph to list_item etc.
                    commit_block()
                    current_type = line_type
                
                current_block.append(stripped)

        # Commit final block
        commit_block()

        # Post-process parent IDs. We simulate this by linking to the most recent section
        # of a strictly lower level.
        # This will be properly translated to foreign keys during DB insertion if we set a temporary link.
        # Actually, since we only have the DB IDs after insertion, we can do that in the repository or pipeline.
        # For now, we just rely on `level` and sequential order to rebuild hierarchy.

        return sections

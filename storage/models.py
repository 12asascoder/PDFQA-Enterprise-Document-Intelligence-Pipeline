"""
PDFQA Pipeline — Data Models

Dataclass definitions for all persistent entities: documents, sections,
chunks, embeddings, entities, relationships, and search logs.

These models are transport objects between the pipeline, database, and
API layers.  They do NOT depend on any ORM — plain dataclasses only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------
@dataclass
class Document:
    """Top-level representation of a processed PDF."""

    id: Optional[int] = None
    filename: str = ""
    sha256: str = ""
    page_count: int = 0
    file_size_bytes: int = 0
    title: str = ""
    author: str = ""
    doc_type: str = ""
    language: str = "en"
    metadata_json: str = "{}"
    status: str = "extracted"          # extracted | parsed | indexed
    content: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def metadata(self) -> Dict[str, Any]:
        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @metadata.setter
    def metadata(self, value: Dict[str, Any]) -> None:
        self.metadata_json = json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Section (hierarchical)
# ---------------------------------------------------------------------------
@dataclass
class Section:
    """A structural section within a document (heading, paragraph, table, …)."""

    id: Optional[int] = None
    doc_id: int = 0
    parent_section_id: Optional[int] = None
    section_type: str = "paragraph"    # heading, paragraph, table, figure, list, caption, footnote, reference, appendix, code
    title: str = ""
    content: str = ""
    page_start: int = 0
    page_end: int = 0
    order_index: int = 0
    level: int = 0                     # 0 = top-level, 1 = subsection, …
    metadata_json: str = "{}"

    @property
    def metadata(self) -> Dict[str, Any]:
        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}


# ---------------------------------------------------------------------------
# Chunk
# ---------------------------------------------------------------------------
@dataclass
class Chunk:
    """A semantic chunk of text for retrieval."""

    id: Optional[int] = None
    doc_id: int = 0
    section_id: Optional[int] = None
    content: str = ""
    content_hash: str = ""
    chunk_index: int = 0
    start_char: int = 0
    end_char: int = 0
    token_count: int = 0
    page_number: int = 0
    metadata_json: str = "{}"

    @property
    def metadata(self) -> Dict[str, Any]:
        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
@dataclass
class Embedding:
    """A vector embedding for a chunk, section, or document."""

    id: Optional[int] = None
    chunk_id: Optional[int] = None
    doc_id: int = 0
    level: str = "chunk"               # document | section | chunk
    model_name: str = ""
    dimensions: int = 0
    vector_blob: bytes = b""


# ---------------------------------------------------------------------------
# Knowledge Graph — Entity
# ---------------------------------------------------------------------------
@dataclass
class Entity:
    """A named entity extracted from a document."""

    id: Optional[int] = None
    doc_id: int = 0
    name: str = ""
    entity_type: str = ""              # person, org, date, location, technology, disease, etc.
    count: int = 1
    metadata_json: str = "{}"

    @property
    def metadata(self) -> Dict[str, Any]:
        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}


# ---------------------------------------------------------------------------
# Knowledge Graph — Relationship
# ---------------------------------------------------------------------------
@dataclass
class Relationship:
    """A relationship edge between two entities."""

    id: Optional[int] = None
    source_entity_id: int = 0
    target_entity_id: int = 0
    relation_type: str = ""            # belongs_to, references, implements, etc.
    doc_id: int = 0
    confidence: float = 1.0
    metadata_json: str = "{}"


# ---------------------------------------------------------------------------
# Search Log
# ---------------------------------------------------------------------------
@dataclass
class SearchLog:
    """A record of a search query for analytics."""

    id: Optional[int] = None
    query: str = ""
    intent: str = ""
    results_count: int = 0
    latency_ms: float = 0.0
    strategy: str = ""
    timestamp: Optional[str] = None


# ---------------------------------------------------------------------------
# Search Result (not persisted — used in API responses)
# ---------------------------------------------------------------------------
@dataclass
class SearchResult:
    """A single search result returned by the search engine."""

    chunk_id: int = 0
    doc_id: int = 0
    score: float = 0.0
    content: str = ""
    page_number: int = 0
    section_title: str = ""
    document_title: str = ""
    filename: str = ""
    retrieval_source: str = ""         # bm25 | vector | hybrid
    highlights: str = ""
    parent_section_content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

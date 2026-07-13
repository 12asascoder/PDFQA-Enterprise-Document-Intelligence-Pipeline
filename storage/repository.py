"""
PDFQA Pipeline — Repository Layer

CRUD operations for all persistent entities.  Each repository class
operates on a single table (or a small cluster of related tables) and
translates between ``sqlite3.Row`` objects and the dataclass models
defined in ``storage.models``.

All repositories take a ``Database`` instance and are thread-safe by
virtue of the per-thread connection model in ``Database``.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from storage.database import Database
from storage.models import (
    Chunk,
    Document,
    Embedding,
    Entity,
    Relationship,
    SearchLog,
    Section,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document Repository
# ---------------------------------------------------------------------------
class DocumentRepository:
    """CRUD for the ``documents`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(self, doc: Document) -> int:
        """Insert or update a document.  Returns the document id."""
        existing = self._db.fetchone(
            "SELECT id FROM documents WHERE filename = ?",
            (doc.filename,),
        )
        if existing:
            self._db.execute(
                """UPDATE documents SET
                    sha256=?, page_count=?, file_size_bytes=?, title=?,
                    author=?, doc_type=?, language=?, metadata_json=?,
                    status=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (
                    doc.sha256, doc.page_count, doc.file_size_bytes,
                    doc.title, doc.author, doc.doc_type, doc.language,
                    doc.metadata_json, doc.status, existing["id"],
                ),
            )
            self._db.commit()
            return existing["id"]

        cursor = self._db.execute(
            """INSERT INTO documents
                (filename, sha256, page_count, file_size_bytes, title,
                 author, doc_type, language, metadata_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                doc.filename, doc.sha256, doc.page_count,
                doc.file_size_bytes, doc.title, doc.author,
                doc.doc_type, doc.language, doc.metadata_json,
                doc.status,
            ),
        )
        self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_by_id(self, doc_id: int) -> Optional[Document]:
        row = self._db.fetchone("SELECT * FROM documents WHERE id = ?", (doc_id,))
        return self._row_to_doc(row) if row else None

    def get_by_filename(self, filename: str) -> Optional[Document]:
        row = self._db.fetchone(
            "SELECT * FROM documents WHERE filename = ?", (filename,),
        )
        return self._row_to_doc(row) if row else None

    def get_all(self, status: Optional[str] = None) -> List[Document]:
        if status:
            rows = self._db.fetchall(
                "SELECT * FROM documents WHERE status = ? ORDER BY id",
                (status,),
            )
        else:
            rows = self._db.fetchall("SELECT * FROM documents ORDER BY id")
        return [self._row_to_doc(r) for r in rows]

    def count(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) as cnt FROM documents")
        return row["cnt"] if row else 0

    def update_status(self, doc_id: int, status: str) -> None:
        self._db.execute(
            "UPDATE documents SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, doc_id),
        )
        self._db.commit()

    @staticmethod
    def _row_to_doc(row) -> Document:
        return Document(
            id=row["id"],
            filename=row["filename"],
            sha256=row["sha256"],
            page_count=row["page_count"],
            file_size_bytes=row["file_size_bytes"],
            title=row["title"],
            author=row["author"],
            doc_type=row["doc_type"],
            language=row["language"],
            metadata_json=row["metadata_json"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ---------------------------------------------------------------------------
# Section Repository
# ---------------------------------------------------------------------------
class SectionRepository:
    """CRUD for the ``sections`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, section: Section) -> int:
        cursor = self._db.execute(
            """INSERT INTO sections
                (doc_id, parent_section_id, section_type, title, content,
                 page_start, page_end, order_index, level, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                section.doc_id, section.parent_section_id,
                section.section_type, section.title, section.content,
                section.page_start, section.page_end, section.order_index,
                section.level, section.metadata_json,
            ),
        )
        self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def insert_many(self, sections: List[Section]) -> List[int]:
        ids = []
        for s in sections:
            ids.append(self.insert(s))
        return ids

    def get_by_doc(self, doc_id: int) -> List[Section]:
        rows = self._db.fetchall(
            "SELECT * FROM sections WHERE doc_id = ? ORDER BY order_index",
            (doc_id,),
        )
        return [self._row_to_section(r) for r in rows]

    def get_by_id(self, section_id: int) -> Optional[Section]:
        row = self._db.fetchone("SELECT * FROM sections WHERE id = ?", (section_id,))
        return self._row_to_section(row) if row else None

    def delete_by_doc(self, doc_id: int) -> None:
        self._db.execute("DELETE FROM sections WHERE doc_id = ?", (doc_id,))
        self._db.commit()

    @staticmethod
    def _row_to_section(row) -> Section:
        return Section(
            id=row["id"],
            doc_id=row["doc_id"],
            parent_section_id=row["parent_section_id"],
            section_type=row["section_type"],
            title=row["title"],
            content=row["content"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            order_index=row["order_index"],
            level=row["level"],
            metadata_json=row["metadata_json"],
        )


# ---------------------------------------------------------------------------
# Chunk Repository
# ---------------------------------------------------------------------------
class ChunkRepository:
    """CRUD for the ``chunks`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, chunk: Chunk) -> int:
        cursor = self._db.execute(
            """INSERT INTO chunks
                (doc_id, section_id, content, content_hash, chunk_index,
                 start_char, end_char, token_count, page_number, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.doc_id, chunk.section_id, chunk.content,
                chunk.content_hash, chunk.chunk_index, chunk.start_char,
                chunk.end_char, chunk.token_count, chunk.page_number,
                chunk.metadata_json,
            ),
        )
        self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def insert_many(self, chunks: List[Chunk]) -> List[int]:
        ids = []
        for c in chunks:
            ids.append(self.insert(c))
        return ids

    def get_by_doc(self, doc_id: int) -> List[Chunk]:
        rows = self._db.fetchall(
            "SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index",
            (doc_id,),
        )
        return [self._row_to_chunk(r) for r in rows]

    def get_by_id(self, chunk_id: int) -> Optional[Chunk]:
        row = self._db.fetchone("SELECT * FROM chunks WHERE id = ?", (chunk_id,))
        return self._row_to_chunk(row) if row else None

    def get_by_section(self, section_id: int) -> List[Chunk]:
        rows = self._db.fetchall(
            "SELECT * FROM chunks WHERE section_id = ? ORDER BY chunk_index",
            (section_id,),
        )
        return [self._row_to_chunk(r) for r in rows]

    def get_adjacent(self, chunk_id: int) -> Dict[str, Optional[Chunk]]:
        """Return the previous and next chunk relative to *chunk_id*."""
        chunk = self.get_by_id(chunk_id)
        if not chunk:
            return {"previous": None, "next": None}

        prev_row = self._db.fetchone(
            """SELECT * FROM chunks
               WHERE doc_id = ? AND chunk_index = ?""",
            (chunk.doc_id, chunk.chunk_index - 1),
        )
        next_row = self._db.fetchone(
            """SELECT * FROM chunks
               WHERE doc_id = ? AND chunk_index = ?""",
            (chunk.doc_id, chunk.chunk_index + 1),
        )
        return {
            "previous": self._row_to_chunk(prev_row) if prev_row else None,
            "next": self._row_to_chunk(next_row) if next_row else None,
        }

    def has_hash(self, content_hash: str, doc_id: int) -> bool:
        """Check if a chunk with this hash already exists for the document."""
        row = self._db.fetchone(
            "SELECT id FROM chunks WHERE content_hash = ? AND doc_id = ?",
            (content_hash, doc_id),
        )
        return row is not None

    def delete_by_doc(self, doc_id: int) -> None:
        self._db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self._db.commit()

    def count_by_doc(self, doc_id: int) -> int:
        row = self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM chunks WHERE doc_id = ?", (doc_id,),
        )
        return row["cnt"] if row else 0

    @staticmethod
    def _row_to_chunk(row) -> Chunk:
        return Chunk(
            id=row["id"],
            doc_id=row["doc_id"],
            section_id=row["section_id"],
            content=row["content"],
            content_hash=row["content_hash"],
            chunk_index=row["chunk_index"],
            start_char=row["start_char"],
            end_char=row["end_char"],
            token_count=row["token_count"],
            page_number=row["page_number"],
            metadata_json=row["metadata_json"],
        )


# ---------------------------------------------------------------------------
# Embedding Repository
# ---------------------------------------------------------------------------
class EmbeddingRepository:
    """CRUD for the ``embeddings`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, emb: Embedding) -> int:
        cursor = self._db.execute(
            """INSERT INTO embeddings
                (chunk_id, doc_id, level, model_name, dimensions, vector_blob)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                emb.chunk_id, emb.doc_id, emb.level,
                emb.model_name, emb.dimensions, emb.vector_blob,
            ),
        )
        self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def insert_many(self, embeddings: List[Embedding]) -> List[int]:
        ids = []
        for e in embeddings:
            ids.append(self.insert(e))
        return ids

    def get_by_doc(self, doc_id: int, level: Optional[str] = None) -> List[Embedding]:
        if level:
            rows = self._db.fetchall(
                "SELECT * FROM embeddings WHERE doc_id = ? AND level = ?",
                (doc_id, level),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM embeddings WHERE doc_id = ?", (doc_id,),
            )
        return [self._row_to_emb(r) for r in rows]

    def delete_by_doc(self, doc_id: int) -> None:
        self._db.execute("DELETE FROM embeddings WHERE doc_id = ?", (doc_id,))
        self._db.commit()

    @staticmethod
    def _row_to_emb(row) -> Embedding:
        return Embedding(
            id=row["id"],
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            level=row["level"],
            model_name=row["model_name"],
            dimensions=row["dimensions"],
            vector_blob=row["vector_blob"],
        )


# ---------------------------------------------------------------------------
# Entity Repository
# ---------------------------------------------------------------------------
class EntityRepository:
    """CRUD for the ``entities`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(self, entity: Entity) -> int:
        """Insert or increment count if entity name+type already exists for the doc."""
        existing = self._db.fetchone(
            "SELECT id, count FROM entities WHERE doc_id = ? AND name = ? AND entity_type = ?",
            (entity.doc_id, entity.name, entity.entity_type),
        )
        if existing:
            self._db.execute(
                "UPDATE entities SET count = count + ? WHERE id = ?",
                (entity.count, existing["id"]),
            )
            self._db.commit()
            return existing["id"]

        cursor = self._db.execute(
            """INSERT INTO entities
                (doc_id, name, entity_type, count, metadata_json)
            VALUES (?, ?, ?, ?, ?)""",
            (
                entity.doc_id, entity.name, entity.entity_type,
                entity.count, entity.metadata_json,
            ),
        )
        self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_by_doc(self, doc_id: int, entity_type: Optional[str] = None) -> List[Entity]:
        if entity_type:
            rows = self._db.fetchall(
                "SELECT * FROM entities WHERE doc_id = ? AND entity_type = ? ORDER BY count DESC",
                (doc_id, entity_type),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM entities WHERE doc_id = ? ORDER BY count DESC",
                (doc_id,),
            )
        return [self._row_to_entity(r) for r in rows]

    def get_by_id(self, entity_id: int) -> Optional[Entity]:
        row = self._db.fetchone("SELECT * FROM entities WHERE id = ?", (entity_id,))
        return self._row_to_entity(row) if row else None

    def search_by_name(self, name: str) -> List[Entity]:
        rows = self._db.fetchall(
            "SELECT * FROM entities WHERE name LIKE ? ORDER BY count DESC LIMIT 50",
            (f"%{name}%",),
        )
        return [self._row_to_entity(r) for r in rows]

    def get_all_types(self) -> List[str]:
        rows = self._db.fetchall(
            "SELECT DISTINCT entity_type FROM entities ORDER BY entity_type",
        )
        return [r["entity_type"] for r in rows]

    def delete_by_doc(self, doc_id: int) -> None:
        self._db.execute("DELETE FROM entities WHERE doc_id = ?", (doc_id,))
        self._db.commit()

    @staticmethod
    def _row_to_entity(row) -> Entity:
        return Entity(
            id=row["id"],
            doc_id=row["doc_id"],
            name=row["name"],
            entity_type=row["entity_type"],
            count=row["count"],
            metadata_json=row["metadata_json"],
        )


# ---------------------------------------------------------------------------
# Relationship Repository
# ---------------------------------------------------------------------------
class RelationshipRepository:
    """CRUD for the ``relationships`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, rel: Relationship) -> int:
        cursor = self._db.execute(
            """INSERT INTO relationships
                (source_entity_id, target_entity_id, relation_type,
                 doc_id, confidence, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                rel.source_entity_id, rel.target_entity_id,
                rel.relation_type, rel.doc_id, rel.confidence,
                rel.metadata_json,
            ),
        )
        self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_by_entity(self, entity_id: int) -> List[Relationship]:
        rows = self._db.fetchall(
            """SELECT * FROM relationships
               WHERE source_entity_id = ? OR target_entity_id = ?
               ORDER BY confidence DESC""",
            (entity_id, entity_id),
        )
        return [self._row_to_rel(r) for r in rows]

    def get_by_doc(self, doc_id: int) -> List[Relationship]:
        rows = self._db.fetchall(
            "SELECT * FROM relationships WHERE doc_id = ? ORDER BY confidence DESC",
            (doc_id,),
        )
        return [self._row_to_rel(r) for r in rows]

    def delete_by_doc(self, doc_id: int) -> None:
        self._db.execute("DELETE FROM relationships WHERE doc_id = ?", (doc_id,))
        self._db.commit()

    @staticmethod
    def _row_to_rel(row) -> Relationship:
        return Relationship(
            id=row["id"],
            source_entity_id=row["source_entity_id"],
            target_entity_id=row["target_entity_id"],
            relation_type=row["relation_type"],
            doc_id=row["doc_id"],
            confidence=row["confidence"],
            metadata_json=row["metadata_json"],
        )


# ---------------------------------------------------------------------------
# Search Log Repository
# ---------------------------------------------------------------------------
class SearchLogRepository:
    """CRUD for the ``search_logs`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, log: SearchLog) -> int:
        cursor = self._db.execute(
            """INSERT INTO search_logs
                (query, intent, results_count, latency_ms, strategy)
            VALUES (?, ?, ?, ?, ?)""",
            (
                log.query, log.intent, log.results_count,
                log.latency_ms, log.strategy,
            ),
        )
        self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_recent(self, limit: int = 50) -> List[SearchLog]:
        rows = self._db.fetchall(
            "SELECT * FROM search_logs ORDER BY id DESC LIMIT ?", (limit,),
        )
        return [self._row_to_log(r) for r in rows]

    @staticmethod
    def _row_to_log(row) -> SearchLog:
        return SearchLog(
            id=row["id"],
            query=row["query"],
            intent=row["intent"],
            results_count=row["results_count"],
            latency_ms=row["latency_ms"],
            strategy=row["strategy"],
            timestamp=row["timestamp"],
        )

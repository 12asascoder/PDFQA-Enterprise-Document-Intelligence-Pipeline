"""
PDFQA Pipeline — SQLite Database Manager

Manages the SQLite database lifecycle:
  • Connection pooling (thread-safe via per-thread connections)
  • Schema creation and migration
  • WAL mode for concurrent read performance
  • Backward-compatible: never drops existing tables

Call ``Database(path).initialize()`` once at startup.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
_SCHEMA_SQL = """
-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT NOT NULL UNIQUE,
    sha256          TEXT NOT NULL,
    page_count      INTEGER DEFAULT 0,
    file_size_bytes INTEGER DEFAULT 0,
    title           TEXT DEFAULT '',
    author          TEXT DEFAULT '',
    doc_type        TEXT DEFAULT '',
    language        TEXT DEFAULT 'en',
    metadata_json   TEXT DEFAULT '{}',
    status          TEXT DEFAULT 'extracted',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sections table (hierarchical)
CREATE TABLE IF NOT EXISTS sections (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id            INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    parent_section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    section_type      TEXT NOT NULL,
    title             TEXT DEFAULT '',
    content           TEXT NOT NULL,
    page_start        INTEGER DEFAULT 0,
    page_end          INTEGER DEFAULT 0,
    order_index       INTEGER DEFAULT 0,
    level             INTEGER DEFAULT 0,
    metadata_json     TEXT DEFAULT '{}'
);

-- Chunks table
CREATE TABLE IF NOT EXISTS chunks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id         INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_id     INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    content        TEXT NOT NULL,
    content_hash   TEXT NOT NULL,
    chunk_index    INTEGER DEFAULT 0,
    start_char     INTEGER DEFAULT 0,
    end_char       INTEGER DEFAULT 0,
    token_count    INTEGER DEFAULT 0,
    page_number    INTEGER DEFAULT 0,
    metadata_json  TEXT DEFAULT '{}'
);

-- Embeddings table
CREATE TABLE IF NOT EXISTS embeddings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
    doc_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    level       TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    dimensions  INTEGER NOT NULL,
    vector_blob BLOB NOT NULL
);

-- Knowledge graph entities
CREATE TABLE IF NOT EXISTS entities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id        INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    entity_type   TEXT NOT NULL,
    count         INTEGER DEFAULT 1,
    metadata_json TEXT DEFAULT '{}'
);

-- Knowledge graph relationships
CREATE TABLE IF NOT EXISTS relationships (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type    TEXT NOT NULL,
    doc_id           INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    confidence       REAL DEFAULT 1.0,
    metadata_json    TEXT DEFAULT '{}'
);

-- Search logs
CREATE TABLE IF NOT EXISTS search_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    query         TEXT NOT NULL,
    intent        TEXT DEFAULT '',
    results_count INTEGER DEFAULT 0,
    latency_ms    REAL DEFAULT 0,
    strategy      TEXT DEFAULT '',
    timestamp     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_sections_doc      ON sections(doc_id);
CREATE INDEX IF NOT EXISTS idx_sections_parent   ON sections(parent_section_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc        ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_section    ON chunks(section_id);
CREATE INDEX IF NOT EXISTS idx_chunks_hash       ON chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_embeddings_chunk  ON embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_doc    ON embeddings(doc_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_level  ON embeddings(level);
CREATE INDEX IF NOT EXISTS idx_entities_doc      ON entities(doc_id);
CREATE INDEX IF NOT EXISTS idx_entities_type     ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name     ON entities(name);
CREATE INDEX IF NOT EXISTS idx_rels_source       ON relationships(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_rels_target       ON relationships(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_rels_doc          ON relationships(doc_id);
CREATE INDEX IF NOT EXISTS idx_docs_sha256       ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_docs_status       ON documents(status);
"""


# ---------------------------------------------------------------------------
# Database manager
# ---------------------------------------------------------------------------
class Database:
    """Thread-safe SQLite database manager.

    Each thread gets its own connection via ``threading.local()``.
    WAL mode is enabled for concurrent read performance.

    Parameters
    ----------
    db_path : Path
        Path to the SQLite database file.  Created if it does not exist.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._initialized = False

    @property
    def path(self) -> Path:
        return self._db_path

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        """Create the database file, tables, and indexes.

        Safe to call multiple times — uses ``IF NOT EXISTS``.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()

        conn.executescript(_SCHEMA_SQL)
        conn.executescript(_INDEXES_SQL)
        conn.commit()

        self._initialized = True
        logger.info("Database initialized at %s", self._db_path)

    def close(self) -> None:
        """Close the current thread's connection if open."""
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            conn.close()
            self._local.connection = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def _get_connection(self) -> sqlite3.Connection:
        """Return the current thread's connection (create if needed)."""
        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return conn

    @property
    def connection(self) -> sqlite3.Connection:
        """Public accessor for the current thread's connection."""
        return self._get_connection()

    # ------------------------------------------------------------------
    # Convenience execute helpers
    # ------------------------------------------------------------------
    def execute(
        self,
        sql: str,
        params: tuple = (),
    ) -> sqlite3.Cursor:
        """Execute a single SQL statement and return the cursor."""
        conn = self._get_connection()
        return conn.execute(sql, params)

    def executemany(
        self,
        sql: str,
        params_list: list,
    ) -> sqlite3.Cursor:
        """Execute a SQL statement for each set of parameters."""
        conn = self._get_connection()
        return conn.executemany(sql, params_list)

    def commit(self) -> None:
        """Commit the current transaction."""
        self._get_connection().commit()

    def fetchone(
        self,
        sql: str,
        params: tuple = (),
    ) -> Optional[sqlite3.Row]:
        """Execute and return a single row (or None)."""
        return self.execute(sql, params).fetchone()

    def fetchall(
        self,
        sql: str,
        params: tuple = (),
    ) -> list:
        """Execute and return all rows."""
        return self.execute(sql, params).fetchall()

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    def table_counts(self) -> dict:
        """Return row counts for all tables (useful for diagnostics)."""
        tables = [
            "documents", "sections", "chunks", "embeddings",
            "entities", "relationships", "search_logs",
        ]
        counts = {}
        for table in tables:
            row = self.fetchone(f"SELECT COUNT(*) as cnt FROM {table}")
            counts[table] = row["cnt"] if row else 0
        return counts

"""
PDFQA Pipeline — FastAPI Server

Main entry point for the API layer. Connects to the database and search indexes
and provides REST endpoints.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import CONFIG
from storage.database import Database
from storage.repository import (
    ChunkRepository,
    DocumentRepository,
    EntityRepository,
    RelationshipRepository,
    SearchLogRepository,
    SectionRepository,
)
from search.bm25_index import BM25Index
from search.vector_store import FAISSVectorStore
from semantic.embeddings import EmbeddingGenerator
from search.hybrid_search import HybridSearchEngine
from search.query_engine import QueryEngine
from search.context_expander import ContextExpander

from api.routes_search import router as search_router
from api.routes_documents import router as documents_router
from api.routes_graph import router as graph_router

logger = logging.getLogger(__name__)

# Global instances for dependency injection
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Initializing API Server...")
    
    # Init DB
    db = Database(CONFIG.db_path)
    db.initialize()
    app_state["db"] = db
    
    # Init Repos
    doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db)
    section_repo = SectionRepository(db)
    app_state["doc_repo"] = doc_repo
    app_state["chunk_repo"] = chunk_repo
    app_state["section_repo"] = section_repo
    app_state["entity_repo"] = EntityRepository(db)
    app_state["rel_repo"] = RelationshipRepository(db)
    app_state["search_log_repo"] = SearchLogRepository(db)
    
    # Init Search
    embedder = EmbeddingGenerator(CONFIG.embedding_model, CONFIG.embedding_batch_size)
    vector_store = FAISSVectorStore(CONFIG.faiss_index_dir)
    vector_store.load_or_create()
    
    bm25 = BM25Index()
    # Rebuild BM25 in memory
    logger.info("Rebuilding BM25 index for API...")
    docs = doc_repo.get_all(status="indexed")
    all_chunks = []
    for doc in docs:
        if doc.id is not None:
            all_chunks.extend(chunk_repo.get_by_doc(doc.id))
    bm25.build(all_chunks)
    
    hybrid_search = HybridSearchEngine(
        bm25=bm25,
        vector_store=vector_store,
        embedder=embedder,
        chunk_repo=chunk_repo,
        doc_repo=doc_repo,
        section_repo=section_repo
    )
    app_state["hybrid_search"] = hybrid_search
    app_state["query_engine"] = QueryEngine()
    app_state["context_expander"] = ContextExpander(chunk_repo, section_repo)
    
    yield
    
    # Shutdown
    logger.info("Shutting down API Server...")
    db.close()


app = FastAPI(
    title="PDFQA Document Intelligence API",
    description="REST API for hybrid semantic search and knowledge graph traversal.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pass state via app.state
app.state.components = app_state

# Include Routers
app.include_router(search_router, prefix="/api/v1/search", tags=["Search"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(graph_router, prefix="/api/v1/graph", tags=["Knowledge Graph"])

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)

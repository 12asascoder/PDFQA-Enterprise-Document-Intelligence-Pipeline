"""
PDFQA Pipeline — API Search Routes
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from storage.models import SearchLog

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    doc_ids: Optional[List[int]] = None
    alpha: Optional[float] = None
    expand_context: bool = False


class SearchResponseResult(BaseModel):
    chunk_id: int
    doc_id: int
    score: float
    content: str
    page_number: int
    section_title: str
    document_title: str
    filename: str
    retrieval_source: str
    parent_section_content: str = ""


class SearchResponse(BaseModel):
    query: str
    intent: str
    strategy: str
    results: List[SearchResponseResult]
    latency_ms: float
    total_found: int


def get_components(request: Request):
    return request.app.state.components


@router.post("/", response_model=SearchResponse)
def perform_search(req: SearchRequest, comps: dict = Depends(get_components)):
    start_time = time.time()
    
    query_engine = comps["query_engine"]
    hybrid_search = comps["hybrid_search"]
    context_expander = comps["context_expander"]
    search_log_repo = comps["search_log_repo"]
    
    # 1. Analyze query
    intent, strategy, auto_alpha = query_engine.analyze(req.query)
    
    # Override alpha if provided by user
    alpha = req.alpha if req.alpha is not None else auto_alpha
    
    # 2. Search
    results = hybrid_search.search(
        query=req.query,
        top_k=req.top_k,
        alpha=alpha,
        doc_ids=req.doc_ids
    )
    
    # 3. Expand context if requested
    if req.expand_context:
        results = context_expander.expand(results)
        
    latency_ms = (time.time() - start_time) * 1000
    
    # 4. Log search
    log = SearchLog(
        query=req.query,
        intent=intent,
        results_count=len(results),
        latency_ms=latency_ms,
        strategy=f"{strategy} (alpha={alpha:.2f})"
    )
    search_log_repo.insert(log)
    
    # 5. Format response
    response_results = []
    for r in results:
        response_results.append(SearchResponseResult(
            chunk_id=r.chunk_id,
            doc_id=r.doc_id,
            score=r.score,
            content=r.content,
            page_number=r.page_number,
            section_title=r.section_title,
            document_title=r.document_title,
            filename=r.filename,
            retrieval_source=r.retrieval_source,
            parent_section_content=r.parent_section_content
        ))
        
    return SearchResponse(
        query=req.query,
        intent=intent,
        strategy=f"{strategy} (alpha={alpha:.2f})",
        results=response_results,
        latency_ms=latency_ms,
        total_found=len(response_results)
    )

@router.get("/logs")
def get_search_logs(limit: int = 50, comps: dict = Depends(get_components)):
    logs = comps["search_log_repo"].get_recent(limit)
    return logs

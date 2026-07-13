"""
PDFQA Pipeline — API Document Routes
"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter()


def get_components(request: Request):
    return request.app.state.components


@router.get("/")
def list_documents(status: str = None, comps: dict = Depends(get_components)):
    docs = comps["doc_repo"].get_all(status=status)
    return {"total": len(docs), "documents": docs}


@router.get("/{doc_id}")
def get_document(doc_id: int, comps: dict = Depends(get_components)):
    doc = comps["doc_repo"].get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{doc_id}/representation")
def get_document_representation(doc_id: int, comps: dict = Depends(get_components)):
    """Return the unified hierarchical JSON representation of the document."""
    doc = comps["doc_repo"].get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    rep = doc.metadata.get("unified_representation")
    if not rep:
        raise HTTPException(status_code=404, detail="Representation not built yet")
        
    return rep

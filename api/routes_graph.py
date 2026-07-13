"""
PDFQA Pipeline — API Knowledge Graph Routes
"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Request

router = APIRouter()


def get_components(request: Request):
    return request.app.state.components


@router.get("/entities/{doc_id}")
def get_entities(doc_id: int, entity_type: str = None, comps: dict = Depends(get_components)):
    """Get entities for a document, optionally filtered by type."""
    entities = comps["entity_repo"].get_by_doc(doc_id, entity_type=entity_type)
    return {"doc_id": doc_id, "total": len(entities), "entities": entities}


@router.get("/relationships/{doc_id}")
def get_relationships(doc_id: int, comps: dict = Depends(get_components)):
    """Get relationships for a document."""
    rels = comps["rel_repo"].get_by_doc(doc_id)
    return {"doc_id": doc_id, "total": len(rels), "relationships": rels}


@router.get("/types")
def get_entity_types(comps: dict = Depends(get_components)):
    """Get all unique entity types in the database."""
    types = comps["entity_repo"].get_all_types()
    return {"types": types}


@router.get("/search")
def search_entities(q: str, comps: dict = Depends(get_components)):
    """Fuzzy search for entities by name."""
    entities = comps["entity_repo"].search_by_name(q)
    return {"query": q, "total": len(entities), "entities": entities}

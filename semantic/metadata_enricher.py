"""
PDFQA Pipeline — Metadata Enricher

Analyzes document content to extract topics, keywords, and document types.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, List

from storage.models import Document, Section

logger = logging.getLogger(__name__)


class MetadataEnricher:
    """Enriches document metadata with topics and keywords."""

    # Simple stop words for keyword extraction
    _STOP_WORDS = set([
        "the", "and", "to", "of", "a", "in", "is", "that", "for", "it",
        "as", "was", "with", "be", "by", "on", "not", "he", "i", "this",
        "are", "or", "his", "from", "at", "which", "but", "have", "an",
        "had", "they", "you", "were", "their", "one", "all", "we", "can",
        "her", "has", "there", "been", "if", "more", "when", "will", "would",
        "who", "so", "no"
    ])
    
    _DOC_TYPES = {
        "report": ["report", "annual", "summary", "fiscal", "quarterly", "esg"],
        "paper": ["abstract", "methodology", "conclusion", "references", "arxiv"],
        "manual": ["manual", "guide", "instructions", "troubleshooting", "setup"],
        "financial": ["10-k", "10-q", "earnings", "balance sheet", "revenue"],
        "legal": ["agreement", "contract", "liability", "terms", "party"]
    }

    def __init__(self) -> None:
        pass

    def enrich(self, doc: Document, sections: List[Section]) -> Document:
        """Analyze text and enrich Document metadata inline."""
        
        full_text = " ".join([s.content for s in sections])
        if not full_text:
            return doc
            
        full_text_lower = full_text.lower()
        
        # 1. Document Type Detection
        scores = {dtype: 0 for dtype in self._DOC_TYPES}
        for dtype, keywords in self._DOC_TYPES.items():
            for kw in keywords:
                scores[dtype] += full_text_lower.count(kw)
                
        best_type = max(scores.items(), key=lambda x: x[1])
        if best_type[1] > 2:
            doc.doc_type = best_type[0]
        else:
            doc.doc_type = "general"
            
        # 2. Keyword Extraction (Simple TF)
        words = re.findall(r'\b[a-z]{4,20}\b', full_text_lower)
        filtered = [w for w in words if w not in self._STOP_WORDS]
        counts = Counter(filtered)
        top_keywords = [word for word, count in counts.most_common(10)]
        
        # Update metadata dictionary
        meta = doc.metadata
        meta["auto_keywords"] = top_keywords
        meta["word_count"] = len(words)
        doc.metadata = meta
        
        return doc

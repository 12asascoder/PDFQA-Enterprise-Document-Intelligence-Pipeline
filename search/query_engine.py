"""
PDFQA Pipeline — Query Engine

Analyzes the search query to determine intent and route to the
optimal search strategy.
"""

from __future__ import annotations

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)


class QueryEngine:
    """Classifies query intent and extracts metadata filters."""

    # Simple heuristic regex patterns for intent classification
    _RE_DEFINITION = re.compile(r"^(what is|define|meaning of)\b", re.IGNORECASE)
    _RE_SUMMARY = re.compile(r"^(summarize|summary of|tl;?dr)\b", re.IGNORECASE)
    _RE_PROCEDURE = re.compile(r"^(how to|steps to|guide for)\b", re.IGNORECASE)
    _RE_COMPARISON = re.compile(r"\b(vs|versus|compare|difference between)\b", re.IGNORECASE)

    def __init__(self) -> None:
        pass

    def analyze(self, query: str) -> Tuple[str, str, float]:
        """
        Analyze the query.
        Returns: (intent, strategy, alpha)
        alpha: 0.0 = lexical, 1.0 = semantic, 0.5 = balanced hybrid
        """
        query_lower = query.lower().strip()
        
        # 1. Intent Classification
        if self._RE_DEFINITION.search(query_lower):
            intent = "definition"
            strategy = "semantic"
            alpha = 0.8
        elif self._RE_SUMMARY.search(query_lower):
            intent = "summary"
            strategy = "semantic"
            alpha = 1.0  # Needs deep semantic matching
        elif self._RE_PROCEDURE.search(query_lower):
            intent = "procedure"
            strategy = "hybrid"
            alpha = 0.6
        elif self._RE_COMPARISON.search(query_lower):
            intent = "comparison"
            strategy = "hybrid"
            alpha = 0.5
        elif len(query_lower.split()) < 3:
            # Short queries are usually entity/keyword searches
            intent = "keyword"
            strategy = "lexical"
            alpha = 0.2  # Lean heavily on BM25 for exact keyword matches
        else:
            intent = "qa"
            strategy = "hybrid"
            alpha = 0.7  # Lean slightly semantic for general QA

        logger.debug("Query: '%s' -> Intent: %s, Strategy: %s, Alpha: %.2f", query, intent, strategy, alpha)
        
        return intent, strategy, alpha

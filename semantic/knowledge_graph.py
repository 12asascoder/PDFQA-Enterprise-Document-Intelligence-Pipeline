"""
PDFQA Pipeline — Knowledge Graph Builder

Extracts named entities and basic relationships from chunk text
to construct a knowledge graph.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

try:
    import spacy  # type: ignore
    _HAS_SPACY = True
except ImportError:
    _HAS_SPACY = False

from storage.models import Chunk, Entity, Relationship
from storage.repository import EntityRepository, RelationshipRepository

logger = logging.getLogger(__name__)


class KnowledgeGraphBuilder:
    """Extracts entities and relationships to build a knowledge graph."""

    def __init__(
        self,
        entity_repo: EntityRepository,
        rel_repo: RelationshipRepository,
        model_name: str = "en_core_web_sm"
    ) -> None:
        self.entity_repo = entity_repo
        self.rel_repo = rel_repo
        self.model_name = model_name
        self._nlp = None
        
        if not _HAS_SPACY:
            logger.warning("spacy not installed. Knowledge Graph extraction disabled.")

    def _load_model(self):
        if self._nlp is None and _HAS_SPACY:
            logger.info("Loading spaCy model: %s", self.model_name)
            try:
                self._nlp = spacy.load(self.model_name)
            except OSError:
                logger.error("spaCy model '%s' not found. Please run: python -m spacy download %s", 
                             self.model_name, self.model_name)
                self._nlp = None

    def process_chunks(self, chunks: List[Chunk], doc_id: int) -> None:
        """Extract entities and relationships from chunks and save to DB."""
        if not _HAS_SPACY:
            return

        self._load_model()
        if self._nlp is None:
            return

        logger.info("Extracting Knowledge Graph from %d chunks", len(chunks))

        # We keep a mapping of entity text to DB ID within this document run
        # to efficiently create relationships.
        entity_id_map = {}

        for chunk in chunks:
            text = chunk.content
            if len(text) > 100000:
                # spaCy has a length limit by default, truncate if too long
                text = text[:100000]

            doc = self._nlp(text)
            
            # 1. Extract Entities
            chunk_entities = []
            for ent in doc.ents:
                # Filter out very common or unhelpful types
                if ent.label_ in ["CARDINAL", "ORDINAL", "QUANTITY", "PERCENT"]:
                    continue
                    
                entity_name = ent.text.strip().title()
                if len(entity_name) < 2:
                    continue

                chunk_entities.append((entity_name, ent.label_))
                
                # Upsert entity
                e = Entity(doc_id=doc_id, name=entity_name, entity_type=ent.label_)
                e_id = self.entity_repo.upsert(e)
                entity_id_map[entity_name] = e_id

            # 2. Extract Relationships (Heuristic Co-occurrence in Sentences)
            # A more advanced approach would use dependency parsing.
            for sent in doc.sents:
                sent_ents = [e for e in sent.ents if e.label_ not in ["CARDINAL", "ORDINAL", "QUANTITY", "PERCENT"]]
                
                # If a sentence has multiple entities, link them as 'co_occurs'
                for i in range(len(sent_ents)):
                    for j in range(i + 1, len(sent_ents)):
                        e1 = sent_ents[i].text.strip().title()
                        e2 = sent_ents[j].text.strip().title()
                        
                        id1 = entity_id_map.get(e1)
                        id2 = entity_id_map.get(e2)
                        
                        if id1 and id2 and id1 != id2:
                            rel = Relationship(
                                source_entity_id=id1,
                                target_entity_id=id2,
                                relation_type="co_occurs",
                                doc_id=doc_id,
                                confidence=0.5
                            )
                            self.rel_repo.insert(rel)

"""
S3M Semantic Memory — Concept Graph with Similarity Retrieval
==============================================================
Lightweight concept graph storing doctrinal and battlefield knowledge.
Retrieval uses keyword similarity (TF-IDF style) without embeddings to keep
runtime deterministic on edge hardware.
"""

from __future__ import annotations

import math
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field


class Concept(BaseModel):
    """One semantic concept node in the S3M knowledge graph."""

    concept_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str
    category: str = "general"
    description: str = ""
    keywords: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    access_count: int = 0


class ConceptLink(BaseModel):
    """Directed semantic relation between two concepts."""

    source_id: str
    target_id: str
    relation: str = "related_to"
    strength: float = Field(default=0.5, ge=0.0, le=1.0)


class SemanticQuery(BaseModel):
    """Query parameters for semantic retrieval."""

    keywords: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    limit: int = 10


class SemanticMemory:
    """Thread-safe semantic memory with bounded concept storage."""

    def __init__(self, capacity: int = 5000, max_memory_mb: float = 999.0) -> None:
        """Initialize concept graph capacity and memory budget."""
        self._concepts: Dict[str, Concept] = {}
        self._links: List[ConceptLink] = []
        self._adjacency: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        self._keyword_index: Dict[str, Set[str]] = defaultdict(set)
        self._capacity = max(100, capacity)
        self._max_bytes = int(max(1.0, max_memory_mb) * 1024 * 1024)
        self._entry_bytes: Dict[str, int] = {}
        self._total_bytes = 0
        self._lock = threading.RLock()

    def add_concept(self, concept: Concept) -> str:
        """Add or update a concept and enforce storage limits."""
        with self._lock:
            concept_id = concept.concept_id
            if concept_id in self._concepts:
                self._deindex_concept(self._concepts[concept_id])
                self._total_bytes -= self._entry_bytes.get(concept_id, 0)

            self._concepts[concept_id] = concept
            self._index_concept(concept)
            estimated = self._estimate_concept_bytes(concept)
            self._entry_bytes[concept_id] = estimated
            self._total_bytes += estimated

            self._evict_until_within_limits()
            return concept_id

    def add_link(self, link: ConceptLink) -> None:
        """Add relation edge when both endpoint concepts are present."""
        with self._lock:
            if link.source_id in self._concepts and link.target_id in self._concepts:
                self._links.append(link)
                self._adjacency[link.source_id].append(
                    (link.target_id, link.relation, link.strength)
                )

    def query(
        self,
        keywords: Optional[List[str]] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieve concepts by TF-IDF-style keyword similarity."""
        with self._lock:
            if not keywords and not category:
                return []

            query_tokens = [token.lower() for token in (keywords or [])]
            n_docs = max(len(self._concepts), 1)
            candidates: Dict[str, float] = defaultdict(float)

            for token in query_tokens:
                matching_ids = self._keyword_index.get(token, set())
                if not matching_ids:
                    continue
                # Smooth IDF keeps weights positive and rewards discriminative terms.
                idf = math.log((1 + n_docs) / (1 + len(matching_ids))) + 1.0
                for concept_id in matching_ids:
                    concept = self._concepts.get(concept_id)
                    if concept is None:
                        continue
                    if category and concept.category.lower() != category.lower():
                        continue
                    tf = sum(1 for kw in concept.keywords if kw.lower() == token)
                    tf += 1 if token in concept.name.lower().split() else 0
                    candidates[concept_id] += tf * idf * concept.confidence

            if category and not candidates:
                for concept_id, concept in self._concepts.items():
                    if concept.category.lower() == category.lower():
                        candidates[concept_id] = concept.confidence

            ranked = sorted(
                candidates.items(),
                key=lambda item: (item[1], self._concepts[item[0]].confidence),
                reverse=True,
            )[: max(0, limit)]
            results: List[Dict[str, Any]] = []
            for concept_id, score in ranked:
                concept = self._concepts[concept_id]
                concept.access_count += 1
                results.append(
                    {
                        "concept_id": concept_id,
                        "concept": concept.model_dump(),
                        "score": score,
                    }
                )
            return results

    def get_related(self, concept_id: str, depth: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
        """Traverse graph links to retrieve related concepts up to a depth."""
        with self._lock:
            visited: Set[str] = {concept_id}
            frontier = [concept_id]
            results: List[Dict[str, Any]] = []

            for _ in range(max(0, depth)):
                next_frontier: List[str] = []
                for current_id in frontier:
                    for target_id, relation, strength in self._adjacency.get(current_id, []):
                        if target_id in visited or target_id not in self._concepts:
                            continue
                        visited.add(target_id)
                        next_frontier.append(target_id)
                        results.append(
                            {
                                "concept_id": target_id,
                                "concept": self._concepts[target_id].model_dump(),
                                "relation": relation,
                                "strength": strength,
                            }
                        )
                frontier = next_frontier
                if not frontier:
                    break

            return results[: max(0, limit)]

    def size(self) -> int:
        """Return number of concepts currently retained."""
        with self._lock:
            return len(self._concepts)

    def current_memory_bytes(self) -> int:
        """Return approximate bytes consumed by concept records."""
        with self._lock:
            return self._total_bytes

    def _index_concept(self, concept: Concept) -> None:
        for keyword in concept.keywords:
            self._keyword_index[keyword.lower()].add(concept.concept_id)
        for token in concept.name.lower().split():
            self._keyword_index[token].add(concept.concept_id)
        self._keyword_index[concept.category.lower()].add(concept.concept_id)

    def _deindex_concept(self, concept: Concept) -> None:
        for keyword in concept.keywords:
            self._keyword_index[keyword.lower()].discard(concept.concept_id)
        for token in concept.name.lower().split():
            self._keyword_index[token].discard(concept.concept_id)
        self._keyword_index[concept.category.lower()].discard(concept.concept_id)

    def _remove_concept(self, concept_id: str) -> None:
        concept = self._concepts.get(concept_id)
        if concept is None:
            return
        self._deindex_concept(concept)
        del self._concepts[concept_id]
        self._total_bytes -= self._entry_bytes.pop(concept_id, 0)

        for source_id, neighbors in list(self._adjacency.items()):
            self._adjacency[source_id] = [
                (target_id, relation, strength)
                for target_id, relation, strength in neighbors
                if target_id != concept_id and source_id != concept_id
            ]
            if not self._adjacency[source_id]:
                self._adjacency.pop(source_id, None)

        self._links = [
            link
            for link in self._links
            if link.source_id != concept_id and link.target_id != concept_id
        ]

    def _evict_until_within_limits(self) -> None:
        while self._concepts and (
            len(self._concepts) > self._capacity or self._total_bytes > self._max_bytes
        ):
            worst = min(
                self._concepts.values(),
                key=lambda concept: (concept.confidence, concept.access_count),
            )
            self._remove_concept(worst.concept_id)

    @staticmethod
    def _estimate_concept_bytes(concept: Concept) -> int:
        try:
            return len(concept.model_dump_json().encode("utf-8"))
        except Exception:
            return 512

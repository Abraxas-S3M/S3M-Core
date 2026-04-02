"""Thread-safe graph-indexed store for defensive Threat Genome retrieval."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .models import TTPPhase, ThreatGenome


def _normalize_token(value: str) -> str:
    return value.strip().lower()


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ThreatGenomeStore:
    """In-memory graph-style index for actor genomes and attribution workflows."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._genomes: Dict[str, ThreatGenome] = {}

        self._technique_index: DefaultDict[str, Set[str]] = defaultdict(set)
        self._phase_index: DefaultDict[str, Set[str]] = defaultdict(set)
        self._region_index: DefaultDict[str, Set[str]] = defaultdict(set)
        self._platform_index: DefaultDict[str, Set[str]] = defaultdict(set)
        self._actor_type_index: DefaultDict[str, Set[str]] = defaultdict(set)
        self._tag_index: DefaultDict[str, Set[str]] = defaultdict(set)

    def _remove_from_index(self, index: DefaultDict[str, Set[str]], key: str, actor_id: str) -> None:
        bucket = index.get(key)
        if not bucket:
            return
        bucket.discard(actor_id)
        if not bucket:
            index.pop(key, None)

    def _extract_index_keys(self, genome: ThreatGenome) -> Dict[str, Set[str]]:
        techniques = {technique_id.strip().upper() for technique_id in genome.ttps}
        phases = {ttp.phase.value for ttp in genome.ttps.values()}
        regions = {_normalize_token(region) for region in genome.regions}
        actor_type = {_normalize_token(genome.actor_type)}

        platforms: Set[str] = set()
        if genome.capabilities is not None:
            platforms = {_normalize_token(name) for name in genome.capabilities.platforms}

        tags: Set[str] = {_normalize_token(tag) for tag in genome.tags}
        # Include TTP-level tags as retrieval pivots for tactical analysts.
        for ttp in genome.ttps.values():
            for tag in ttp.tags:
                tags.add(_normalize_token(tag))

        return {
            "techniques": techniques,
            "phases": phases,
            "regions": regions,
            "platforms": platforms,
            "actor_type": actor_type,
            "tags": tags,
        }

    def _index_genome(self, genome: ThreatGenome) -> None:
        keys = self._extract_index_keys(genome)
        actor_id = genome.actor_id
        for technique in keys["techniques"]:
            self._technique_index[technique].add(actor_id)
        for phase in keys["phases"]:
            self._phase_index[phase].add(actor_id)
        for region in keys["regions"]:
            self._region_index[region].add(actor_id)
        for platform in keys["platforms"]:
            self._platform_index[platform].add(actor_id)
        for actor_type in keys["actor_type"]:
            self._actor_type_index[actor_type].add(actor_id)
        for tag in keys["tags"]:
            self._tag_index[tag].add(actor_id)

    def _deindex_genome(self, genome: ThreatGenome) -> None:
        keys = self._extract_index_keys(genome)
        actor_id = genome.actor_id
        for technique in keys["techniques"]:
            self._remove_from_index(self._technique_index, technique, actor_id)
        for phase in keys["phases"]:
            self._remove_from_index(self._phase_index, phase, actor_id)
        for region in keys["regions"]:
            self._remove_from_index(self._region_index, region, actor_id)
        for platform in keys["platforms"]:
            self._remove_from_index(self._platform_index, platform, actor_id)
        for actor_type in keys["actor_type"]:
            self._remove_from_index(self._actor_type_index, actor_type, actor_id)
        for tag in keys["tags"]:
            self._remove_from_index(self._tag_index, tag, actor_id)

    def add_genome(self, genome: ThreatGenome) -> None:
        """Insert a new genome and index all retrieval pivots."""
        if not isinstance(genome, ThreatGenome):
            raise ValueError("genome must be a ThreatGenome instance")
        with self._lock:
            if genome.actor_id in self._genomes:
                raise ValueError(f"Genome already exists for actor_id: {genome.actor_id}")
            self._genomes[genome.actor_id] = genome
            self._index_genome(genome)

    def upsert_genome(self, genome: ThreatGenome) -> None:
        """Insert or replace a genome and refresh index edges."""
        if not isinstance(genome, ThreatGenome):
            raise ValueError("genome must be a ThreatGenome instance")
        with self._lock:
            existing = self._genomes.get(genome.actor_id)
            if existing is not None:
                self._deindex_genome(existing)
            self._genomes[genome.actor_id] = genome
            self._index_genome(genome)

    def refresh_genome(self, actor_id: str) -> None:
        """Rebuild indexes for a genome after in-place mutations."""
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("actor_id must be a non-empty string")
        actor_id = actor_id.strip()
        with self._lock:
            genome = self._genomes.get(actor_id)
            if genome is None:
                raise KeyError(f"Unknown actor_id: {actor_id}")
            self._deindex_genome(genome)
            self._index_genome(genome)

    def rebuild_indexes(self) -> None:
        """Recompute all indexes from stored genomes."""
        with self._lock:
            self._technique_index.clear()
            self._phase_index.clear()
            self._region_index.clear()
            self._platform_index.clear()
            self._actor_type_index.clear()
            self._tag_index.clear()
            for genome in self._genomes.values():
                self._index_genome(genome)

    def get_genome(self, actor_id: str) -> Optional[ThreatGenome]:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("actor_id must be a non-empty string")
        with self._lock:
            return self._genomes.get(actor_id.strip())

    def remove_genome(self, actor_id: str) -> bool:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("actor_id must be a non-empty string")
        actor_id = actor_id.strip()
        with self._lock:
            genome = self._genomes.pop(actor_id, None)
            if genome is None:
                return False
            self._deindex_genome(genome)
            return True

    def list_genomes(self) -> List[ThreatGenome]:
        with self._lock:
            return list(self._genomes.values())

    def _resolve(self, actor_ids: Iterable[str]) -> List[ThreatGenome]:
        genomes = [self._genomes[actor_id] for actor_id in actor_ids if actor_id in self._genomes]
        genomes.sort(key=lambda g: (g.last_activity, g.actor_id), reverse=True)
        return genomes

    def find_by_technique(self, mitre_id: str) -> List[ThreatGenome]:
        if not isinstance(mitre_id, str) or not mitre_id.strip():
            raise ValueError("mitre_id must be a non-empty string")
        key = mitre_id.strip().upper()
        with self._lock:
            return self._resolve(self._technique_index.get(key, set()))

    def find_by_phase(self, phase: str | TTPPhase) -> List[ThreatGenome]:
        phase_value = TTPPhase.from_value(phase).value
        with self._lock:
            return self._resolve(self._phase_index.get(phase_value, set()))

    def find_by_platform(self, platform: str) -> List[ThreatGenome]:
        if not isinstance(platform, str) or not platform.strip():
            raise ValueError("platform must be a non-empty string")
        key = _normalize_token(platform)
        with self._lock:
            return self._resolve(self._platform_index.get(key, set()))

    def find_by_region(self, region: str) -> List[ThreatGenome]:
        if not isinstance(region, str) or not region.strip():
            raise ValueError("region must be a non-empty string")
        key = _normalize_token(region)
        with self._lock:
            return self._resolve(self._region_index.get(key, set()))

    def find_by_tag(self, tag: str) -> List[ThreatGenome]:
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError("tag must be a non-empty string")
        key = _normalize_token(tag)
        with self._lock:
            return self._resolve(self._tag_index.get(key, set()))

    def find_by_actor_type(self, actor_type: str) -> List[ThreatGenome]:
        if not isinstance(actor_type, str) or not actor_type.strip():
            raise ValueError("actor_type must be a non-empty string")
        key = _normalize_token(actor_type)
        with self._lock:
            return self._resolve(self._actor_type_index.get(key, set()))

    def find_similar(self, query_genome: ThreatGenome, top_k: int = 5) -> List[Tuple[str, float]]:
        if not isinstance(query_genome, ThreatGenome):
            raise ValueError("query_genome must be a ThreatGenome instance")
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        with self._lock:
            scored: List[Tuple[str, float]] = []
            for actor_id, genome in self._genomes.items():
                if actor_id == query_genome.actor_id:
                    continue
                score = query_genome.similarity(genome)
                scored.append((actor_id, score))
            scored.sort(key=lambda item: item[1], reverse=True)
            return scored[:top_k]

    def attribute_observations(
        self,
        sequence: Sequence[Dict[str, Any]],
        *,
        top_k: int = 5,
        min_score: float = 0.01,
    ) -> List[Dict[str, Any]]:
        if not isinstance(sequence, Sequence):
            raise ValueError("sequence must be a sequence of observations")
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        if not isinstance(min_score, (float, int)):
            raise ValueError("min_score must be numeric")
        min_score = max(0.0, min(1.0, float(min_score)))

        with self._lock:
            matches: List[Dict[str, Any]] = []
            for genome in self._genomes.values():
                best_chain_id: Optional[str] = None
                best_score = 0.0
                for chain in genome.indicator_chains.values():
                    score = chain.match_observations(sequence)
                    if score > best_score:
                        best_score = score
                        best_chain_id = chain.chain_id
                if best_chain_id is not None and best_score >= min_score:
                    matches.append(
                        {
                            "actor_id": genome.actor_id,
                            "actor_name": genome.actor_name,
                            "chain_id": best_chain_id,
                            "score": best_score,
                        }
                    )

            # Highest-scoring attribution candidates are prioritized for analyst triage.
            matches.sort(key=lambda item: item["score"], reverse=True)
            return matches[:top_k]

    def match_behavior(
        self,
        params: Dict[str, Any],
        *,
        top_k: int = 5,
        min_score: float = 0.01,
    ) -> List[Dict[str, Any]]:
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        if not isinstance(min_score, (float, int)):
            raise ValueError("min_score must be numeric")
        min_score = max(0.0, min(1.0, float(min_score)))

        with self._lock:
            results: List[Dict[str, Any]] = []
            for genome in self._genomes.values():
                best_signature_id: Optional[str] = None
                best_score = 0.0
                for signature in genome.signatures.values():
                    score = signature.match_score(params)
                    if score > best_score:
                        best_score = score
                        best_signature_id = signature.signature_id
                if best_signature_id is not None and best_score >= min_score:
                    results.append(
                        {
                            "actor_id": genome.actor_id,
                            "actor_name": genome.actor_name,
                            "signature_id": best_signature_id,
                            "score": best_score,
                        }
                    )
            results.sort(key=lambda item: item["score"], reverse=True)
            return results[:top_k]

    def get_ttp_coverage_matrix(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            matrix: Dict[str, Dict[str, float]] = {}
            for actor_id, genome in self._genomes.items():
                matrix[actor_id] = genome.get_phase_coverage()
            return matrix

    def get_global_ttp_frequency(self) -> Dict[str, float]:
        """Aggregate confidence-weighted technique frequency across actor genomes."""
        with self._lock:
            counts: DefaultDict[str, float] = defaultdict(float)
            for genome in self._genomes.values():
                for ttp in genome.ttps.values():
                    counts[ttp.technique_id] += ttp.confidence
            return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))

    def get_technique_actors(self) -> Dict[str, List[str]]:
        with self._lock:
            return {
                technique: sorted(actor_ids)
                for technique, actor_ids in sorted(self._technique_index.items())
            }

    def recently_active(
        self,
        *,
        since_hours: float = 24.0,
        as_of: Optional[datetime] = None,
    ) -> List[ThreatGenome]:
        if not isinstance(since_hours, (float, int)) or since_hours < 0:
            raise ValueError("since_hours must be a non-negative number")
        anchor = _ensure_utc(as_of) if as_of else datetime.now(timezone.utc)
        threshold = anchor - timedelta(hours=float(since_hours))
        with self._lock:
            selected = [genome for genome in self._genomes.values() if genome.last_activity >= threshold]
            selected.sort(key=lambda genome: genome.last_activity, reverse=True)
            return selected

    def dormant(
        self,
        *,
        min_days: float = 30.0,
        as_of: Optional[datetime] = None,
    ) -> List[ThreatGenome]:
        if not isinstance(min_days, (float, int)) or min_days < 0:
            raise ValueError("min_days must be a non-negative number")
        anchor = _ensure_utc(as_of) if as_of else datetime.now(timezone.utc)
        threshold = anchor - timedelta(days=float(min_days))
        with self._lock:
            selected = [genome for genome in self._genomes.values() if genome.last_activity < threshold]
            selected.sort(key=lambda genome: genome.last_activity)
            return selected

    def __len__(self) -> int:
        with self._lock:
            return len(self._genomes)

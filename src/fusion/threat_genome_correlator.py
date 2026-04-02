"""Threat Genome Correlation and Evolution Engine.

Takes incoming observations and evolves the Threat Genome library:

  1. Extract genome-relevant features from each observation
  2. Score the observation against every genome in the store
  3. If best score >= threshold -> UPDATE the matched genome
  4. If no match -> CREATE a new genome
  5. Every decision produces an explainable CorrelationVerdict

Scoring gates (all configurable weights):
  - Temporal proximity:  is this genome recently active?
  - Geospatial proximity: does the observation occur where this genome operates?
  - Signature overlap:    do extracted features match known behavioral signatures?
  - Comms overlap:        do communication features match?
  - Cyber fingerprint:    do cyber indicators match?
  - Behavioral tag similarity: do behavior tags align?

The correlator is deterministic and fully testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.threat_genome.models import (
    BehavioralSignature,
    CapabilityProfile,
    GenomeEvolutionEntry,
    PlatformType,
    SignatureType,
    ThreatGenome,
    TTP,
    TTPPhase,
)
from src.threat_genome.genome_store import GenomeStore


@dataclass
class GenomeObservation:
    """Normalised observation input for the genome correlator."""

    observation_id: str = ""
    source_type: str = ""
    source_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    extracted_signature_features: Dict[str, Any] = field(default_factory=dict)
    comms_features: Dict[str, Any] = field(default_factory=dict)
    cyber_features: Dict[str, Any] = field(default_factory=dict)
    behavior_tags: List[str] = field(default_factory=list)
    ttp_hints: List[Dict[str, Any]] = field(default_factory=list)
    raw_confidence: float = 0.5
    classification: str = ""
    threat_level: str = ""
    regions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.observation_id:
            self.observation_id = f"gobs-{uuid.uuid4().hex[:10]}"
        self.raw_confidence = max(0.0, min(1.0, self.raw_confidence))

    @property
    def has_geo(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def to_absorb_features(self) -> Dict[str, Any]:
        return {
            "ttp_hints": list(self.ttp_hints),
            "signature_params": dict(self.extracted_signature_features) if self.extracted_signature_features else {},
            "comms_features": dict(self.comms_features),
            "cyber_features": dict(self.cyber_features),
            "behavior_tags": list(self.behavior_tags),
            "regions": list(self.regions),
            "raw_confidence": self.raw_confidence,
            "threat_level": self.threat_level,
            "classification": self.classification,
        }


@dataclass
class GateScore:
    gate_name: str
    raw_score: float
    weight: float
    weighted_score: float
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate_name,
            "raw_score": round(self.raw_score, 4),
            "weight": round(self.weight, 3),
            "weighted_score": round(self.weighted_score, 4),
            "explanation": self.explanation,
        }


@dataclass
class CorrelationVerdict:
    verdict_id: str = ""
    observation_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decision: str = ""
    matched_genome_id: Optional[str] = None
    matched_genome_name: Optional[str] = None
    created_genome_id: Optional[str] = None
    composite_score: float = 0.0
    threshold: float = 0.0
    gate_scores: List[GateScore] = field(default_factory=list)
    components_updated: List[str] = field(default_factory=list)
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.verdict_id:
            self.verdict_id = f"vrd-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict_id": self.verdict_id,
            "observation_id": self.observation_id,
            "decision": self.decision,
            "matched_genome_id": self.matched_genome_id,
            "matched_genome_name": self.matched_genome_name,
            "created_genome_id": self.created_genome_id,
            "composite_score": round(self.composite_score, 4),
            "threshold": round(self.threshold, 4),
            "gate_scores": [g.to_dict() for g in self.gate_scores],
            "components_updated": self.components_updated,
            "confidence_before": round(self.confidence_before, 4),
            "confidence_after": round(self.confidence_after, 4),
            "explanation": self.explanation,
        }


@dataclass
class MergeRecord:
    merge_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    survivor_id: str = ""
    absorbed_id: str = ""
    reason: str = ""
    store_result: Optional[Dict[str, Any]] = None
    explanation: str = ""

    def __post_init__(self) -> None:
        if not self.merge_id:
            self.merge_id = f"mrg-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "merge_id": self.merge_id,
            "timestamp": self.timestamp.isoformat(),
            "survivor_id": self.survivor_id,
            "absorbed_id": self.absorbed_id,
            "reason": self.reason,
            "store_result": self.store_result,
            "explanation": self.explanation,
        }


class ThreatGenomeCorrelator:
    """Correlation engine that evolves Threat Genomes from observations."""

    def __init__(
        self,
        store: GenomeStore,
        match_threshold: float = 0.30,
        w_temporal: float = 0.15,
        w_geo: float = 0.20,
        w_signature: float = 0.25,
        w_comms: float = 0.10,
        w_cyber: float = 0.15,
        w_tags: float = 0.15,
        max_temporal_gap_hours: float = 720.0,
        max_geo_distance_m: float = 50_000.0,
    ) -> None:
        self.store = store
        self.match_threshold = match_threshold
        self.weights = {
            "temporal": w_temporal,
            "geo": w_geo,
            "signature": w_signature,
            "comms": w_comms,
            "cyber": w_cyber,
            "tags": w_tags,
        }
        self.max_temporal_h = max_temporal_gap_hours
        self.max_geo_m = max_geo_distance_m
        self._verdict_log: List[CorrelationVerdict] = []
        self._merge_log: List[MergeRecord] = []

    def correlate(self, obs: GenomeObservation) -> CorrelationVerdict:
        genomes = self.store.list_genomes()
        if not genomes:
            return self._create_new_genome(obs, best_score=0.0, gate_scores=[])

        best_genome: Optional[ThreatGenome] = None
        best_score = -1.0
        best_gates: List[GateScore] = []

        for genome in genomes:
            gates = self._score_gates(obs, genome)
            composite = sum(g.weighted_score for g in gates)
            if composite > best_score:
                best_score = composite
                best_genome = genome
                best_gates = gates

        if best_score >= self.match_threshold and best_genome is not None:
            return self._update_genome(obs, best_genome, best_score, best_gates)
        return self._create_new_genome(obs, best_score, best_gates)

    def correlate_batch(self, observations: List[GenomeObservation]) -> List[CorrelationVerdict]:
        return [self.correlate(obs) for obs in observations]

    def _score_gates(self, obs: GenomeObservation, genome: ThreatGenome) -> List[GateScore]:
        return [
            self._gate_temporal(obs, genome),
            self._gate_geo(obs, genome),
            self._gate_signature(obs, genome),
            self._gate_comms(obs, genome),
            self._gate_cyber(obs, genome),
            self._gate_tags(obs, genome),
        ]

    def _gate_temporal(self, obs: GenomeObservation, genome: ThreatGenome) -> GateScore:
        w = self.weights["temporal"]
        gap_h = abs((obs.timestamp - genome.last_updated).total_seconds()) / 3600.0
        if gap_h >= self.max_temporal_h:
            return GateScore("temporal", 0.0, w, 0.0, f"Genome dormant {gap_h:.0f}h (max {self.max_temporal_h:.0f}h)")
        raw = 1.0 - (gap_h / self.max_temporal_h)
        return GateScore("temporal", raw, w, raw * w, f"Last active {gap_h:.1f}h ago -> proximity {raw:.2f}")

    def _gate_geo(self, obs: GenomeObservation, genome: ThreatGenome) -> GateScore:
        w = self.weights["geo"]
        if not obs.has_geo and not obs.regions:
            return GateScore("geo", 0.0, w, 0.0, "No geolocation or regions in observation")
        if not genome.regions_of_activity:
            return GateScore("geo", 0.0, w, 0.0, "Genome has no known regions")
        obs_regions = set(r.lower() for r in obs.regions)
        genome_regions = set(r.lower() for r in genome.regions_of_activity)
        overlap = obs_regions & genome_regions
        if overlap:
            raw = min(1.0, len(overlap) / max(1, len(genome_regions)))
            return GateScore("geo", raw, w, raw * w, f"Region overlap: {overlap}")
        return GateScore("geo", 0.0, w, 0.0, "No region overlap")

    def _gate_signature(self, obs: GenomeObservation, genome: ThreatGenome) -> GateScore:
        w = self.weights["signature"]
        if not obs.extracted_signature_features or not genome.signatures:
            return GateScore("signature", 0.0, w, 0.0, "No signature features to compare")
        best = 0.0
        best_name = ""
        for sig in genome.signatures.values():
            score = sig.match_score(obs.extracted_signature_features)
            if score > best:
                best = score
                best_name = sig.name
        expl = f"Best match: '{best_name}' = {best:.3f}" if best_name else "No signature matched"
        return GateScore("signature", best, w, best * w, expl)

    def _gate_comms(self, obs: GenomeObservation, genome: ThreatGenome) -> GateScore:
        w = self.weights["comms"]
        if not obs.comms_features:
            return GateScore("comms", 0.0, w, 0.0, "No comms features in observation")
        comms_sigs = [s for s in genome.signatures.values() if s.signature_type == SignatureType.COMMUNICATION]
        if not comms_sigs:
            return GateScore("comms", 0.0, w, 0.0, "Genome has no comms signatures")
        best = 0.0
        best_name = ""
        for sig in comms_sigs:
            score = sig.match_score(obs.comms_features)
            if score > best:
                best = score
                best_name = sig.name
        return GateScore("comms", best, w, best * w, f"Comms match: '{best_name}' = {best:.3f}" if best_name else "No comms match")

    def _gate_cyber(self, obs: GenomeObservation, genome: ThreatGenome) -> GateScore:
        w = self.weights["cyber"]
        if not obs.cyber_features:
            return GateScore("cyber", 0.0, w, 0.0, "No cyber features in observation")
        if not genome.capabilities:
            return GateScore("cyber", 0.0, w, 0.0, "Genome has no capability profile")
        obs_caps: Set[str] = set()
        for key, val in obs.cyber_features.items():
            if isinstance(val, list):
                obs_caps.update(str(v).lower() for v in val)
            elif isinstance(val, str):
                obs_caps.add(val.lower())
            obs_caps.add(str(key).lower())
        genome_caps = set(c.lower() for c in genome.capabilities.cyber_capabilities)
        if not obs_caps or not genome_caps:
            return GateScore("cyber", 0.0, w, 0.0, "Empty capability sets")
        overlap = obs_caps & genome_caps
        jaccard = len(overlap) / len(obs_caps | genome_caps)
        return GateScore("cyber", jaccard, w, jaccard * w, f"Cyber Jaccard={jaccard:.3f}, overlap={overlap}" if overlap else "No cyber overlap")

    def _gate_tags(self, obs: GenomeObservation, genome: ThreatGenome) -> GateScore:
        w = self.weights["tags"]
        obs_tags = set(t.lower() for t in obs.behavior_tags)
        genome_tags = set(t.lower() for t in genome.tags)
        if not obs_tags or not genome_tags:
            return GateScore("tags", 0.0, w, 0.0, "Empty tag sets")
        overlap = obs_tags & genome_tags
        jaccard = len(overlap) / len(obs_tags | genome_tags)
        return GateScore("tags", jaccard, w, jaccard * w, f"Tag Jaccard={jaccard:.3f}, shared={overlap}")

    def _update_genome(self, obs: GenomeObservation, genome: ThreatGenome, score: float, gates: List[GateScore]) -> CorrelationVerdict:
        conf_before = genome.confidence
        components = genome.absorb_observation(obs.to_absorb_features(), obs.observation_id)
        self.store.upsert_genome(genome)
        verdict = CorrelationVerdict(
            observation_id=obs.observation_id,
            decision="matched",
            matched_genome_id=genome.genome_id,
            matched_genome_name=genome.actor_name,
            composite_score=score,
            threshold=self.match_threshold,
            gate_scores=gates,
            components_updated=components,
            confidence_before=conf_before,
            confidence_after=genome.confidence,
            explanation=self._build_match_explanation(obs, genome, score, gates),
        )
        self._verdict_log.append(verdict)
        return verdict

    def _create_new_genome(self, obs: GenomeObservation, best_score: float, gate_scores: List[GateScore]) -> CorrelationVerdict:
        genome = ThreatGenome(
            actor_name=obs.classification or f"Unknown-{obs.observation_id[:8]}",
            actor_type="unknown",
            regions=set(obs.regions),
            threat_rating=obs.threat_level or "unknown",
            confidence=obs.raw_confidence * 0.6,
            tags=set(t.lower() for t in obs.behavior_tags),
        )
        components = genome.absorb_observation(obs.to_absorb_features(), obs.observation_id)
        self.store.add_genome(genome)
        verdict = CorrelationVerdict(
            observation_id=obs.observation_id,
            decision="created",
            created_genome_id=genome.genome_id,
            composite_score=best_score,
            threshold=self.match_threshold,
            gate_scores=gate_scores,
            components_updated=components,
            confidence_before=0.0,
            confidence_after=genome.confidence,
            explanation=self._build_create_explanation(obs, best_score),
        )
        self._verdict_log.append(verdict)
        return verdict

    def merge(self, survivor_id: str, absorbed_id: str, reason: str = "") -> MergeRecord:
        result = self.store.merge_genomes(survivor_id, absorbed_id, reason)
        if result:
            explanation = (
                f"Merged '{result['absorbed_name']}' into '{result['survivor_name']}'. "
                f"{result['components_absorbed']} components absorbed. "
                f"Aliases: {result['survivor_post_merge']['aliases']}. "
                f"Confidence: {result['survivor_pre_merge']['confidence']:.3f} -> "
                f"{result['survivor_post_merge']['confidence']:.3f}."
            )
        else:
            explanation = f"Merge failed: genome(s) ({survivor_id}, {absorbed_id}) not found."
        record = MergeRecord(
            survivor_id=survivor_id,
            absorbed_id=absorbed_id,
            reason=reason,
            store_result=result,
            explanation=explanation,
        )
        self._merge_log.append(record)
        return record

    def _build_match_explanation(self, obs: GenomeObservation, genome: ThreatGenome, score: float, gates: List[GateScore]) -> str:
        top_gates = sorted(gates, key=lambda g: g.weighted_score, reverse=True)
        top_factors = [f"{g.gate_name}={g.raw_score:.2f}" for g in top_gates[:3] if g.raw_score > 0]
        return (
            f"Observation {obs.observation_id} matched genome "
            f"'{genome.actor_name}' (score={score:.3f}, threshold={self.match_threshold:.3f}). "
            f"Top factors: {', '.join(top_factors)}. "
            f"{len(obs.behavior_tags)} tags, {len(obs.ttp_hints)} TTP hints absorbed."
        )

    def _build_create_explanation(self, obs: GenomeObservation, best_score: float) -> str:
        return (
            f"Observation {obs.observation_id} did not match any genome "
            f"(best={best_score:.3f}, threshold={self.match_threshold:.3f}). "
            f"New genome from source={obs.source_type}, "
            f"class='{obs.classification}', conf={obs.raw_confidence:.2f}."
        )

    @staticmethod
    def from_fusion_observation(obs: Any) -> GenomeObservation:
        features = getattr(obs, "extracted_features", {}) or {}
        sig_features: Dict[str, Any] = {}
        comms_features: Dict[str, Any] = {}
        cyber_features: Dict[str, Any] = {}
        for key, val in features.items():
            kl = key.lower()
            if any(k in kl for k in ["freq", "burst", "signal", "comm", "protocol"]):
                comms_features[key] = val
            elif any(k in kl for k in ["ioc", "hash", "ip", "domain", "malware", "c2"]):
                cyber_features[key] = val
            else:
                sig_features[key] = val
        source_domain = getattr(obs, "source_domain", None)
        source_type = source_domain.value if hasattr(source_domain, "value") else str(source_domain or "unknown")
        return GenomeObservation(
            observation_id=getattr(obs, "observation_id", ""),
            source_type=source_type,
            source_id=getattr(obs, "source_id", ""),
            timestamp=getattr(obs, "timestamp", datetime.now(timezone.utc)),
            latitude=getattr(obs, "latitude", None),
            longitude=getattr(obs, "longitude", None),
            extracted_signature_features=sig_features,
            comms_features=comms_features,
            cyber_features=cyber_features,
            behavior_tags=list(getattr(obs, "tags", [])),
            raw_confidence=float(getattr(obs, "initial_confidence", 0.5)),
            classification=getattr(obs, "classification", ""),
            threat_level=features.get("threat_level", ""),
            regions=[str(r) for r in features.get("regions", [])],
        )

    def get_verdict_log(self, last_n: int = 30) -> List[Dict[str, Any]]:
        return [v.to_dict() for v in self._verdict_log[-last_n:]]

    def get_merge_log(self, last_n: int = 20) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._merge_log[-last_n:]]

    def stats(self) -> Dict[str, Any]:
        verdicts = self._verdict_log
        return {
            "total_correlations": len(verdicts),
            "matched": sum(1 for v in verdicts if v.decision == "matched"),
            "created": sum(1 for v in verdicts if v.decision == "created"),
            "merges": len(self._merge_log),
            "store_genomes": self.store.count(),
        }

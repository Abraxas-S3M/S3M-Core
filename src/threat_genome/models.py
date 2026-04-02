"""Threat Genome core models for defensive actor profiling and attribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def _normalize_token(value: str) -> str:
    return value.strip().lower()


def _safe_jaccard(left: Set[str], right: Set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


class TTPPhase(str, Enum):
    """Extended kill-chain phases across cyber, kinetic, EW, ISR, and logistics."""

    RECONNAISSANCE = "reconnaissance"
    RESOURCE_DEVELOPMENT = "resource_development"
    INITIAL_ACCESS = "initial_access"
    EXECUTION = "execution"
    PERSISTENCE = "persistence"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DEFENSE_EVASION = "defense_evasion"
    CREDENTIAL_ACCESS = "credential_access"
    DISCOVERY = "discovery"
    LATERAL_MOVEMENT = "lateral_movement"
    COLLECTION = "collection"
    COMMAND_AND_CONTROL = "command_and_control"
    EXFILTRATION = "exfiltration"
    IMPACT = "impact"
    ISR_COLLECTION = "isr_collection"
    ELECTRONIC_ATTACK = "electronic_attack"
    ELECTRONIC_WARFARE = "electronic_warfare"
    KINETIC_MANEUVER = "kinetic_maneuver"
    KINETIC_PREPARATION = "kinetic_preparation"
    KINETIC_STRIKE = "kinetic_strike"
    LOGISTICS_STAGING = "logistics_staging"
    LOGISTICS_DISRUPTION = "logistics_disruption"

    @classmethod
    def from_value(cls, value: str | "TTPPhase") -> "TTPPhase":
        if isinstance(value, TTPPhase):
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("phase must be a non-empty string or TTPPhase")
        normalized = value.strip().lower()
        for phase in cls:
            if normalized == phase.value:
                return phase
        raise ValueError(f"Unsupported TTP phase: {value}")


ALL_TTP_PHASES: Tuple[TTPPhase, ...] = tuple(TTPPhase)


class SignatureType(str, Enum):
    """Behavioral signature families used for explainable matching."""

    TEMPORAL = "temporal"
    MOVEMENT = "movement"
    COMMUNICATION = "communication"
    TARGETING = "targeting"
    EVASION = "evasion"
    ESCALATION = "escalation"
    LOGISTICS = "logistics"
    FORMATION = "formation"

    @classmethod
    def from_value(cls, value: str | "SignatureType") -> "SignatureType":
        if isinstance(value, SignatureType):
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("signature_type must be a non-empty string or SignatureType")
        normalized = value.strip().lower()
        for sig_type in cls:
            if sig_type.value == normalized:
                return sig_type
        raise ValueError(f"Unsupported signature type: {value}")


class PlatformType(str, Enum):
    """Platform categories for tactical capability profiles."""

    FIXED_WING_UAV = "fixed_wing_uav"
    LOITERING_MUNITION = "loitering_munition"
    MULTIROTOR_UAV = "multirotor_uav"
    GROUND_VEHICLE = "ground_vehicle"
    MARITIME_SURFACE = "maritime_surface"

    @classmethod
    def from_value(cls, value: str | "PlatformType") -> "PlatformType":
        if isinstance(value, PlatformType):
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("platform_type must be a non-empty string or PlatformType")
        normalized = value.strip().lower()
        for platform_type in cls:
            if platform_type.value == normalized:
                return platform_type
        raise ValueError(f"Unsupported platform type: {value}")


@dataclass
class GenomeEvolutionEntry:
    """Single explainable mutation in a genome's evolution history."""

    change_type: str
    source_id: str = ""
    description: str = ""
    evidence_reference: str = ""
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    details: Dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        mapping = {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.change_type,
            "change_type": self.change_type,
            "details": self.details,
            "description": self.description,
            "source_id": self.source_id,
        }
        if key not in mapping:
            raise KeyError(key)
        return mapping[key]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "change_type": self.change_type,
            "source_id": self.source_id,
            "description": self.description,
            "evidence_reference": self.evidence_reference,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "details": dict(self.details),
        }


@dataclass
class TTP:
    """MITRE-aligned technique with Bayesian reinforcement and recency decay."""

    technique_id: str = ""
    name: str = ""
    phase: TTPPhase | str = TTPPhase.EXECUTION
    mitre_id: str = ""
    ttp_id: str = field(default_factory=lambda: f"ttp-{uuid4().hex[:8]}")
    confidence: float = 0.5
    observation_count: int = 0
    last_observed: Optional[datetime] = None
    half_life_days: float = 45.0
    provenance: List[str] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.technique_id, str):
            raise ValueError("technique_id must be a string")
        if not isinstance(self.mitre_id, str):
            raise ValueError("mitre_id must be a string")
        if not self.technique_id.strip():
            self.technique_id = self.mitre_id.strip()
        if not self.technique_id.strip():
            self.technique_id = f"AUTO-{uuid4().hex[:8]}".upper()
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        self.technique_id = self.technique_id.strip().upper()
        self.mitre_id = self.technique_id
        self.name = self.name.strip()
        self.phase = TTPPhase.from_value(self.phase)
        if not isinstance(self.ttp_id, str) or not self.ttp_id.strip():
            self.ttp_id = f"ttp-{uuid4().hex[:8]}"
        if not isinstance(self.confidence, (float, int)):
            raise ValueError("confidence must be numeric")
        self.confidence = _clamp01(float(self.confidence))
        if not isinstance(self.observation_count, int) or self.observation_count < 0:
            raise ValueError("observation_count must be a non-negative integer")
        if self.last_observed is not None and not isinstance(self.last_observed, datetime):
            raise ValueError("last_observed must be datetime or None")
        if self.last_observed is not None:
            self.last_observed = _ensure_utc(self.last_observed)
        if not isinstance(self.half_life_days, (float, int)) or self.half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        self.half_life_days = float(self.half_life_days)
        if not isinstance(self.provenance, list) or any(not isinstance(v, str) or not v.strip() for v in self.provenance):
            raise ValueError("provenance must be a list of non-empty strings")
        self.provenance = [v.strip() for v in self.provenance]
        if not isinstance(self.tags, (set, list, tuple)):
            raise ValueError("tags must be a set/list/tuple of strings")
        normalized_tags: Set[str] = set()
        for tag in self.tags:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("tags must contain non-empty strings")
            normalized_tags.add(_normalize_token(tag))
        self.tags = normalized_tags
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")

    def record_observation(
        self,
        *,
        observation_confidence: float = 0.7,
        likelihood_multiplier: float = 1.35,
        observed_at: Optional[datetime] = None,
        evidence_reference: Optional[str] = None,
    ) -> float:
        """Bayesian confidence update from a new observation."""
        if not isinstance(observation_confidence, (float, int)):
            raise ValueError("observation_confidence must be numeric")
        if not isinstance(likelihood_multiplier, (float, int)):
            raise ValueError("likelihood_multiplier must be numeric")
        observation_confidence = _clamp01(float(observation_confidence))
        likelihood_multiplier = float(likelihood_multiplier)
        if likelihood_multiplier <= 0:
            raise ValueError("likelihood_multiplier must be > 0")

        # Tactical Bayesian reinforcement: observations raise posterior odds.
        prior = min(max(self.confidence, 1e-6), 1.0 - 1e-6)
        prior_odds = prior / (1.0 - prior)
        likelihood_ratio = max(0.01, likelihood_multiplier * (0.5 + observation_confidence))
        posterior_odds = prior_odds * likelihood_ratio
        posterior = posterior_odds / (1.0 + posterior_odds)
        self.confidence = _clamp01(float(posterior))

        self.observation_count += 1
        self.last_observed = _ensure_utc(observed_at) if observed_at else _utcnow()
        if evidence_reference is not None:
            if not isinstance(evidence_reference, str) or not evidence_reference.strip():
                raise ValueError("evidence_reference must be a non-empty string when provided")
            self.provenance.append(evidence_reference.strip())
        return self.confidence

    def decay_confidence(
        self,
        *,
        as_of: Optional[datetime] = None,
        half_life_days: Optional[float] = None,
    ) -> float:
        """Apply recency half-life decay to keep stale intelligence conservative."""
        if self.last_observed is None:
            return self.confidence
        as_of_utc = _ensure_utc(as_of) if as_of else _utcnow()
        hl = float(half_life_days if half_life_days is not None else self.half_life_days)
        if hl <= 0:
            raise ValueError("half_life_days must be > 0")

        elapsed_days = max(0.0, (as_of_utc - self.last_observed).total_seconds() / 86400.0)
        factor = 0.5 ** (elapsed_days / hl)
        self.confidence = _clamp01(self.confidence * factor)
        return self.confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ttp_id": self.ttp_id,
            "technique_id": self.technique_id,
            "mitre_id": self.mitre_id,
            "name": self.name,
            "phase": self.phase.value,
            "confidence": self.confidence,
            "observation_count": self.observation_count,
            "last_observed": self.last_observed.isoformat() if self.last_observed else None,
            "half_life_days": self.half_life_days,
            "provenance": list(self.provenance),
            "tags": sorted(self.tags),
            "metadata": dict(self.metadata),
        }


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and isfinite(float(value))


def _to_set(value: Any) -> Set[str]:
    if isinstance(value, str):
        return {_normalize_token(value)}
    if isinstance(value, (set, list, tuple)):
        normalized: Set[str] = set()
        for item in value:
            if isinstance(item, str) and item.strip():
                normalized.add(_normalize_token(item))
        return normalized
    return set()


@dataclass
class BehavioralSignature:
    """Quantified actor behavior over time, movement, comms, and tactical effects."""

    signature_id: str = ""
    name: str = ""
    signature_type: SignatureType = SignatureType.TEMPORAL
    pattern_parameters: Dict[str, Any] = field(default_factory=dict)
    temporal_patterns: Dict[str, Any] = field(default_factory=dict)
    movement_patterns: Dict[str, Any] = field(default_factory=dict)
    communication_patterns: Dict[str, Any] = field(default_factory=dict)
    targeting_patterns: Dict[str, Any] = field(default_factory=dict)
    evasion_patterns: Dict[str, Any] = field(default_factory=dict)
    escalation_patterns: Dict[str, Any] = field(default_factory=dict)
    logistics_patterns: Dict[str, Any] = field(default_factory=dict)
    formation_patterns: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    specificity: float = 0.5
    provenance: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.signature_id, str):
            raise ValueError("signature_id must be a string")
        if not isinstance(self.name, str):
            raise ValueError("name must be a string")
        if not self.signature_id.strip():
            self.signature_id = f"sig-{uuid4().hex[:8]}"
        if not self.name.strip():
            self.name = self.signature_id
        self.signature_id = self.signature_id.strip()
        self.name = self.name.strip()
        self.signature_type = SignatureType.from_value(self.signature_type)
        if not isinstance(self.pattern_parameters, dict):
            raise ValueError("pattern_parameters must be a dictionary")
        for field_name in (
            "temporal_patterns",
            "movement_patterns",
            "communication_patterns",
            "targeting_patterns",
            "evasion_patterns",
            "escalation_patterns",
            "logistics_patterns",
            "formation_patterns",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, dict):
                raise ValueError(f"{field_name} must be a dictionary")
        if not isinstance(self.confidence, (float, int)):
            raise ValueError("confidence must be numeric")
        self.confidence = _clamp01(float(self.confidence))
        if not isinstance(self.provenance, list) or any(not isinstance(v, str) or not v.strip() for v in self.provenance):
            raise ValueError("provenance must be a list of non-empty strings")
        self.provenance = [p.strip() for p in self.provenance]
        self.created_at = _ensure_utc(self.created_at)
        self.updated_at = _ensure_utc(self.updated_at)

        # Backward compatibility path: fold generic pattern_parameters into
        # the family dictionary implied by signature_type so legacy and new
        # scoring code can both operate.
        if self.pattern_parameters:
            if self.signature_type == SignatureType.TEMPORAL:
                self.temporal_patterns.update(self.pattern_parameters)
            elif self.signature_type == SignatureType.MOVEMENT:
                self.movement_patterns.update(self.pattern_parameters)
            elif self.signature_type == SignatureType.COMMUNICATION:
                self.communication_patterns.update(self.pattern_parameters)
            elif self.signature_type == SignatureType.TARGETING:
                self.targeting_patterns.update(self.pattern_parameters)
            elif self.signature_type == SignatureType.EVASION:
                self.evasion_patterns.update(self.pattern_parameters)
            elif self.signature_type == SignatureType.ESCALATION:
                self.escalation_patterns.update(self.pattern_parameters)
            elif self.signature_type == SignatureType.LOGISTICS:
                self.logistics_patterns.update(self.pattern_parameters)
            elif self.signature_type == SignatureType.FORMATION:
                self.formation_patterns.update(self.pattern_parameters)

    def _iter_expected(self) -> Iterable[Tuple[str, str, Any]]:
        families = (
            ("temporal", self.temporal_patterns),
            ("movement", self.movement_patterns),
            ("communication", self.communication_patterns),
            ("targeting", self.targeting_patterns),
            ("evasion", self.evasion_patterns),
            ("escalation", self.escalation_patterns),
            ("logistics", self.logistics_patterns),
            ("formation", self.formation_patterns),
        )
        for family_name, family_values in families:
            for key, expected in family_values.items():
                yield family_name, key, expected

    def _specificity_weight(self, expected: Any) -> float:
        if isinstance(expected, bool):
            return 1.25
        if _is_numeric(expected):
            return 1.0 + 1.0 / (abs(float(expected)) + 1.0)
        if isinstance(expected, (tuple, list)) and len(expected) == 2 and _is_numeric(expected[0]) and _is_numeric(expected[1]):
            low = float(min(expected[0], expected[1]))
            high = float(max(expected[0], expected[1]))
            span = max(high - low, 1e-6)
            return 1.0 + 1.0 / (span + 1.0)
        if isinstance(expected, (set, list, tuple)):
            expected_set = _to_set(expected)
            return 1.0 + 1.0 / max(1, len(expected_set))
        if isinstance(expected, str):
            return 1.15
        return 1.0

    def _value_score(self, expected: Any, observed: Any) -> float:
        if observed is None:
            return 0.0
        if isinstance(expected, bool):
            if not isinstance(observed, bool):
                return 0.0
            return 1.0 if expected == observed else 0.0

        if isinstance(expected, (tuple, list)) and len(expected) == 2 and _is_numeric(expected[0]) and _is_numeric(expected[1]):
            if not _is_numeric(observed):
                return 0.0
            low = float(min(expected[0], expected[1]))
            high = float(max(expected[0], expected[1]))
            obs = float(observed)
            if low <= obs <= high:
                return 1.0
            # Outside expected operating envelope: score decays by normalized distance.
            span = max(high - low, 1.0)
            distance = low - obs if obs < low else obs - high
            return max(0.0, 1.0 - (distance / span))

        if _is_numeric(expected):
            if not _is_numeric(observed):
                return 0.0
            exp = float(expected)
            obs = float(observed)
            normalizer = max(1.0, abs(exp))
            return max(0.0, 1.0 - abs(exp - obs) / normalizer)

        if isinstance(expected, (set, list, tuple)):
            expected_set = _to_set(expected)
            observed_set = _to_set(observed)
            if not expected_set or not observed_set:
                return 0.0
            return _safe_jaccard(expected_set, observed_set)

        if isinstance(expected, str):
            return 1.0 if isinstance(observed, str) and _normalize_token(observed) == _normalize_token(expected) else 0.0
        return 0.0

    def match_score(self, observed_params: Mapping[str, Any]) -> float:
        """Score observed behavior using range/boolean/proximity/set matching."""
        if not isinstance(observed_params, Mapping):
            raise ValueError("observed_params must be a mapping")

        total_weight = 0.0
        weighted_score = 0.0
        matched_signals = 0
        total_signals = 0

        for family_name, key, expected in self._iter_expected():
            total_signals += 1
            family_observed = observed_params.get(family_name, {})
            if isinstance(family_observed, Mapping) and key in family_observed:
                observed_value = family_observed[key]
            else:
                observed_value = observed_params.get(key)

            score = self._value_score(expected, observed_value)
            weight = self._specificity_weight(expected)
            weighted_score += score * weight
            total_weight += weight
            if observed_value is not None:
                matched_signals += 1

        if total_signals == 0 or total_weight <= 0:
            return 0.0

        base_match = weighted_score / total_weight
        coverage = matched_signals / total_signals
        confidence_weight = 0.5 + 0.5 * self.confidence
        return _clamp01(base_match * (0.6 + 0.4 * coverage) * confidence_weight)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature_id": self.signature_id,
            "name": self.name,
            "signature_type": self.signature_type.value,
            "pattern_parameters": dict(self.pattern_parameters),
            "confidence": self.confidence,
            "specificity": self.specificity,
            "provenance": list(self.provenance),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "temporal_patterns": dict(self.temporal_patterns),
            "movement_patterns": dict(self.movement_patterns),
            "communication_patterns": dict(self.communication_patterns),
            "targeting_patterns": dict(self.targeting_patterns),
            "evasion_patterns": dict(self.evasion_patterns),
            "escalation_patterns": dict(self.escalation_patterns),
            "logistics_patterns": dict(self.logistics_patterns),
            "formation_patterns": dict(self.formation_patterns),
        }


def _validate_evidence_mapping(mapping: Dict[str, List[str]], field_name: str) -> Dict[str, List[str]]:
    if not isinstance(mapping, dict):
        raise ValueError(f"{field_name} must be a dictionary")
    normalized: Dict[str, List[str]] = {}
    for key, refs in mapping.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(refs, list) or not refs:
            raise ValueError(f"{field_name} entry '{key}' must include evidence references")
        clean_refs: List[str] = []
        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError(f"{field_name} entry '{key}' contains an invalid evidence reference")
            clean_refs.append(ref.strip())
        normalized[key.strip()] = clean_refs
    return normalized


@dataclass
class CapabilityProfile:
    """Assessed capabilities with strict evidence provenance per entry."""

    platforms: Dict[str, List[str]] = field(default_factory=dict)
    weapons: Dict[str, List[str]] = field(default_factory=dict)
    cyber_capabilities: Dict[str, List[str]] = field(default_factory=dict)
    ew_capabilities: Dict[str, List[str]] = field(default_factory=dict)
    swarm_parameters: Dict[str, List[str]] = field(default_factory=dict)
    logistics_capabilities: Dict[str, List[str]] = field(default_factory=dict)
    confidence: float = 0.5
    max_range_km: float = 0.0
    provenance: List[str] = field(default_factory=list)
    assessment_basis: List[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if isinstance(self.platforms, list):
            platform_map: Dict[str, List[str]] = {}
            for p in self.platforms:
                if isinstance(p, PlatformType):
                    key = p.value
                else:
                    key = _normalize_token(str(p))
                if key:
                    platform_map[key] = ["auto-import"]
            self.platforms = platform_map
        self.platforms = _validate_evidence_mapping(self.platforms, "platforms")
        self.weapons = _validate_evidence_mapping(self.weapons, "weapons")
        if isinstance(self.cyber_capabilities, list):
            self.cyber_capabilities = {str(c): ["auto-import"] for c in self.cyber_capabilities}
        self.cyber_capabilities = _validate_evidence_mapping(self.cyber_capabilities, "cyber_capabilities")
        self.ew_capabilities = _validate_evidence_mapping(self.ew_capabilities, "ew_capabilities")
        self.swarm_parameters = _validate_evidence_mapping(self.swarm_parameters, "swarm_parameters")
        self.logistics_capabilities = _validate_evidence_mapping(self.logistics_capabilities, "logistics_capabilities")
        if not isinstance(self.confidence, (float, int)):
            raise ValueError("confidence must be numeric")
        self.confidence = _clamp01(float(self.confidence))
        if not isinstance(self.max_range_km, (float, int)):
            raise ValueError("max_range_km must be numeric")
        self.max_range_km = float(self.max_range_km)
        if not isinstance(self.provenance, list) or any(not isinstance(v, str) or not v.strip() for v in self.provenance):
            raise ValueError("provenance must be a list of non-empty strings")
        self.provenance = [p.strip() for p in self.provenance]
        if not isinstance(self.assessment_basis, list):
            raise ValueError("assessment_basis must be a list of strings")
        self.assessment_basis = [str(v).strip() for v in self.assessment_basis if str(v).strip()]
        self.updated_at = _ensure_utc(self.updated_at)

    def _domain_map(self) -> Dict[str, Dict[str, List[str]]]:
        return {
            "platforms": self.platforms,
            "weapons": self.weapons,
            "cyber": self.cyber_capabilities,
            "ew": self.ew_capabilities,
            "swarm": self.swarm_parameters,
            "logistics": self.logistics_capabilities,
        }

    def add_entry(self, *, domain: str, item: str, evidence_references: Sequence[str]) -> None:
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError("domain must be a non-empty string")
        if not isinstance(item, str) or not item.strip():
            raise ValueError("item must be a non-empty string")
        if not isinstance(evidence_references, Sequence) or isinstance(evidence_references, (str, bytes)):
            raise ValueError("evidence_references must be a sequence of strings")
        refs = []
        for ref in evidence_references:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("evidence_references must contain non-empty strings")
            refs.append(ref.strip())
        if not refs:
            raise ValueError("at least one evidence reference is required")

        domains = self._domain_map()
        normalized_domain = _normalize_token(domain)
        if normalized_domain not in domains:
            raise ValueError(f"Unsupported capability domain: {domain}")
        domain_mapping = domains[normalized_domain]
        if item not in domain_mapping:
            domain_mapping[item] = []
        for ref in refs:
            if ref not in domain_mapping[item]:
                domain_mapping[item].append(ref)
        self.updated_at = _utcnow()

    def all_items(self) -> Set[str]:
        items: Set[str] = set()
        for domain, mapping in self._domain_map().items():
            for item in mapping:
                items.add(f"{domain}:{_normalize_token(item)}")
        return items

    def domain_coverage(self) -> float:
        domains = self._domain_map()
        populated = sum(1 for mapping in domains.values() if mapping)
        return populated / len(domains)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platforms": dict(self.platforms),
            "weapons": dict(self.weapons),
            "cyber_capabilities": dict(self.cyber_capabilities),
            "ew_capabilities": dict(self.ew_capabilities),
            "swarm_parameters": dict(self.swarm_parameters),
            "logistics_capabilities": dict(self.logistics_capabilities),
            "confidence": self.confidence,
            "max_range_km": self.max_range_km,
            "provenance": list(self.provenance),
            "assessment_basis": list(self.assessment_basis),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class ChainLink:
    """Single observable in a temporal indicator sequence."""

    observable_type: str
    observable_value: Any
    min_time_delta_s: float = 0.0
    max_time_delta_s: float = 300.0
    confidence_weight: float = 1.0
    provenance: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.observable_type, str) or not self.observable_type.strip():
            raise ValueError("observable_type must be a non-empty string")
        self.observable_type = _normalize_token(self.observable_type)
        if not isinstance(self.min_time_delta_s, (float, int)) or self.min_time_delta_s < 0:
            raise ValueError("min_time_delta_s must be a non-negative number")
        if not isinstance(self.max_time_delta_s, (float, int)) or self.max_time_delta_s < 0:
            raise ValueError("max_time_delta_s must be a non-negative number")
        self.min_time_delta_s = float(self.min_time_delta_s)
        self.max_time_delta_s = float(self.max_time_delta_s)
        if self.max_time_delta_s < self.min_time_delta_s:
            raise ValueError("max_time_delta_s must be >= min_time_delta_s")
        if not isinstance(self.confidence_weight, (float, int)) or self.confidence_weight <= 0:
            raise ValueError("confidence_weight must be > 0")
        self.confidence_weight = float(self.confidence_weight)
        if not isinstance(self.provenance, list) or any(not isinstance(v, str) or not v.strip() for v in self.provenance):
            raise ValueError("provenance must be a list of non-empty strings")
        self.provenance = [p.strip() for p in self.provenance]

    def _value_similarity(self, observed_value: Any) -> float:
        expected = self.observable_value
        if isinstance(expected, bool):
            if not isinstance(observed_value, bool):
                return 0.0
            return 1.0 if expected == observed_value else 0.0
        if _is_numeric(expected):
            if not _is_numeric(observed_value):
                return 0.0
            exp = float(expected)
            obs = float(observed_value)
            return max(0.0, 1.0 - abs(exp - obs) / max(1.0, abs(exp)))
        if isinstance(expected, (set, list, tuple)):
            expected_set = _to_set(expected)
            observed_set = _to_set(observed_value)
            if not expected_set or not observed_set:
                return 0.0
            return _safe_jaccard(expected_set, observed_set)
        if isinstance(expected, str):
            return 1.0 if isinstance(observed_value, str) and _normalize_token(observed_value) == _normalize_token(expected) else 0.0
        return 0.0

    def match(self, observation: Mapping[str, Any]) -> float:
        if not isinstance(observation, Mapping):
            return 0.0
        obs_type = observation.get("type")
        if not isinstance(obs_type, str) or _normalize_token(obs_type) != self.observable_type:
            return 0.0
        return self._value_similarity(observation.get("value"))


@dataclass
class IndicatorChain:
    """Temporal sequence fingerprint used for defensive attribution."""

    chain_id: str
    name: str
    links: List[ChainLink] = field(default_factory=list)
    confidence: float = 0.5
    provenance: List[str] = field(default_factory=list)
    last_matched: Optional[datetime] = None
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.chain_id, str) or not self.chain_id.strip():
            raise ValueError("chain_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        self.chain_id = self.chain_id.strip()
        self.name = self.name.strip()
        if not isinstance(self.links, list) or any(not isinstance(link, ChainLink) for link in self.links):
            raise ValueError("links must be a list of ChainLink objects")
        if not isinstance(self.confidence, (float, int)):
            raise ValueError("confidence must be numeric")
        self.confidence = _clamp01(float(self.confidence))
        if not isinstance(self.provenance, list) or any(not isinstance(v, str) or not v.strip() for v in self.provenance):
            raise ValueError("provenance must be a list of non-empty strings")
        self.provenance = [p.strip() for p in self.provenance]
        if self.last_matched is not None:
            self.last_matched = _ensure_utc(self.last_matched)
        self.updated_at = _ensure_utc(self.updated_at)

    def add_link(self, link: ChainLink) -> None:
        if not isinstance(link, ChainLink):
            raise ValueError("link must be a ChainLink instance")
        self.links.append(link)
        self.updated_at = _utcnow()

    def _normalize_observations(self, observations: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for obs in observations:
            if not isinstance(obs, Mapping):
                continue
            obs_type = obs.get("type")
            if not isinstance(obs_type, str) or not obs_type.strip():
                continue
            timestamp_raw = obs.get("timestamp")
            timestamp: Optional[datetime] = None
            if isinstance(timestamp_raw, datetime):
                timestamp = _ensure_utc(timestamp_raw)
            normalized.append(
                {
                    "type": _normalize_token(obs_type),
                    "value": obs.get("value"),
                    "timestamp": timestamp,
                }
            )
        if any(entry["timestamp"] is not None for entry in normalized):
            normalized.sort(
                key=lambda item: item["timestamp"] if item["timestamp"] is not None else datetime.max.replace(tzinfo=timezone.utc)
            )
        return normalized

    def match_observations(self, observations: Sequence[Mapping[str, Any]]) -> float:
        """Score sequential matching with temporal tolerance and link confidence."""
        if not isinstance(observations, Sequence):
            raise ValueError("observations must be a sequence")
        if not self.links:
            return 0.0

        normalized = self._normalize_observations(observations)
        if not normalized:
            return 0.0

        total_weight = sum(link.confidence_weight for link in self.links)
        if total_weight <= 0:
            return 0.0

        best_score = 0.0
        first_link = self.links[0]

        for start_idx, start_obs in enumerate(normalized):
            first_score = first_link.match(start_obs)
            if first_score <= 0.0:
                continue
            cumulative = first_score * first_link.confidence_weight
            matched_links = 1
            prev_idx = start_idx
            prev_ts = start_obs.get("timestamp")

            for link in self.links[1:]:
                best_next_idx = -1
                best_next_score = 0.0
                best_next_ts: Optional[datetime] = None

                for idx in range(prev_idx + 1, len(normalized)):
                    candidate = normalized[idx]
                    candidate_score = link.match(candidate)
                    if candidate_score <= 0.0:
                        continue

                    candidate_ts = candidate.get("timestamp")
                    if prev_ts is not None and candidate_ts is not None:
                        delta = (candidate_ts - prev_ts).total_seconds()
                        if delta < link.min_time_delta_s or delta > link.max_time_delta_s:
                            continue

                    if candidate_score > best_next_score:
                        best_next_idx = idx
                        best_next_score = candidate_score
                        best_next_ts = candidate_ts

                if best_next_idx < 0:
                    break

                cumulative += best_next_score * link.confidence_weight
                matched_links += 1
                prev_idx = best_next_idx
                prev_ts = best_next_ts

            normalized_score = cumulative / total_weight
            continuity = matched_links / len(self.links)
            combined = normalized_score * (0.5 + 0.5 * continuity)
            if combined > best_score:
                best_score = combined

        final_score = _clamp01(best_score * (0.6 + 0.4 * self.confidence))
        if final_score > 0:
            self.last_matched = _utcnow()
        return final_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "name": self.name,
            "confidence": self.confidence,
            "provenance": list(self.provenance),
            "last_matched": self.last_matched.isoformat() if self.last_matched else None,
            "updated_at": self.updated_at.isoformat(),
            "links": [
                {
                    "observable_type": link.observable_type,
                    "observable_value": link.observable_value,
                    "min_time_delta_s": link.min_time_delta_s,
                    "max_time_delta_s": link.max_time_delta_s,
                    "confidence_weight": link.confidence_weight,
                    "provenance": list(link.provenance),
                }
                for link in self.links
            ],
        }


@dataclass
class ThreatGenome:
    """Complete, evolving behavioral fingerprint for a threat actor."""

    actor_id: str = ""
    actor_name: str = ""
    actor_type: str = "unknown"
    actor_aliases: List[str] = field(default_factory=list)
    threat_rating: str = "unknown"
    confidence: float = 0.5
    observation_count: int = 0
    regions_of_activity: List[str] = field(default_factory=list)
    regions: Set[str] = field(default_factory=set)
    tags: Set[str] = field(default_factory=set)
    ttps: Dict[str, TTP] = field(default_factory=dict)
    signatures: Dict[str, BehavioralSignature] = field(default_factory=dict)
    capabilities: Optional[CapabilityProfile] = None
    indicator_chains: Dict[str, IndicatorChain] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    last_activity: datetime = field(default_factory=_utcnow)
    evolution_log: List[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.actor_id, str):
            raise ValueError("actor_id must be a string")
        if not self.actor_id.strip():
            self.actor_id = f"gen-{uuid4().hex[:10]}"
        if not isinstance(self.actor_name, str):
            raise ValueError("actor_name must be a string")
        if not self.actor_name.strip():
            self.actor_name = self.actor_id
        if not isinstance(self.actor_type, str) or not self.actor_type.strip():
            raise ValueError("actor_type must be a non-empty string")
        if not isinstance(self.actor_aliases, list):
            raise ValueError("actor_aliases must be a list")
        self.actor_aliases = [str(a).strip() for a in self.actor_aliases if str(a).strip()]
        if not isinstance(self.threat_rating, str):
            raise ValueError("threat_rating must be a string")
        self.threat_rating = self.threat_rating.strip().lower() if self.threat_rating else "unknown"
        if not isinstance(self.confidence, (float, int)):
            raise ValueError("confidence must be numeric")
        self.confidence = _clamp01(float(self.confidence))
        if not isinstance(self.observation_count, int) or self.observation_count < 0:
            raise ValueError("observation_count must be a non-negative integer")
        self.actor_id = self.actor_id.strip()
        self.actor_name = self.actor_name.strip()
        self.actor_type = _normalize_token(self.actor_type)

        if not isinstance(self.regions_of_activity, list):
            raise ValueError("regions_of_activity must be a list of strings")
        if not isinstance(self.regions, (set, list, tuple)):
            raise ValueError("regions must be a set/list/tuple of strings")
        merged_regions = set(self.regions)
        for region in self.regions_of_activity:
            if isinstance(region, str) and region.strip():
                merged_regions.add(region)
        self.regions = {
            _normalize_token(region)
            for region in merged_regions
            if isinstance(region, str) and region.strip()
        }
        self.regions_of_activity = list(self.regions_of_activity)
        if not isinstance(self.tags, (set, list, tuple)):
            raise ValueError("tags must be a set/list/tuple of strings")
        self.tags = {_normalize_token(tag) for tag in self.tags if isinstance(tag, str) and tag.strip()}
        if any(not isinstance(v, TTP) for v in self.ttps.values()):
            raise ValueError("ttps must contain TTP values")
        if any(not isinstance(v, BehavioralSignature) for v in self.signatures.values()):
            raise ValueError("signatures must contain BehavioralSignature values")
        if self.capabilities is not None and not isinstance(self.capabilities, CapabilityProfile):
            raise ValueError("capabilities must be CapabilityProfile or None")
        if any(not isinstance(v, IndicatorChain) for v in self.indicator_chains.values()):
            raise ValueError("indicator_chains must contain IndicatorChain values")
        self.created_at = _ensure_utc(self.created_at)
        self.updated_at = _ensure_utc(self.updated_at)
        self.last_activity = _ensure_utc(self.last_activity)
        if not isinstance(self.evolution_log, list):
            raise ValueError("evolution_log must be a list")
        normalized_log: List[GenomeEvolutionEntry] = []
        for entry in self.evolution_log:
            if isinstance(entry, GenomeEvolutionEntry):
                normalized_log.append(entry)
            elif isinstance(entry, dict):
                normalized_log.append(
                    GenomeEvolutionEntry(
                        change_type=str(entry.get("action") or entry.get("change_type") or "mutation"),
                        source_id=str(entry.get("source_id", "")),
                        description=str(entry.get("description", "")),
                        details=dict(entry.get("details", {})) if isinstance(entry.get("details", {}), dict) else {},
                    )
                )
            else:
                normalized_log.append(GenomeEvolutionEntry(change_type="mutation", description=str(entry)))
        self.evolution_log = normalized_log
        self.regions_of_activity = list(self.regions)

    # ------------------------------------------------------------------
    # Observation absorption (Chunk 2 — genome evolution)
    # ------------------------------------------------------------------

    @property
    def genome_id(self) -> str:
        return self.actor_id

    @property
    def first_observed(self) -> datetime:
        return self.created_at

    @first_observed.setter
    def first_observed(self, value: datetime) -> None:
        self.created_at = _ensure_utc(value)

    @property
    def last_updated(self) -> datetime:
        return self.updated_at

    @last_updated.setter
    def last_updated(self, value: datetime) -> None:
        self.updated_at = _ensure_utc(value)
        self.last_activity = self.updated_at

    def _log_evolution(
        self,
        change_type: str,
        source_id: str,
        description: str,
        evidence_reference: str,
        confidence_before: float,
        confidence_after: float,
    ) -> None:
        self.evolution_log.append(
            GenomeEvolutionEntry(
                change_type=change_type,
                source_id=source_id,
                description=description,
                evidence_reference=evidence_reference,
                confidence_before=float(confidence_before),
                confidence_after=float(confidence_after),
            )
        )

    def absorb_observation(self, obs_features: Dict[str, Any],
                           observation_id: str = "") -> List[str]:
        """Absorb extracted features from a correlated observation.

        Called by the correlator when an observation matches this genome.
        Updates TTPs, signatures, tags, regions, and confidence.
        """
        touched: List[str] = []

        # --- TTP hints ---
        for hint in obs_features.get("ttp_hints", []):
            if not isinstance(hint, dict):
                continue
            mitre_id = str(hint.get("mitre_id", "") or "")
            name = str(hint.get("name", "") or "")
            phase_str = str(hint.get("phase", "execution") or "execution")
            conf = float(hint.get("confidence", 0.5))
            try:
                phase = TTPPhase(phase_str)
            except ValueError:
                phase = TTPPhase.EXECUTION
            ttp = TTP(mitre_id=mitre_id, name=name, phase=phase, confidence=conf)
            self.add_ttp(ttp)
            touched.append(ttp.ttp_id)

        # --- Signature parameters ---
        sig_params = obs_features.get("signature_params", {})
        if isinstance(sig_params, dict) and sig_params:
            sig_copy = dict(sig_params)
            sig_type_str = str(sig_copy.pop("signature_type", "temporal") or "temporal")
            try:
                sig_type = SignatureType(sig_type_str)
            except ValueError:
                sig_type = SignatureType.TEMPORAL
            sig = BehavioralSignature(
                signature_type=sig_type,
                name=f"auto_{sig_type.value}_{observation_id[:8]}",
                pattern_parameters=sig_copy,
                confidence=float(obs_features.get("raw_confidence", 0.5)),
                specificity=0.4,
            )
            self.add_signature(sig)
            touched.append(sig.signature_id)

        # --- Comms features -> communication signature ---
        comms = obs_features.get("comms_features", {})
        if isinstance(comms, dict) and comms:
            sig = BehavioralSignature(
                signature_type=SignatureType.COMMUNICATION,
                name=f"comms_{observation_id[:8]}",
                pattern_parameters=dict(comms),
                confidence=float(obs_features.get("raw_confidence", 0.5)),
                specificity=0.5,
            )
            self.add_signature(sig)
            touched.append(sig.signature_id)

        # --- Cyber features -> capabilities ---
        cyber = obs_features.get("cyber_features", {})
        if isinstance(cyber, dict) and cyber:
            caps_list = cyber.get("capabilities", [])
            if caps_list and isinstance(caps_list, list):
                if self.capabilities is None:
                    self.set_capabilities(CapabilityProfile(
                        cyber_capabilities={str(c): [observation_id or "auto-import"] for c in caps_list},
                        confidence=float(obs_features.get("raw_confidence", 0.5)),
                        assessment_basis=[observation_id],
                    ))
                else:
                    for cap in caps_list:
                        if str(cap) not in self.capabilities.cyber_capabilities:
                            self.capabilities.cyber_capabilities[str(cap)] = [observation_id or "auto-import"]
                    self.capabilities.assessment_basis.append(observation_id)
                touched.append("cap")

        # --- Tags ---
        new_tags = set(str(t).lower() for t in obs_features.get("behavior_tags", []))
        self.tags.update(new_tags)

        # --- Regions ---
        for r in obs_features.get("regions", []):
            if r:
                self.regions.add(_normalize_token(str(r)))

        # --- Threat level ---
        threat_hint = obs_features.get("threat_level")
        if threat_hint and str(threat_hint) != self.threat_rating:
            self.threat_rating = str(threat_hint)

        # --- Confidence update (Bayesian blend) ---
        raw_conf = float(obs_features.get("raw_confidence", 0.5))
        old_conf = self.confidence
        self.confidence = 1.0 - (1.0 - self.confidence) * (1.0 - raw_conf * 0.3)
        self.confidence = min(0.98, self.confidence)

        self._log_evolution(
            "observation_absorbed", observation_id,
            f"Absorbed obs {observation_id}: {len(touched)} components",
            observation_id, old_conf, self.confidence,
        )
        self._touch()
        return touched

    def merge_from(self, other: "ThreatGenome", merge_reason: str = "") -> List[str]:
        """Absorb all components from another genome into this one.

        Used when two genomes are discovered to be the same actor.
        Preserves aliases, regions, tags, evolution history.
        Returns list of component IDs absorbed.
        """
        absorbed: List[str] = []

        # Aliases
        if other.actor_name and other.actor_name != self.actor_name:
            if other.actor_name not in self.actor_aliases:
                self.actor_aliases.append(other.actor_name)
        for alias in other.actor_aliases:
            if alias not in self.actor_aliases and alias != self.actor_name:
                self.actor_aliases.append(alias)

        # TTPs
        for ttp in other.ttps.values():
            self.add_ttp(ttp)
            absorbed.append(ttp.ttp_id)

        # Signatures
        for sig in other.signatures.values():
            if sig.signature_id not in self.signatures:
                self.add_signature(sig)
                absorbed.append(sig.signature_id)

        # Capabilities
        if other.capabilities:
            if self.capabilities is None:
                self.set_capabilities(other.capabilities)
            else:
                for p in other.capabilities.platforms:
                    if p not in self.capabilities.platforms:
                        self.capabilities.platforms[p] = list(other.capabilities.platforms[p])
                for c in other.capabilities.cyber_capabilities:
                    if c not in self.capabilities.cyber_capabilities:
                        self.capabilities.cyber_capabilities[c] = list(other.capabilities.cyber_capabilities[c])

        # Indicator chains
        for chain in other.indicator_chains.values():
            if chain.chain_id not in self.indicator_chains:
                self.add_indicator_chain(chain)
                absorbed.append(chain.chain_id)

        # Regions, tags
        self.regions.update(other.regions)
        self.regions_of_activity = list(self.regions_of_activity)
        self.tags.update(other.tags)

        # Evolution history
        self.evolution_log.extend(other.evolution_log)

        # Timestamps
        if other.first_observed < self.first_observed:
            self.first_observed = other.first_observed
        self.observation_count += other.observation_count

        # Confidence boost from merge corroboration
        self.confidence = min(0.98, max(self.confidence, other.confidence) + 0.03)

        self._log_evolution(
            "genome_merged", other.genome_id,
            f"Merged '{other.actor_name}': {len(absorbed)} components. {merge_reason}",
            f"merge-{other.genome_id}", other.confidence, self.confidence,
        )
        self._touch()
        return absorbed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _touch(self, activity_time: Optional[datetime] = None) -> None:
        now = _ensure_utc(activity_time) if activity_time else _utcnow()
        self.updated_at = now
        self.last_activity = now
        self.observation_count += 1

    def _log_mutation(self, action: str, details: Dict[str, Any]) -> None:
        self.evolution_log.append(
            GenomeEvolutionEntry(
                change_type=action,
                description=action,
                details=dict(details),
            )
        )

    def add_ttp(self, ttp: TTP) -> None:
        if not isinstance(ttp, TTP):
            raise ValueError("ttp must be a TTP instance")
        action = "add_ttp" if ttp.technique_id not in self.ttps else "update_ttp"
        self.ttps[ttp.technique_id] = ttp
        self._touch(ttp.last_observed)
        self._log_mutation(
            action,
            {
                "technique_id": ttp.technique_id,
                "phase": ttp.phase.value,
                "confidence": ttp.confidence,
                "provenance_count": len(ttp.provenance),
            },
        )

    def add_signature(self, signature: BehavioralSignature) -> None:
        if not isinstance(signature, BehavioralSignature):
            raise ValueError("signature must be a BehavioralSignature instance")
        action = "add_signature" if signature.signature_id not in self.signatures else "update_signature"
        self.signatures[signature.signature_id] = signature
        self._touch(signature.updated_at)
        self._log_mutation(
            action,
            {
                "signature_id": signature.signature_id,
                "confidence": signature.confidence,
                "provenance_count": len(signature.provenance),
            },
        )

    def set_capabilities(self, capabilities: CapabilityProfile) -> None:
        if not isinstance(capabilities, CapabilityProfile):
            raise ValueError("capabilities must be a CapabilityProfile instance")
        self.capabilities = capabilities
        self._touch(capabilities.updated_at)
        self._log_mutation(
            "set_capabilities",
            {
                "item_count": len(capabilities.all_items()),
                "domain_coverage": capabilities.domain_coverage(),
                "confidence": capabilities.confidence,
            },
        )

    def add_indicator_chain(self, chain: IndicatorChain) -> None:
        if not isinstance(chain, IndicatorChain):
            raise ValueError("chain must be an IndicatorChain instance")
        action = "add_indicator_chain" if chain.chain_id not in self.indicator_chains else "update_indicator_chain"
        self.indicator_chains[chain.chain_id] = chain
        self._touch(chain.updated_at)
        self._log_mutation(
            action,
            {
                "chain_id": chain.chain_id,
                "link_count": len(chain.links),
                "confidence": chain.confidence,
            },
        )

    def _ttp_similarity(self, other: "ThreatGenome") -> float:
        left = self.ttps
        right = other.ttps
        keys = set(left) | set(right)
        if not keys:
            return 1.0
        numerator = 0.0
        denominator = 0.0
        for key in keys:
            l = left[key].confidence if key in left else 0.0
            r = right[key].confidence if key in right else 0.0
            numerator += min(l, r)
            denominator += max(l, r)
        if denominator <= 0:
            return 0.0
        return numerator / denominator

    def similarity(self, other_genome: "ThreatGenome") -> float:
        """Weighted Jaccard similarity (TTPs/signatures/capabilities/regions)."""
        if not isinstance(other_genome, ThreatGenome):
            raise ValueError("other_genome must be ThreatGenome")
        if self.actor_id == other_genome.actor_id:
            return 1.0

        ttp_score = self._ttp_similarity(other_genome)
        signature_score = _safe_jaccard(set(self.signatures), set(other_genome.signatures))
        left_caps = self.capabilities.all_items() if self.capabilities else set()
        right_caps = other_genome.capabilities.all_items() if other_genome.capabilities else set()
        capability_score = _safe_jaccard(left_caps, right_caps)
        region_score = _safe_jaccard(self.regions, other_genome.regions)
        return _clamp01(
            0.40 * ttp_score
            + 0.25 * signature_score
            + 0.20 * capability_score
            + 0.15 * region_score
        )

    def compute_completeness(self) -> float:
        """Estimate profile completeness for defensive planning confidence."""
        ttp_count_score = min(1.0, len(self.ttps) / 8.0)
        phase_coverage_score = len({ttp.phase for ttp in self.ttps.values()}) / len(ALL_TTP_PHASES) if self.ttps else 0.0
        signature_score = min(1.0, len(self.signatures) / 4.0)
        capability_score = 0.0
        if self.capabilities is not None:
            capability_score = self.capabilities.domain_coverage() * (0.5 + 0.5 * self.capabilities.confidence)
        chain_score = min(1.0, len(self.indicator_chains) / 3.0)
        return _clamp01(
            0.30 * ttp_count_score
            + 0.15 * phase_coverage_score
            + 0.20 * signature_score
            + 0.20 * capability_score
            + 0.15 * chain_score
        )

    def decay_confidence(
        self,
        *,
        half_life_days: float = 60.0,
        as_of: Optional[datetime] = None,
    ) -> Dict[str, float]:
        """Exponential decay for stale profiles to avoid over-confident attribution."""
        if not isinstance(half_life_days, (float, int)) or half_life_days <= 0:
            raise ValueError("half_life_days must be > 0")
        as_of_utc = _ensure_utc(as_of) if as_of else _utcnow()

        ttp_total = 0.0
        for ttp in self.ttps.values():
            ttp_total += ttp.decay_confidence(as_of=as_of_utc, half_life_days=float(half_life_days))
        ttp_avg = ttp_total / len(self.ttps) if self.ttps else 0.0

        def _decay_timestamped(value: float, timestamp: datetime) -> float:
            age_days = max(0.0, (as_of_utc - timestamp).total_seconds() / 86400.0)
            factor = 0.5 ** (age_days / float(half_life_days))
            return _clamp01(value * factor)

        signature_total = 0.0
        for signature in self.signatures.values():
            signature.confidence = _decay_timestamped(signature.confidence, signature.updated_at)
            signature_total += signature.confidence
        signature_avg = signature_total / len(self.signatures) if self.signatures else 0.0

        chain_total = 0.0
        for chain in self.indicator_chains.values():
            anchor = chain.last_matched if chain.last_matched else chain.updated_at
            chain.confidence = _decay_timestamped(chain.confidence, anchor)
            chain_total += chain.confidence
        chain_avg = chain_total / len(self.indicator_chains) if self.indicator_chains else 0.0

        capabilities_confidence = 0.0
        if self.capabilities is not None:
            self.capabilities.confidence = _decay_timestamped(self.capabilities.confidence, self.capabilities.updated_at)
            capabilities_confidence = self.capabilities.confidence

        self._touch(as_of_utc)
        summary = {
            "ttp_average_confidence": ttp_avg,
            "signature_average_confidence": signature_avg,
            "chain_average_confidence": chain_avg,
            "capabilities_confidence": capabilities_confidence,
        }
        self._log_mutation("decay_confidence", summary)
        return summary

    def get_phase_coverage(self) -> Dict[str, float]:
        """Confidence-weighted coverage across the extended threat kill-chain."""
        coverage = {phase.value: 0.0 for phase in ALL_TTP_PHASES}
        for ttp in self.ttps.values():
            phase_name = ttp.phase.value
            # Union-style confidence accumulation preserves diminishing returns.
            prior = coverage[phase_name]
            coverage[phase_name] = 1.0 - (1.0 - prior) * (1.0 - ttp.confidence)
        return coverage

    def get_uncovered_phases(self, *, threshold: float = 0.2) -> List[str]:
        if not isinstance(threshold, (float, int)):
            raise ValueError("threshold must be numeric")
        threshold = _clamp01(float(threshold))
        coverage = self.get_phase_coverage()
        return sorted([phase for phase, score in coverage.items() if score < threshold])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "actor_type": self.actor_type,
            "actor_aliases": list(self.actor_aliases),
            "threat_rating": self.threat_rating,
            "confidence": self.confidence,
            "observation_count": self.observation_count,
            "regions": sorted(self.regions),
            "tags": sorted(self.tags),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "ttps": {k: v.to_dict() for k, v in self.ttps.items()},
            "signatures": {k: v.to_dict() for k, v in self.signatures.items()},
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
            "indicator_chains": {k: v.to_dict() for k, v in self.indicator_chains.items()},
            "completeness": self.compute_completeness(),
            "phase_coverage": self.get_phase_coverage(),
            "evolution_log": [e.to_dict() if hasattr(e, "to_dict") else e for e in self.evolution_log],
        }

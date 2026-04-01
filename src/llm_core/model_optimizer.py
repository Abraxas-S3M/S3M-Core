"""
S3M Model Optimizer v1.0
Intelligent resource allocation and preload planning.

This module computes tactical engine allocation under strict VRAM budgets.
It is designed for offline edge deployments where each loaded model changes
mission readiness, latency posture, and failure tolerance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence

from .engine_registry import EngineID, EngineRegistry, TaskDomain


logger = logging.getLogger("s3m.optimizer")


class LoadCategory(Enum):
    """Engine load strategy."""

    ALWAYS_LOADED = "always_loaded"
    OPPORTUNISTIC = "opportunistic"
    UNLOAD_FIRST = "unload_first"
    NEVER_LOADED = "never_loaded"


class HardwareProfile(Enum):
    """Hardware constraint profiles."""

    EDGE_16GB = "edge_16gb"
    EDGE_32GB = "edge_32gb"
    EDGE_64GB = "edge_64gb"
    SERVER_128GB = "server_128gb"


class RuntimeProfile(Enum):
    """Runtime configuration profiles."""

    EDGE_MINIMAL = "edge_minimal"
    EDGE_DUAL = "edge_dual"
    EDGE_TRIPLE = "edge_triple"
    SERVER_FULL = "server_full"


HARDWARE_PROFILES: Dict[str, Dict[str, object]] = {
    HardwareProfile.EDGE_16GB.value: {
        "name": "Edge Device (16GB VRAM)",
        "available_gb": 16.0,
        "recommended_engines": 1,
        "consensus_available": False,
        "tier": "minimal",
        "use_cases": ["tactical_only", "single_engine"],
    },
    HardwareProfile.EDGE_32GB.value: {
        "name": "Edge Device (32GB VRAM)",
        "available_gb": 32.0,
        "recommended_engines": 2,
        "consensus_available": False,
        "tier": "moderate",
        "use_cases": ["tactical", "planning"],
    },
    HardwareProfile.EDGE_64GB.value: {
        "name": "Edge Device (64GB VRAM)",
        "available_gb": 64.0,
        "recommended_engines": 3,
        "consensus_available": True,
        "tier": "advanced",
        "use_cases": ["tactical", "reasoning", "planning"],
    },
    HardwareProfile.SERVER_128GB.value: {
        "name": "Server (128GB+ VRAM)",
        "available_gb": 128.0,
        "recommended_engines": 4,
        "consensus_available": True,
        "tier": "full_quad",
        "use_cases": ["all_domains", "consensus_voting"],
    },
}


RUNTIME_PROFILES: Dict[str, Dict[str, object]] = {
    RuntimeProfile.EDGE_MINIMAL.value: {
        "name": "Edge Minimal",
        "engines": [EngineID.PHI3.value],
        "strategy": "SINGLE_ENGINE",
        "consensus_enabled": False,
        "expected_latency_ms": 50,
        "capability_level": "tactical_only",
        "expected_success_rate": 0.92,
    },
    RuntimeProfile.EDGE_DUAL.value: {
        "name": "Edge Dual Engine",
        "engines": [EngineID.PHI3.value, EngineID.MISTRAL.value],
        "strategy": "HIERARCHICAL",
        "consensus_enabled": False,
        "expected_latency_ms": 85,
        "capability_level": "tactical_planning",
        "expected_success_rate": 0.95,
    },
    RuntimeProfile.EDGE_TRIPLE.value: {
        "name": "Edge Triple Engine",
        "engines": [EngineID.PHI3.value, EngineID.GROK.value, EngineID.MISTRAL.value],
        "strategy": "HIERARCHICAL",
        "consensus_enabled": False,
        "expected_latency_ms": 120,
        "capability_level": "all_domains",
        "expected_success_rate": 0.96,
    },
    RuntimeProfile.SERVER_FULL.value: {
        "name": "Server Full Quad",
        "engines": [
            EngineID.PHI3.value,
            EngineID.GROK.value,
            EngineID.MISTRAL.value,
            EngineID.ALLAM.value,
        ],
        "strategy": "CONSENSUS",
        "consensus_enabled": True,
        "expected_latency_ms": 200,
        "capability_level": "all_domains_consensus",
        "expected_success_rate": 0.98,
    },
}


@dataclass
class ModelProfile:
    """Engine memory and performance profile."""

    engine_id: EngineID
    name: str
    memory_footprint_gb: float
    inference_latency_ms: float
    throughput_tok_s: float
    context_window: int
    quantization: str

    def utility_score(self, primary_domain: TaskDomain, registry: EngineRegistry) -> float:
        """
        Calculate utility score in range [0.0, 1.0].

        Tactical weighting model:
        - 40%: primary domain expertise
        - 30%: average capability in other domains
        - 20%: relative throughput
        - 10%: relative speed (inverse latency)
        """
        primary_score = registry.get_capability_score(self.engine_id, primary_domain)

        # Consensus is an orchestration policy, not a direct model-specialty domain.
        other_domains = [
            domain
            for domain in TaskDomain
            if domain not in {primary_domain, TaskDomain.CONSENSUS}
        ]
        other_scores = [registry.get_capability_score(self.engine_id, domain) for domain in other_domains]
        other_avg = sum(other_scores) / len(other_scores) if other_scores else 0.5

        throughput_relative = min(self.throughput_tok_s / 36.0, 1.0)
        speed_relative = max(1.0 - (self.inference_latency_ms / 50.0), 0.0)

        score = (
            (primary_score * 0.4)
            + (other_avg * 0.3)
            + (throughput_relative * 0.2)
            + (speed_relative * 0.1)
        )
        return min(max(score, 0.0), 1.0)


@dataclass
class AllocationPlan:
    """Memory allocation plan for selected hardware profile."""

    hardware_profile: str
    available_memory_gb: float
    allocated_engines: List[EngineID]
    total_memory_used_gb: float
    slack_memory_gb: float
    load_plan: Dict[EngineID, LoadCategory]
    runtime_profile: str
    expected_latency_ms: int
    capability_level: str
    consensus_available: bool
    utilization_percent: float

    def is_feasible(self) -> bool:
        """Check if plan is feasible against memory budget."""
        return self.total_memory_used_gb <= self.available_memory_gb

    def summary(self) -> str:
        """Return human-readable summary for operators."""
        lines = [
            f"Hardware: {self.hardware_profile}",
            f"Available: {self.available_memory_gb:.1f}GB",
            f"Allocated: {self.total_memory_used_gb:.1f}GB ({self.utilization_percent:.0%})",
            f"Slack: {self.slack_memory_gb:.1f}GB",
            f"Engines: {[engine.value for engine in self.allocated_engines]}",
            f"Runtime Profile: {self.runtime_profile}",
            f"Expected Latency: {self.expected_latency_ms}ms",
            f"Capability: {self.capability_level}",
            f"Consensus: {'Enabled' if self.consensus_available else 'Disabled'}",
        ]
        return "\n".join(lines)


@dataclass
class PreloadPlan:
    """Preload execution plan derived from load categories."""

    startup_engines: List[EngineID]
    opportunistic_engines: List[EngineID]
    unload_candidates: List[EngineID]
    estimated_startup_time_ms: float
    estimated_total_memory_gb: float


@dataclass
class MemoryBudget:
    """Memory budget validation output."""

    requested_memory_gb: float
    available_memory_gb: float
    fits: bool
    overage_gb: float
    recommendation: str


class ModelOptimizer:
    """
    Intelligent resource allocator for the quad-engine stack.

    Responsibilities:
    1) load static engine resource profiles from the registry,
    2) compute constrained allocations under mission VRAM budgets,
    3) classify startup vs opportunistic model load behavior,
    4) validate candidate engine sets against hardware limits.
    """

    def __init__(self, registry: Optional[EngineRegistry] = None):
        self.registry = registry or EngineRegistry()
        self.profiles: Dict[EngineID, ModelProfile] = self._load_profiles()
        logger.info("ModelOptimizer initialized")

    # ===================== Public API =====================
    def allocate_for_hardware(
        self,
        hardware_profile: str,
        primary_domain: TaskDomain = TaskDomain.TACTICAL,
        required_engines: Optional[List[EngineID]] = None,
    ) -> AllocationPlan:
        """
        Allocate engines for a named hardware profile.

        Tactical design note:
        hardware profiles intentionally cap recommended engine count, so even if
        raw memory can fit more engines, lower tiers preserve thermal headroom,
        failover margin, and deterministic startup behavior.
        """
        if hardware_profile not in HARDWARE_PROFILES:
            raise ValueError(f"Unknown hardware profile: {hardware_profile}")

        if not isinstance(primary_domain, TaskDomain):
            raise ValueError("primary_domain must be a TaskDomain enum")

        hw = HARDWARE_PROFILES[hardware_profile]
        available_gb = float(hw["available_gb"])
        recommended_engines = int(hw["recommended_engines"])

        required = self._normalize_engine_ids(required_engines or [])
        required_memory = self.estimate_total_memory(required)
        if required_memory > available_gb:
            raise ValueError(
                f"Required engines need {required_memory:.1f}GB but only {available_gb:.1f}GB available"
            )

        max_engines = max(recommended_engines, len(required))
        allocated = self._greedy_allocate(
            available_gb=available_gb,
            primary_domain=primary_domain,
            required_engines=required,
            max_engines=max_engines,
        )

        load_plan = self._create_load_plan(allocated_engines=allocated, available_gb=available_gb)
        runtime_profile = self._select_runtime_profile(allocated)
        runtime_cfg = RUNTIME_PROFILES[runtime_profile.value]

        total_memory = self.estimate_total_memory(allocated)
        slack = available_gb - total_memory
        utilization = total_memory / available_gb if available_gb > 0 else 0.0
        plan = AllocationPlan(
            hardware_profile=hardware_profile,
            available_memory_gb=available_gb,
            allocated_engines=allocated,
            total_memory_used_gb=total_memory,
            slack_memory_gb=slack,
            load_plan=load_plan,
            runtime_profile=runtime_profile.value,
            expected_latency_ms=int(runtime_cfg["expected_latency_ms"]),
            capability_level=str(runtime_cfg["capability_level"]),
            consensus_available=bool(hw["consensus_available"]),
            utilization_percent=utilization,
        )
        logger.info(
            "Allocation for %s selected=%s memory=%.1f/%.1fGB",
            hardware_profile,
            [engine.value for engine in allocated],
            total_memory,
            available_gb,
        )
        return plan

    def recommend_runtime_profile(self, available_memory_gb: float, mission_critical: bool = False) -> str:
        """
        Recommend runtime profile from available VRAM.

        mission_critical can bias toward consensus on high-memory systems.
        """
        if available_memory_gb < 16.0:
            raise ValueError("Minimum 16GB required")

        if available_memory_gb < 25.0:
            return RuntimeProfile.EDGE_MINIMAL.value
        if available_memory_gb < 40.0:
            return RuntimeProfile.EDGE_DUAL.value
        if available_memory_gb < 70.0:
            return RuntimeProfile.EDGE_TRIPLE.value
        if mission_critical:
            return RuntimeProfile.SERVER_FULL.value
        return RuntimeProfile.SERVER_FULL.value

    def estimate_total_memory(self, engine_ids: Sequence[EngineID]) -> float:
        """Estimate total VRAM required by selected engines."""
        if engine_ids is None:
            raise ValueError("engine_ids cannot be None")
        normalized = self._normalize_engine_ids(list(engine_ids))
        return sum(self.profiles[engine_id].memory_footprint_gb for engine_id in normalized)

    def validate_budget(self, engine_ids: List[EngineID], available_memory_gb: float) -> MemoryBudget:
        """Validate selected engines against available VRAM."""
        if available_memory_gb <= 0:
            raise ValueError("available_memory_gb must be positive")

        requested = self.estimate_total_memory(engine_ids)
        overage = max(0.0, requested - available_memory_gb)
        fits = overage == 0.0

        if fits:
            recommendation = (
                f"[OK] Fits in budget ({requested:.1f}GB / {available_memory_gb:.1f}GB)."
            )
        else:
            recommendation = (
                f"[OVER] Exceeds budget by {overage:.1f}GB. "
                "Reduce loaded engines or increase available memory."
            )

        return MemoryBudget(
            requested_memory_gb=requested,
            available_memory_gb=available_memory_gb,
            fits=fits,
            overage_gb=overage,
            recommendation=recommendation,
        )

    def plan_preload(self, allocation_plan: AllocationPlan, async_loading: bool = True) -> PreloadPlan:
        """Build startup/opportunistic/unload sequencing for engine loading."""
        startup: List[EngineID] = []
        opportunistic: List[EngineID] = []
        unload_candidates: List[EngineID] = []

        for engine_id, category in allocation_plan.load_plan.items():
            if category == LoadCategory.ALWAYS_LOADED:
                startup.append(engine_id)
            elif category == LoadCategory.OPPORTUNISTIC:
                opportunistic.append(engine_id)
            elif category == LoadCategory.UNLOAD_FIRST:
                unload_candidates.append(engine_id)

        startup_time_ms = sum(self.profiles[engine].inference_latency_ms for engine in startup) * 1.5
        if not async_loading:
            # In degraded field networks, sync preload can front-load readiness cost.
            startup_time_ms += (
                sum(self.profiles[engine].inference_latency_ms for engine in opportunistic) * 1.5
            )

        return PreloadPlan(
            startup_engines=startup,
            opportunistic_engines=opportunistic,
            unload_candidates=unload_candidates,
            estimated_startup_time_ms=startup_time_ms,
            estimated_total_memory_gb=allocation_plan.total_memory_used_gb,
        )

    def get_all_profiles(self) -> Dict[str, Dict[str, object]]:
        """Return copy of hardware profiles for display APIs."""
        return {name: profile.copy() for name, profile in HARDWARE_PROFILES.items()}

    def get_profile_details(self, profile_name: str) -> Dict[str, object]:
        """
        Return profile details.

        Supports either hardware profile names (edge_32gb) or runtime profile
        names (edge_dual) so orchestrators can request details from either path.
        """
        if profile_name in HARDWARE_PROFILES:
            allocation = self.allocate_for_hardware(profile_name)
            return {
                "hardware": HARDWARE_PROFILES[profile_name].copy(),
                "runtime": RUNTIME_PROFILES[allocation.runtime_profile].copy(),
                "engines": [engine.value for engine in allocation.allocated_engines],
                "consensus": allocation.consensus_available,
            }

        if profile_name in RUNTIME_PROFILES:
            runtime = RUNTIME_PROFILES[profile_name].copy()
            mapped_hw = self._runtime_to_hardware(profile_name)
            hardware = HARDWARE_PROFILES[mapped_hw].copy()
            return {
                "hardware": hardware,
                "runtime": runtime,
                "engines": list(runtime["engines"]),
                "consensus": bool(hardware["consensus_available"]),
            }

        raise ValueError(f"Unknown profile: {profile_name}")

    # ===================== Internal Methods =====================
    def _load_profiles(self) -> Dict[EngineID, ModelProfile]:
        """Load per-engine profiles from EngineRegistry metadata."""
        profiles: Dict[EngineID, ModelProfile] = {}
        for engine_id in EngineID:
            config = self.registry.get_config(engine_id)
            profiles[engine_id] = ModelProfile(
                engine_id=engine_id,
                name=config.name,
                memory_footprint_gb=config.memory_footprint_gb,
                inference_latency_ms=config.inference_latency_ms,
                throughput_tok_s=config.throughput_tok_s,
                context_window=config.context_window,
                quantization=config.quantization,
            )
        return profiles

    def _greedy_allocate(
        self,
        available_gb: float,
        primary_domain: TaskDomain,
        required_engines: Optional[List[EngineID]] = None,
        max_engines: Optional[int] = None,
    ) -> List[EngineID]:
        """
        Greedy allocator maximizing utility/cost ratio.

        Tactical interpretation:
        the allocator favors high utility-per-GB engines first, preserving
        optional memory headroom for runtime failover and reload operations.
        """
        if available_gb <= 0:
            raise ValueError("available_gb must be positive")
        if max_engines is not None and max_engines <= 0:
            return []

        required = self._normalize_engine_ids(required_engines or [])
        allocated = list(required)
        remaining_budget = available_gb - self.estimate_total_memory(allocated)

        candidates = [engine_id for engine_id in EngineID if engine_id not in allocated]
        candidate_scores = []
        for engine_id in candidates:
            utility = self.profiles[engine_id].utility_score(primary_domain, self.registry)
            cost = self.profiles[engine_id].memory_footprint_gb
            ratio = utility / max(cost, 0.001)
            candidate_scores.append((engine_id, utility, cost, ratio))

        candidate_scores.sort(key=lambda row: (row[3], row[1]), reverse=True)

        for engine_id, _, cost, _ in candidate_scores:
            if max_engines is not None and len(allocated) >= max_engines:
                break
            if cost <= remaining_budget:
                allocated.append(engine_id)
                remaining_budget -= cost
            else:
                logger.debug(
                    "Skipping %s (cost=%.2f, remaining=%.2f)", engine_id.value, cost, remaining_budget
                )

        return sorted(allocated, key=lambda engine: engine.value)

    def _create_load_plan(
        self, allocated_engines: List[EngineID], available_gb: float
    ) -> Dict[EngineID, LoadCategory]:
        """Assign load categories used by preload and runtime memory pressure logic."""
        if available_gb <= 0:
            raise ValueError("available_gb must be positive")

        plan: Dict[EngineID, LoadCategory] = {
            engine_id: LoadCategory.NEVER_LOADED for engine_id in EngineID
        }

        if EngineID.PHI3 in allocated_engines:
            plan[EngineID.PHI3] = LoadCategory.ALWAYS_LOADED

        for engine_id in (EngineID.MISTRAL, EngineID.GROK):
            if engine_id in allocated_engines and plan[engine_id] == LoadCategory.NEVER_LOADED:
                plan[engine_id] = LoadCategory.OPPORTUNISTIC

        if EngineID.ALLAM in allocated_engines and plan[EngineID.ALLAM] == LoadCategory.NEVER_LOADED:
            plan[EngineID.ALLAM] = LoadCategory.UNLOAD_FIRST

        # Safety net for any future engine IDs added to the registry.
        for engine_id in allocated_engines:
            if plan[engine_id] == LoadCategory.NEVER_LOADED:
                plan[engine_id] = LoadCategory.OPPORTUNISTIC

        return plan

    def _select_runtime_profile(self, engines: List[EngineID]) -> RuntimeProfile:
        """Select runtime profile based on number of loaded engines."""
        engine_count = len(engines)
        if engine_count >= 4:
            return RuntimeProfile.SERVER_FULL
        if engine_count == 3:
            return RuntimeProfile.EDGE_TRIPLE
        if engine_count == 2:
            return RuntimeProfile.EDGE_DUAL
        return RuntimeProfile.EDGE_MINIMAL

    @staticmethod
    def _normalize_engine_ids(engine_ids: List[EngineID]) -> List[EngineID]:
        """Return stable, deduplicated engine list with type validation."""
        seen = set()
        normalized: List[EngineID] = []
        for engine_id in engine_ids:
            if not isinstance(engine_id, EngineID):
                raise ValueError("engine_ids must contain EngineID values")
            if engine_id in seen:
                continue
            seen.add(engine_id)
            normalized.append(engine_id)
        return normalized

    @staticmethod
    def _runtime_to_hardware(runtime_profile_name: str) -> str:
        """Map runtime profile to nearest hardware profile."""
        mapping = {
            RuntimeProfile.EDGE_MINIMAL.value: HardwareProfile.EDGE_16GB.value,
            RuntimeProfile.EDGE_DUAL.value: HardwareProfile.EDGE_32GB.value,
            RuntimeProfile.EDGE_TRIPLE.value: HardwareProfile.EDGE_64GB.value,
            RuntimeProfile.SERVER_FULL.value: HardwareProfile.SERVER_128GB.value,
        }
        return mapping[runtime_profile_name]


def estimate_inference_time(
    engines: List[EngineID],
    expected_tokens: int,
    strategy: str,
    optimizer: ModelOptimizer,
) -> Dict[str, float | str | int]:
    """
    Estimate inference timing for a given engine set and strategy.

    This is a planning estimate used by mission controllers to preflight
    latency envelopes before dispatching a live tactical prompt.
    """
    if optimizer is None:
        raise ValueError("optimizer is required")
    if expected_tokens < 0:
        raise ValueError("expected_tokens must be non-negative")
    if not engines:
        return {"error": "No engines provided"}

    normalized = ModelOptimizer._normalize_engine_ids(engines)
    normalized_strategy = (strategy or "").strip().upper()
    if not normalized_strategy:
        return {"error": "Unknown strategy: <empty>"}

    if normalized_strategy == "SINGLE_ENGINE":
        fastest = min(normalized, key=lambda engine_id: optimizer.profiles[engine_id].inference_latency_ms)
        base_latency = optimizer.profiles[fastest].inference_latency_ms
        tokens_per_sec = optimizer.profiles[fastest].throughput_tok_s
        generation_time = (expected_tokens / max(tokens_per_sec, 0.001)) * 1000.0
        return {
            "base_latency_ms": base_latency,
            "generation_time_ms": generation_time,
            "total_ms": base_latency + generation_time,
            "engine": fastest.value,
        }

    if normalized_strategy == "CONSENSUS":
        max_latency = max(optimizer.profiles[engine_id].inference_latency_ms for engine_id in normalized)
        min_throughput = min(optimizer.profiles[engine_id].throughput_tok_s for engine_id in normalized)
        generation_time = (expected_tokens / max(min_throughput, 0.001)) * 1000.0
        return {
            "base_latency_ms": max_latency,
            "generation_time_ms": generation_time,
            "total_ms": max_latency + generation_time,
            "engines": len(normalized),
            "strategy": "parallel",
        }

    if normalized_strategy == "HIERARCHICAL":
        total_latency = sum(optimizer.profiles[engine_id].inference_latency_ms for engine_id in normalized)
        avg_throughput = (
            sum(optimizer.profiles[engine_id].throughput_tok_s for engine_id in normalized)
            / float(len(normalized))
        )
        generation_time = (expected_tokens / max(avg_throughput, 0.001)) * 1000.0
        return {
            "base_latency_ms": total_latency,
            "generation_time_ms": generation_time,
            "total_ms": total_latency + generation_time,
            "engines": len(normalized),
            "strategy": "sequential",
        }

    return {"error": f"Unknown strategy: {strategy}"}

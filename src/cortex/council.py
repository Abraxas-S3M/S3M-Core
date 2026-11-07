"""Cyber engine council — routes SOC tasks by type, not untrusted keywords.

Military/tactical context: the SOC pipeline selects ``CyberTaskType`` from case
metadata; alert bodies never influence which engine runs. High-risk analytic tasks
use ACE instead of multi-engine majority vote.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

import yaml

from src.cortex.ace import (
    ACEResult,
    ReliabilityStore,
    SameEngineFamilyError,
    cross_examine,
)
from src.cortex.taint import build_engine_prompts, quarantine_extract
from src.llm_core.backends.backend_factory import BackendFactory
from src.quad_engine.model_registry import ModelRegistry, get_registry

logger = logging.getLogger("s3m.cortex.council")

DEFAULT_CORTEX_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "cortex.yaml"

ACE_TASK_TYPES = frozenset(
    {
        "attack_path",
        "root_cause",
        "campaign_correlation",
        "change_planning",
    }
)


class CyberTaskType(str, Enum):
    """Trusted task classification set by SOC/planner code — never from alert text."""

    ALERT_TRIAGE = "alert_triage"
    IOC_EXTRACTION = "ioc_extraction"
    LOG_SUMMARIZE = "log_summarize"
    ATTACK_PATH = "attack_path"
    ROOT_CAUSE = "root_cause"
    CAMPAIGN_CORRELATION = "campaign_correlation"
    CHANGE_PLANNING = "change_planning"
    REFUTE_PLAN = "refute_plan"
    ARABIC_BRIEF = "arabic_brief"
    CONFIG_REVIEW = "config_review"


@dataclass(frozen=True)
class RoleConfig:
    name: str
    engine_id: str
    family: str
    runtime_format: str
    model_file: str
    backend_config: Dict[str, Any]
    extraction_only: bool = False


@dataclass(frozen=True)
class TaskRoute:
    task_type: CyberTaskType
    role: str
    engine_id: str
    family: str
    uses_ace: bool
    ace_proposer_role: Optional[str] = None
    ace_challenger_role: Optional[str] = None
    quarantine: bool = False


@dataclass
class CouncilRunResult:
    task_type: CyberTaskType
    route: TaskRoute
    system_prompt: str
    user_prompt: str
    output: str
    ace: Optional[ACEResult] = None


class RoleEngine:
    """Council-facing engine handle with optional test-time generate override."""

    def __init__(
        self,
        *,
        role: str,
        engine_id: str,
        family: str,
        registry: ModelRegistry,
        runtime_format: str,
        model_file: str,
        backend_config: Dict[str, Any],
        generate: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        self.role = role
        self.engine_id = engine_id
        self.family = family
        self._registry = registry
        self._runtime_format = runtime_format
        self._model_file = model_file
        self._backend_config = backend_config
        self._generate = generate
        self._backend: Any = None

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if self._generate is not None:
            return self._generate(system_prompt, user_prompt)

        if self._backend is None:
            model_path = self._registry.resolve_model_path(self.engine_id)
            if model_path:
                try:
                    self._backend = BackendFactory.create(
                        self._runtime_format,
                        model_path,
                        self._backend_config,
                    )
                except ValueError:
                    logger.debug("Backend unavailable for %s; using placeholder", self.engine_id)
                    self._backend = False
            else:
                self._backend = False

        if self._backend:
            # Real backends expose generate/infer; tests use injected generate().
            if hasattr(self._backend, "generate"):
                return str(self._backend.generate(system_prompt, user_prompt))
            if hasattr(self._backend, "complete"):
                return str(self._backend.complete(system_prompt, user_prompt))

        return (
            f"[placeholder:{self.role}] Process the case using grounded evidence only.\n"
            "Emit CLAIM|evidence_id|conclusion lines."
        )


class EngineCouncil:
    """Loads cortex.yaml, maps task types to roles, and runs ACE where configured."""

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        *,
        config_path: Optional[Path] = None,
        registry: Optional[ModelRegistry] = None,
        reliability: Optional[ReliabilityStore] = None,
        engines: Optional[Dict[str, RoleEngine]] = None,
    ) -> None:
        if config is None:
            config = load_cortex_config(config_path)
        council_cfg = (config.get("engine_council") or {}) if isinstance(config, Mapping) else {}
        self._config = council_cfg
        self._registry = registry or get_registry()
        reliability_path = str(council_cfg.get("reliability_path", "/opt/s3m/state/cortex/reliability.json"))
        self._reliability = reliability or ReliabilityStore(reliability_path)
        self._roles = self._parse_roles(council_cfg.get("roles", {}))
        self._task_routing = council_cfg.get("task_routing", {})
        self._engines_override = engines

    def route(self, task_type: CyberTaskType) -> TaskRoute:
        """Resolve role and engine for a trusted task type."""
        entry = self._task_routing.get(task_type.value, {})
        role_name = str(entry.get("role", "sentinel"))
        role = self._roles.get(role_name)
        if role is None:
            raise KeyError(f"Unknown council role '{role_name}' for task {task_type.value}")

        ace_cfg = entry.get("ace") or {}
        uses_ace = bool(ace_cfg) or task_type.value in ACE_TASK_TYPES
        return TaskRoute(
            task_type=task_type,
            role=role_name,
            engine_id=role.engine_id,
            family=role.family,
            uses_ace=uses_ace,
            ace_proposer_role=str(ace_cfg.get("proposer_role", role_name)) if uses_ace else None,
            ace_challenger_role=str(ace_cfg.get("challenger_role", "challenger")) if uses_ace else None,
            quarantine=bool(entry.get("quarantine", False)),
        )

    def get_role_engine(self, role_name: str) -> RoleEngine:
        if self._engines_override and role_name in self._engines_override:
            return self._engines_override[role_name]
        role = self._roles.get(role_name)
        if role is None:
            raise KeyError(f"Unknown role: {role_name}")
        return RoleEngine(
            role=role.name,
            engine_id=role.engine_id,
            family=role.family,
            registry=self._registry,
            runtime_format=role.runtime_format,
            model_file=role.model_file,
            backend_config=dict(role.backend_config),
        )

    def record_verdict(self, engine_id: str, domain: str, correct: bool) -> None:
        """Record human feedback on an engine verdict for reliability tracking."""
        self._reliability.record_verdict(engine_id, domain, correct)

    @property
    def reliability(self) -> ReliabilityStore:
        return self._reliability

    def build_prompts(
        self,
        *,
        mission_system: str,
        trusted_context: str,
        untrusted_fields: Optional[Mapping[str, str]] = None,
    ) -> tuple[str, str]:
        """Build prompts; untrusted SOC fields are quarantined into the user prompt only."""
        quarantine = None
        if untrusted_fields:
            quarantine = quarantine_extract(
                untrusted_fields,
                datamark_prefix=str(self._config.get("datamark_prefix", "DATA|")),
                untrusted_begin=str(self._config.get("untrusted_begin", "<<<UNTRUSTED_DATA>>>")),
                untrusted_end=str(self._config.get("untrusted_end", "<<<END_UNTRUSTED_DATA>>>")),
                system_data_doctrine=str(self._config.get("system_data_doctrine", "")),
            )
        return build_engine_prompts(
            system_data_doctrine=str(self._config.get("system_data_doctrine", "")),
            mission_system=mission_system,
            trusted_context=trusted_context,
            datamarked_block=quarantine.datamarked_block if quarantine else None,
        )

    def run(
        self,
        task_type: CyberTaskType,
        *,
        evidence_ids: Optional[List[str]] = None,
        case_evidence: Optional[Mapping[str, str]] = None,
        trusted_context: str = "",
        untrusted_fields: Optional[Mapping[str, str]] = None,
        mission_system: str = "You are a cyber defense analyst for S3M.",
    ) -> CouncilRunResult:
        route = self.route(task_type)
        system_prompt, user_prompt = self.build_prompts(
            mission_system=mission_system,
            trusted_context=trusted_context,
            untrusted_fields=untrusted_fields if route.quarantine or untrusted_fields else None,
        )

        if route.uses_ace:
            proposer = self.get_role_engine(route.ace_proposer_role or route.role)
            challenger = self.get_role_engine(route.ace_challenger_role or "challenger")
            ace_result = cross_examine(
                evidence_ids=list(evidence_ids or []),
                case_evidence=case_evidence or {},
                proposer=proposer,
                challenger=challenger,
                reliability=self._reliability,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                task_domain=task_type.value,
            )
            return CouncilRunResult(
                task_type=task_type,
                route=route,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output=ace_result.recommendation,
                ace=ace_result,
            )

        engine = self.get_role_engine(route.role)
        output = engine.complete(system_prompt, user_prompt)
        return CouncilRunResult(
            task_type=task_type,
            route=route,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output=output,
        )

    def _parse_roles(self, raw: Any) -> Dict[str, RoleConfig]:
        roles: Dict[str, RoleConfig] = {}
        if not isinstance(raw, Mapping):
            return roles
        for name, cfg in raw.items():
            if not isinstance(cfg, Mapping):
                continue
            roles[str(name)] = RoleConfig(
                name=str(name),
                engine_id=str(cfg.get("engine_id", "")),
                family=str(cfg.get("family", "")),
                runtime_format=str(cfg.get("runtime_format", "gguf")),
                model_file=str(cfg.get("model_file", "")),
                backend_config=dict(cfg.get("backend_config") or {}),
                extraction_only=bool(cfg.get("extraction_only", False)),
            )
        return roles


def load_cortex_config(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = path or DEFAULT_CORTEX_CONFIG
    if not config_path.is_file():
        raise FileNotFoundError(f"Cortex config not found: {config_path}")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}
    return payload


__all__ = [
    "ACE_TASK_TYPES",
    "CyberTaskType",
    "CouncilRunResult",
    "EngineCouncil",
    "RoleEngine",
    "SameEngineFamilyError",
    "TaskRoute",
    "load_cortex_config",
]

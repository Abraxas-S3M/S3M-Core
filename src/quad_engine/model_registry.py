"""Model registry for the S3M-Core Quad-Engine Orchestration Demo Layer.

Tactical context:
    The registry is the single source of truth for which four reasoning engines
    exist, what doctrinal role each plays, and which (optional) local GGUF model
    file backs each one. For the first demo, no physical model is required: a
    missing model simply resolves to ``placeholder`` status so the demo never
    goes blank.

Security doctrine:
    * Model files are referenced by *bare filename only* and resolved strictly
      against ``S3M_MODELS_DIR``. Arbitrary paths from user input are never
      honored. This blocks path traversal and shell-injection vectors into the
      local llama.cpp runner.
    * The registry performs no network calls, no training, and never touches
      Grok/xAI, RunPod, R2, or the trainer/sync daemons.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from src.quad_engine.models import (
    ARABIC_ENGINE,
    ENGINE_IDS,
    PLANNING_ENGINE,
    REASONING_ENGINE,
    TACTICAL_ENGINE,
    EngineRecord,
    EngineRole,
    EngineStatus,
    ModelRegistryEntry,
)


def _models_dir() -> str:
    """Resolve the trusted models directory from the environment."""
    return os.environ.get("S3M_MODELS_DIR", "/opt/s3m/models")


def _local_llm_enabled() -> bool:
    """Local LLM execution is opt-in and disabled by default."""
    return os.environ.get("S3M_ENABLE_LOCAL_LLM", "false").strip().lower() in {
        "true",
        "1",
        "yes",
        "on",
    }


# Default registry seed. Status is advisory; the registry recomputes effective
# status from model presence + the local-LLM enable flag at query time.
_DEFAULT_ENTRIES: tuple[ModelRegistryEntry, ...] = (
    ModelRegistryEntry(
        engine_id=TACTICAL_ENGINE,
        display_name="S3M Tactical Engine",
        model_file="phi-3-mini-q4_k_m.gguf",
        role=EngineRole.TACTICAL,
        status=EngineStatus.PLACEHOLDER,
        max_tokens=512,
        description="Fast SITREP, track explanation, immediate operational summary.",
    ),
    ModelRegistryEntry(
        engine_id=REASONING_ENGINE,
        display_name="S3M Reasoning Engine",
        model_file="mistral-7b-instruct-q4_k_m.gguf",
        role=EngineRole.REASONING,
        status=EngineStatus.PLACEHOLDER,
        max_tokens=768,
        description="Threat assessment, competing hypotheses, confidence reasoning, anomaly analysis.",
    ),
    ModelRegistryEntry(
        engine_id=PLANNING_ENGINE,
        display_name="S3M Planning Engine",
        model_file="phi-3-mini-q4_k_m.gguf",
        role=EngineRole.PLANNING,
        status=EngineStatus.PLACEHOLDER,
        max_tokens=768,
        description="COA options, watch priorities, sensor cueing suggestions, commander task list.",
    ),
    ModelRegistryEntry(
        engine_id=ARABIC_ENGINE,
        display_name="S3M Arabic Engine",
        model_file="allam-7b-instruct-q4_k_m.gguf",
        role=EngineRole.ARABIC,
        status=EngineStatus.PLACEHOLDER,
        max_tokens=512,
        description="Arabic commander summary, terminology support, Saudi/GCC regional phrasing.",
    ),
)


class ModelRegistry:
    """In-memory registry of quad-engine model entries.

    The registry never mutates the model files on disk and never downloads
    anything. It only inspects whether an approved file already exists under the
    trusted models directory.
    """

    def __init__(
        self,
        entries: Optional[List[ModelRegistryEntry]] = None,
        *,
        models_dir: Optional[str] = None,
    ) -> None:
        seed = entries if entries is not None else list(_DEFAULT_ENTRIES)
        self._entries: Dict[str, ModelRegistryEntry] = {e.engine_id: e for e in seed}
        self._models_dir = models_dir or _models_dir()

    @property
    def models_dir(self) -> str:
        return self._models_dir

    def engine_ids(self) -> List[str]:
        return list(self._entries.keys())

    def get(self, engine_id: str) -> Optional[ModelRegistryEntry]:
        return self._entries.get(engine_id)

    def all_entries(self) -> List[ModelRegistryEntry]:
        return list(self._entries.values())

    def resolve_model_path(self, engine_id: str) -> Optional[str]:
        """Resolve the approved, sandboxed path for an engine's model file.

        Returns ``None`` if the engine is unknown or its file is not present.
        The filename is taken only from the trusted registry entry (never from
        caller input) and joined to ``S3M_MODELS_DIR``. The resolved path is
        verified to stay inside the models directory to defeat traversal.
        """
        entry = self._entries.get(engine_id)
        if entry is None or not entry.model_file:
            return None

        # Reject any registry filename that tries to escape the directory.
        filename = entry.model_file
        if os.path.sep in filename or (os.path.altsep and os.path.altsep in filename):
            return None
        if filename in {".", ".."}:
            return None

        base = Path(self._models_dir).resolve()
        candidate = (base / filename).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        if candidate.is_file():
            return str(candidate)
        return None

    def model_present(self, engine_id: str) -> bool:
        return self.resolve_model_path(engine_id) is not None

    def effective_status(self, engine_id: str) -> EngineStatus:
        """Compute the live status of an engine for the current environment.

        * If the engine is unknown -> ``unavailable``.
        * If local LLM is enabled AND the approved model file exists ->
          ``live_local``.
        * Otherwise -> ``placeholder`` (deterministic demo output).
        """
        entry = self._entries.get(engine_id)
        if entry is None:
            return EngineStatus.UNAVAILABLE
        if _local_llm_enabled() and self.model_present(engine_id):
            return EngineStatus.LIVE_LOCAL
        return EngineStatus.PLACEHOLDER

    def engine_status_map(self) -> Dict[str, EngineStatus]:
        return {eid: self.effective_status(eid) for eid in self._entries}

    def to_records(self) -> List[EngineRecord]:
        """Return GUI-safe engine records (no paths, no secrets)."""
        records: List[EngineRecord] = []
        for eid, entry in self._entries.items():
            records.append(
                EngineRecord(
                    engine_id=eid,
                    display_name=entry.display_name,
                    role=entry.role,
                    status=self.effective_status(eid),
                    model_present=self.model_present(eid),
                    max_tokens=entry.max_tokens,
                    description=entry.description,
                )
            )
        return records


_GLOBAL_REGISTRY: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    """Return the process-wide model registry singleton."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = ModelRegistry()
    return _GLOBAL_REGISTRY


def local_llm_enabled() -> bool:
    """Public helper mirroring the S3M_ENABLE_LOCAL_LLM flag."""
    return _local_llm_enabled()

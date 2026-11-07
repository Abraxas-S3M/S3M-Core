"""Load quad-engine registry entries from configs/engines.yaml.

Tactical context:
    Field operators maintain one engines document; the demo layer derives bare
    model filenames and council bindings from that file instead of hardcoding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.cortex.model_admission import load_engines_document, quad_engine_bindings
from src.quad_engine.models import (
    ARABIC_ENGINE,
    ENGINE_IDS,
    PLANNING_ENGINE,
    REASONING_ENGINE,
    TACTICAL_ENGINE,
    EngineRole,
    EngineStatus,
    ModelRegistryEntry,
)

_DEFAULT_ENGINES_PATH = "configs/engines.yaml"

_ROLE_BY_QUAD: Dict[str, EngineRole] = {
    TACTICAL_ENGINE: EngineRole.TACTICAL,
    REASONING_ENGINE: EngineRole.REASONING,
    PLANNING_ENGINE: EngineRole.PLANNING,
    ARABIC_ENGINE: EngineRole.ARABIC,
}

_DESCRIPTIONS: Dict[str, str] = {
    TACTICAL_ENGINE: "Fast SITREP, track explanation, immediate operational summary.",
    REASONING_ENGINE: "Threat assessment, competing hypotheses, confidence reasoning, anomaly analysis.",
    PLANNING_ENGINE: "COA options, watch priorities, sensor cueing suggestions, commander task list.",
    ARABIC_ENGINE: "Arabic commander summary, terminology support, Saudi/GCC regional phrasing.",
}


def engines_yaml_path(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(_DEFAULT_ENGINES_PATH)


def load_registry_entries(engines_path: Optional[str] = None) -> List[ModelRegistryEntry]:
    """Build ModelRegistryEntry list from engines.yaml quad_engine_map."""
    path = engines_yaml_path(engines_path)
    doc = load_engines_document(str(path))
    engines = doc.get("engines") or {}
    bindings = quad_engine_bindings(str(path))
    entries: List[ModelRegistryEntry] = []

    for quad_id in ENGINE_IDS:
        backing = bindings.get(quad_id)
        if not backing:
            raise KeyError(f"quad_engine_map missing binding for {quad_id}")
        cfg = engines.get(backing)
        if not isinstance(cfg, dict):
            raise KeyError(f"engines.{backing} missing for quad binding {quad_id}")
        model_file = str(cfg.get("model_file") or "").strip()
        max_tokens = int(cfg.get("max_tokens") or 512)
        display_name = str(cfg.get("name") or backing)
        entries.append(
            ModelRegistryEntry(
                engine_id=quad_id,
                display_name=display_name,
                model_file=model_file,
                role=_ROLE_BY_QUAD[quad_id],
                status=EngineStatus.PLACEHOLDER,
                max_tokens=max_tokens,
                description=_DESCRIPTIONS.get(quad_id, ""),
            )
        )
    return entries


def load_yaml_raw(engines_path: Optional[str] = None) -> Dict[str, object]:
    path = engines_yaml_path(engines_path)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

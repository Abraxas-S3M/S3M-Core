"""Classify SOAR playbook steps for Cortex PolicyGate routing."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Set

import yaml

from services.cyber.models import PlaybookAction, PlaybookStepKind

_SCHEMA_PATH = Path("configs/cyber/playbook_schema.yaml")

_MUTATE_KEYWORDS = (
    "block",
    "isolate",
    "disable",
    "revoke",
    "quarantine",
    "delete",
    "push",
    "config",
    "destroy",
    "purge",
)

_READ_KEYWORDS = ("enrich", "lookup", "collect", "scan", "evidence")

_PLAN_KEYWORDS = ("draft", "recommend", "notify", "report", "llm", "analysis")

_FORBIDDEN_ACTIONS: Set[str] = {
    "DELETE_EVIDENCE",
    "DELETE_FILE",
    "PURGE_LOGS",
    "DESTROY_ARTIFACT",
}


@lru_cache(maxsize=1)
def _load_schema_maps() -> tuple[Dict[str, PlaybookStepKind], Set[str]]:
    action_map: Dict[str, PlaybookStepKind] = {}
    forbidden: Set[str] = set(_FORBIDDEN_ACTIONS)
    if not _SCHEMA_PATH.is_file():
        return action_map, forbidden
    payload = yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8")) or {}
    classifications = payload.get("action_classifications", {})
    if isinstance(classifications, dict):
        for kind_name, actions in classifications.items():
            try:
                kind = PlaybookStepKind.from_value(kind_name)
            except ValueError:
                continue
            if not isinstance(actions, list):
                continue
            for action in actions:
                action_map[str(action).strip().upper()] = kind
    raw_forbidden = payload.get("forbidden_actions", [])
    if isinstance(raw_forbidden, list):
        forbidden.update(str(item).strip().upper() for item in raw_forbidden)
    return action_map, forbidden


def forbidden_playbook_actions() -> Set[str]:
    _, forbidden = _load_schema_maps()
    return set(forbidden)


def is_forbidden_action(action: PlaybookAction | str) -> bool:
    token = action.value if isinstance(action, PlaybookAction) else str(action)
    return token.strip().upper() in forbidden_playbook_actions()


def _keyword_kind(text: str) -> Optional[PlaybookStepKind]:
    lowered = text.lower()
    if any(keyword in lowered for keyword in _MUTATE_KEYWORDS):
        return PlaybookStepKind.MUTATE
    if any(keyword in lowered for keyword in _READ_KEYWORDS):
        return PlaybookStepKind.READ
    if any(keyword in lowered for keyword in _PLAN_KEYWORDS):
        return PlaybookStepKind.PLAN
    return None


def classify_playbook_step(
    action: PlaybookAction,
    *,
    override_kind: Optional[str] = None,
    parameters: Optional[dict] = None,
    step_name: str = "",
) -> PlaybookStepKind:
    """Resolve step kind; unknown actions default to mutate for safety."""
    if override_kind:
        return PlaybookStepKind.from_value(override_kind)

    action_map, _ = _load_schema_maps()
    mapped = action_map.get(action.value)
    if mapped is not None:
        return mapped

    for token in (action.value, step_name):
        hinted = _keyword_kind(token)
        if hinted is not None:
            return hinted

    if parameters:
        param_blob = " ".join(str(value) for value in parameters.values())
        hinted = _keyword_kind(param_blob)
        if hinted is not None:
            return hinted
        custom_action = str(parameters.get("action", ""))
        if custom_action:
            hinted = _keyword_kind(custom_action)
            if hinted is not None:
                return hinted

    # Tactical default: treat unrecognized response actions as state-changing.
    return PlaybookStepKind.MUTATE


def resolve_tool_name(action: PlaybookAction, parameters: dict) -> str:
    if action == PlaybookAction.CUSTOM:
        custom = str(parameters.get("action", "CUSTOM")).strip().upper()
        return re.sub(r"[^A-Z0-9_]+", "_", custom) or "CUSTOM"
    return action.value

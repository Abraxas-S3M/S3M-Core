"""Load logical action → XiiD MCP tool mappings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MAP = _REPO_ROOT / "configs/xiid_tool_map.yaml"


@dataclass(slots=True, frozen=True)
class ActionBinding:
    """One planner/broker action bound to an MCP tool."""

    action: str
    tool: str
    tool_class: str
    kind: str

    @property
    def requires_envelope(self) -> bool:
        return self.kind == "write"


class XiidToolMap:
    """Resolves logical action names to placeholder XiiD tool identifiers."""

    def __init__(self, actions: Mapping[str, ActionBinding]) -> None:
        self._actions = dict(actions)

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> "XiidToolMap":
        map_path = path or _DEFAULT_MAP
        raw = yaml.safe_load(map_path.read_text(encoding="utf-8"))
        actions: Dict[str, ActionBinding] = {}
        for action, spec in raw.get("actions", {}).items():
            actions[action] = ActionBinding(
                action=action,
                tool=str(spec["tool"]),
                tool_class=str(spec.get("class", "")),
                kind=str(spec.get("kind", "read")),
            )
        return cls(actions)

    def resolve(self, action: str) -> ActionBinding:
        if action not in self._actions:
            raise KeyError(f"unknown logical action: {action}")
        return self._actions[action]

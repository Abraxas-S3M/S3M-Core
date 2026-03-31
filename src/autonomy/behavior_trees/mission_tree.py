"""Mission tree builder for tactical YAML-defined behavior plans.

Mission definitions allow commanders to express doctrinal OODA behavior
without changing Python code, while still validating tactical safety rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict

import yaml

from .llm_replan_node import LLMReplanNode
from .nodes import (
    ActionNode,
    BTNode,
    ConditionNode,
    EngageNode,
    HoldNode,
    PatrolNode,
    ReconNode,
    RetreatNode,
    RTBNode,
    SelectorNode,
    SequenceNode,
)


@dataclass
class MissionTree:
    """Build behavior trees from YAML mission definitions."""

    yaml_path_or_dict: str | Dict[str, Any]

    def __post_init__(self) -> None:
        if isinstance(self.yaml_path_or_dict, dict):
            self.raw = self.yaml_path_or_dict
        else:
            path = Path(self.yaml_path_or_dict)
            if not path.exists():
                raise FileNotFoundError(f"mission YAML not found: {path}")
            with path.open("r", encoding="utf-8") as handle:
                self.raw = yaml.safe_load(handle) or {}

        mission = self.raw.get("mission")
        if not isinstance(mission, dict):
            raise ValueError("mission definition must contain 'mission' mapping")
        tree = mission.get("tree")
        if not isinstance(tree, dict):
            raise ValueError("mission definition must contain mission.tree mapping")
        self.tree_spec = tree

    def build(self) -> BTNode:
        """Validate and build tactical behavior tree."""
        root = self._build_node(self.tree_spec)
        self._validate(root)
        return root

    def _validate(self, node: BTNode) -> None:
        if isinstance(node, (SequenceNode, SelectorNode)) and not node.children:
            raise ValueError(f"{node.name} cannot have empty children")
        for child in node.children:
            self._validate(child)

    def _build_node(self, spec: Dict[str, Any]) -> BTNode:
        if not isinstance(spec, dict):
            raise ValueError("tree node spec must be a mapping")
        node_type = str(spec.get("type", "")).strip().lower()
        if not node_type:
            raise ValueError("tree node missing type")
        name = str(spec.get("name", node_type))

        if node_type == "sequence":
            children = [self._build_node(child) for child in spec.get("children", [])]
            return SequenceNode(name=name, children=children)
        if node_type == "selector":
            children = [self._build_node(child) for child in spec.get("children", [])]
            return SelectorNode(name=name, children=children)
        if node_type == "condition":
            check = str(spec.get("check", "")).strip()
            if not check:
                raise ValueError(f"condition '{name}' missing check expression")
            return ConditionNode(name=name, check_fn=self._compile_check(check))
        if node_type == "action":
            action_name = str(spec.get("node", "")).strip().lower()
            return self._action_from_name(name=name, action_name=action_name)
        raise ValueError(f"unsupported node type: {node_type}")

    def _action_from_name(self, name: str, action_name: str) -> BTNode:
        mapping = {
            "patrol": PatrolNode,
            "engage": EngageNode,
            "recon": ReconNode,
            "retreat": RetreatNode,
            "hold": HoldNode,
            "rtb": RTBNode,
            "llm_replan": LLMReplanNode,
        }
        node_class = mapping.get(action_name)
        if node_class is None:
            raise ValueError(f"unknown action node: {action_name}")
        if node_class is LLMReplanNode:
            return LLMReplanNode(name=name)
        return node_class(name=name)

    def _compile_check(self, expression: str) -> Callable[[Dict[str, Any]], bool]:
        tokens = expression.strip().split()
        if len(tokens) < 3:
            raise ValueError(f"invalid condition expression: {expression}")
        key = tokens[0]
        operator = tokens[1]
        value_expr = " ".join(tokens[2:])

        def _parse_value(raw: str, ctx: Dict[str, Any]) -> Any:
            lowered = raw.lower()
            if lowered in {"true", "false"}:
                return lowered == "true"
            if raw in ctx:
                return ctx.get(raw)
            try:
                if "." in raw:
                    return float(raw)
                return int(raw)
            except ValueError:
                return raw

        def _check(ctx: Dict[str, Any]) -> bool:
            left = ctx.get(key)
            right = _parse_value(value_expr, ctx)
            if operator == "==":
                return left == right
            if operator == "!=":
                return left != right
            if operator == ">":
                return float(left or 0) > float(right)
            if operator == "<":
                return float(left or 0) < float(right)
            if operator == ">=":
                return float(left or 0) >= float(right)
            if operator == "<=":
                return float(left or 0) <= float(right)
            raise ValueError(f"unsupported operator in check: {operator}")

        return _check

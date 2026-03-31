#!/usr/bin/env python3
"""Focused behavior tree demo for S3M Phase 6 autonomy.

Demonstrates a small tactical behavior chain and shows tick-by-tick decisions,
including LLM replan fallback when orchestrator guidance is unavailable.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.autonomy.behavior_trees import (  # noqa: E402
    LLMReplanNode,
    MissionExecutor,
    PatrolNode,
    RTBNode,
    SequenceNode,
    SelectorNode,
    EngageNode,
    ConditionNode,
    BTStatus,
)


def build_demo_tree() -> SequenceNode:
    engage_or_replan = SelectorNode(
        "engage_or_replan",
        children=[
            SequenceNode(
                "threat_check_then_engage",
                children=[
                    ConditionNode(
                        "threat_is_close",
                        lambda ctx: float(ctx.get("nearest_threat_distance", 999.0)) < 40.0,
                    ),
                    EngageNode("engage_if_authorized"),
                ],
            ),
            LLMReplanNode("llm_replan_if_no_direct_action"),
        ],
    )
    return SequenceNode(
        "demo_sequence",
        children=[
            PatrolNode("patrol_phase"),
            engage_or_replan,
            RTBNode("return_to_base_phase"),
        ],
    )


def main() -> int:
    tree = build_demo_tree()
    context = {
        "agent_id": "demo_agent",
        "mission_id": "demo_behavior",
        "rules_of_engagement": "weapons_tight",
        "waypoints": [(10.0, 5.0, 50.0), (20.0, 10.0, 50.0), (30.0, 15.0, 50.0)],
        "agent_position": (0.0, 0.0, 50.0),
        "patrol_step": 8.0,
        "base_position": (0.0, 0.0, 50.0),
        "threats": [{"id": "t1", "position": (27.0, 14.0, 50.0), "threat_level": 0.8}],
        "nearest_threat_distance": 35.0,
        "decision_log": [],
    }

    executor = MissionExecutor(tree=tree, tick_rate_hz=5.0)
    executor.start(context)
    print("== Behavior Tree Demo ==")
    for i in range(15):
        status = executor.tick()
        node_path = executor.get_current_node_path()
        print(f"Tick {i+1:02d}: status={status.value}, active_path={node_path}")
        if i == 5:
            # Tactical context shift: threat moved outside direct engage range.
            context["nearest_threat_distance"] = 90.0
            context["threats"] = [{"id": "t2", "position": (100.0, 100.0, 50.0), "threat_level": 0.6}]
        if status in {BTStatus.SUCCESS, BTStatus.FAILURE}:
            break
        time.sleep(0.05)

    print("\nRecent decisions:")
    for decision in context.get("decision_log", [])[-8:]:
        print(
            f"- {decision.timestamp.isoformat()} | {decision.decision_type.value.upper()} "
            f"| risk={decision.risk_score:.2f} | reason={decision.reasoning}"
        )

    print("\nLLMReplan fallback note:")
    print(context.get("replan_reason", "No replan fallback encountered"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

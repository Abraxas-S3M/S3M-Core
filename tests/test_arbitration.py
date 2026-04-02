"""Tests for game-theoretic multi-agent arbitration components."""

from __future__ import annotations

from src.autonomy.arbitration import (
    AuctionAllocator,
    ByzantineConsensus,
    CoalitionEngine,
    ConflictResolver,
    MultiAgentArbitrator,
)
from src.autonomy.models import AgentCapability, AgentInfo, AgentRole, AgentState


def _agent(agent_id: str, x: float = 0.0, battery: float = 90.0) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        role=AgentRole.FOLLOWER,
        state=AgentState.IDLE,
        capability=AgentCapability.AIR,
        position=(x, 0.0, 0.0),
        heading=0.0,
        speed=0.0,
        battery_pct=battery,
        fuel_pct=80.0,
        sensor_loadout=["eo", "ir"],
        weapon_loadout=["basic"],
        comms_status="nominal",
    )


def test_shapley_value_known_three_player_game() -> None:
    coalition = CoalitionEngine(mc_samples=400, random_seed=7)

    def value_fn(team: list[str]) -> float:
        # Additive game: Shapley equals standalone values.
        values = {"a": 1.0, "b": 2.0, "c": 3.0}
        return sum(values.get(member, 0.0) for member in team)

    shapley = coalition.approximate_shapley(["a", "b", "c"], value_fn)
    assert abs(shapley["a"] - 1.0) < 0.25
    assert abs(shapley["b"] - 2.0) < 0.25
    assert abs(shapley["c"] - 3.0) < 0.25


def test_coalition_stability_check() -> None:
    coalition = CoalitionEngine(mc_samples=200, random_seed=3)
    agents = ["a1", "a2", "a3"]
    objectives = ["obj1", "obj2"]
    result = coalition.form_coalitions(agents, objectives)
    assert result["core_stable"] is True
    assert result["individually_rational"] is True


def test_cbba_convergence_with_five_agents_tasks() -> None:
    allocator = AuctionAllocator(max_rounds=50)
    agents = [f"a{i}" for i in range(5)]
    tasks = [f"t{i}" for i in range(5)]
    values = {(a, t): float(5 - abs(i - j)) for i, a in enumerate(agents) for j, t in enumerate(tasks)}
    out = allocator.allocate(agents, tasks, values)
    assert out["converged"] is True
    assert out["rounds"] <= 50
    assert len(out["assignments"]) == 5


def test_byzantine_consensus_approve_reject_override() -> None:
    protocol = ByzantineConsensus()
    nodes = ["n1", "n2", "n3", "n4"]
    approve = protocol.run_consensus(nodes, {"n1": "approve", "n2": "approve", "n3": "approve", "n4": "reject"})
    assert approve["result"] == "APPROVE"
    reject = protocol.run_consensus(nodes, {"n1": "reject", "n2": "reject", "n3": "reject", "n4": "approve"})
    assert reject["result"] == "REJECT"
    override = protocol.run_consensus(
        nodes,
        {"n1": "reject", "n2": "reject", "n3": "approve", "n4": "approve"},
        commander_override="APPROVE",
    )
    assert override["result"] == "APPROVE"
    assert override.get("commander_override") is True


def test_conflict_detection_roe_and_resource_contention() -> None:
    resolver = ConflictResolver()
    directives = [
        {"id": "d1", "type": "engage", "rules_of_engagement": "weapons_free", "resource": "uav-1", "priority": 3},
        {"id": "d2", "type": "hold", "rules_of_engagement": "weapons_hold", "resource": "uav-1", "priority": 2},
    ]
    conflicts = resolver.detect_conflicts(directives)
    conflict_types = {c["type"] for c in conflicts}
    assert "ROE_CONTRADICTION" in conflict_types
    assert "RESOURCE_CONTENTION" in conflict_types


def test_full_arbitrator_pipeline() -> None:
    arbitrator = MultiAgentArbitrator()
    agents = [_agent("a1", x=10.0), _agent("a2", x=20.0), _agent("a3", x=30.0)]
    mission = {"mission_id": "m-1", "objectives": ["recon", "cover"], "rules_of_engagement": "weapons_tight", "priority": 2}
    out = arbitrator.arbitrate(agents=agents, mission=mission, mode="coalition")
    assert out["mode"] == "coalition"
    assert isinstance(out["assignments"], dict)
    assert "consensus_result" in out


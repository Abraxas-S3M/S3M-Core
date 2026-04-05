"""Tests for S3M advanced multi-agent intelligence extensions."""

from datetime import datetime, timezone

from src.autonomy.arbitration.arbitrator import MultiAgentArbitrator
from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    Mission,
    MissionStatus,
    MissionType,
)
from src.autonomy.swarm.agent_comm_protocol import AgentCommProtocol, AgentMessage, MessageType
from src.autonomy.swarm.coordinator import SwarmCoordinator
from src.autonomy.swarm.game_theoretic_layer import GameTheoreticLayer
from src.autonomy.swarm.negotiation.contract_net import ContractNetProtocol, Proposal


def _agent(agent_id: str, x: float = 0.0, battery: float = 90.0) -> AgentInfo:
    return AgentInfo(
        agent_id=agent_id,
        role=AgentRole.FOLLOWER,
        state=AgentState.IDLE,
        capability=AgentCapability.AIR,
        position=(x, 0.0, 10.0),
        heading=0.0,
        speed=0.0,
        battery_pct=battery,
        fuel_pct=80.0,
        last_heartbeat=datetime.now(timezone.utc),
        sensor_loadout=["eo", "ir"],
        weapon_loadout=["basic"],
        comms_status="nominal",
    )


def _mission(mission_id: str = "m-advanced") -> Mission:
    return Mission(
        mission_id=mission_id,
        mission_type=MissionType.RECON,
        status=MissionStatus.PENDING,
        title="Recon",
        description="Recon tactical area",
        assigned_agents=[],
        waypoints=[(100.0, 0.0, 10.0)],
        priority=2,
        rules_of_engagement="weapons_tight",
        parameters={"min_agents": 1, "deadline_ms": 5000},
    )


def test_contract_net_basic_negotiation() -> None:
    cnp = ContractNetProtocol()
    cfp = cnp.create_cfp(task_id="recon-alpha", issuer_id="command")

    cnp.submit_proposal(
        cfp.cfp_id,
        Proposal(
            agent_id="uav-1",
            cfp_id=cfp.cfp_id,
            cost_estimate=50.0,
            time_estimate_ms=3000.0,
            capability_score=0.9,
        ),
    )
    cnp.submit_proposal(
        cfp.cfp_id,
        Proposal(
            agent_id="uav-2",
            cfp_id=cfp.cfp_id,
            cost_estimate=80.0,
            time_estimate_ms=2000.0,
            capability_score=0.7,
        ),
    )
    cnp.submit_proposal(
        cfp.cfp_id,
        Proposal(
            agent_id="uav-3",
            cfp_id=cfp.cfp_id,
            cost_estimate=30.0,
            time_estimate_ms=4000.0,
            capability_score=0.8,
        ),
    )

    result = cnp.evaluate_and_award(cfp.cfp_id)
    assert result.success is True
    assert result.winner_agent_id is not None
    assert result.total_proposals == 3
    assert result.rationale_en
    assert result.rationale_ar


def test_contract_net_insufficient_proposals() -> None:
    cnp = ContractNetProtocol()
    cfp = cnp.create_cfp(task_id="strike-bravo", min_proposals=3)
    cnp.submit_proposal(cfp.cfp_id, Proposal(agent_id="uav-1", cfp_id=cfp.cfp_id, capability_score=0.9))
    result = cnp.evaluate_and_award(cfp.cfp_id)
    assert result.success is False


def test_contract_net_arbitrator_integration() -> None:
    cnp = ContractNetProtocol()
    agents = [_agent("a1", x=20.0), _agent("a2", x=30.0), _agent("a3", x=40.0)]
    cfp = cnp.create_cfp(task_id="integration-task", min_proposals=1)
    for idx, agent in enumerate(agents):
        cnp.submit_proposal(
            cfp.cfp_id,
            Proposal(
                cfp_id=cfp.cfp_id,
                agent_id=agent.agent_id,
                cost_estimate=40.0 + (idx * 5),
                time_estimate_ms=1500.0 + (idx * 50.0),
                capability_score=0.8 - (idx * 0.05),
            ),
        )
    result = cnp.evaluate_with_arbitrator(
        cfp_id=cfp.cfp_id,
        arbitrator=MultiAgentArbitrator(),
        agents=agents,
        mode="coalition",
    )
    assert result.success is True
    assert "assignments" in result.arbitration_summary


def test_game_theoretic_nash_equilibrium() -> None:
    gt = GameTheoreticLayer(seed=42)
    agents = ["a1", "a2"]
    actions = {"a1": ["left", "right"], "a2": ["left", "right"]}

    def utility(agent: str, action: str, profile: dict) -> float:
        if profile["a1"] == profile["a2"]:
            return 1.0 if agent == "a1" else 0.5
        return 0.5 if agent == "a1" else 1.0

    payoffs = gt.build_payoff_matrix(agents, actions, utility)
    result = gt.find_nash_equilibrium(agents, actions, payoffs)
    assert "equilibrium" in result
    assert result["equilibrium"]["a1"] in ["left", "right"]
    assert isinstance(result["stable"], bool)


def test_game_theoretic_fictitious_play() -> None:
    gt = GameTheoreticLayer(seed=7)
    agents = ["x", "y"]
    actions = {"x": ["A", "B"], "y": ["A", "B"]}

    def utility(agent: str, action: str, profile: dict) -> float:
        return 0.8 if action == "A" else 0.6

    mixed = gt.fictitious_play(agents, actions, utility, rounds=50)
    assert "x" in mixed
    assert abs(sum(mixed["x"].values()) - 1.0) < 0.01


def test_agent_comm_protocol_unicast_and_broadcast() -> None:
    comm = AgentCommProtocol()
    comm.register_agent("a1")
    comm.register_agent("a2")
    comm.register_agent("a3")

    unicast = AgentMessage(
        sender_id="a1",
        receiver_id="a2",
        message_type=MessageType.INFORM,
        payload={"position": [10.0, 20.0]},
    )
    assert comm.send(unicast) is True
    received = comm.receive("a2")
    assert len(received) == 1
    assert received[0].sender_id == "a1"

    broadcast = AgentMessage(
        sender_id="a1",
        receiver_id="*",
        message_type=MessageType.ALERT,
        payload={"threat": "incoming"},
    )
    assert comm.send(broadcast) is True
    assert len(comm.receive("a2")) == 1
    assert len(comm.receive("a3")) == 1
    assert len(comm.receive("a1")) == 0


def test_agent_message_serialization_roundtrip() -> None:
    comm = AgentCommProtocol()
    msg = AgentMessage(
        sender_id="alpha",
        receiver_id="beta",
        message_type=MessageType.REQUEST,
        payload={"task": "scan"},
    )
    encoded = comm.serialize_message(msg)
    decoded = comm.deserialize_message(encoded)
    assert decoded.sender_id == "alpha"
    assert decoded.payload["task"] == "scan"


def test_swarm_coordinator_contract_net_and_stability() -> None:
    coord = SwarmCoordinator(max_agents=10)
    coord.register_agent(_agent("uav-1", x=10.0, battery=95.0))
    coord.register_agent(_agent("uav-2", x=40.0, battery=88.0))
    mission = _mission("mission-cnp")
    assignments = coord.assign_mission_contract_net(mission, mode="coalition")
    assert assignments
    assert mission.mission_id in coord.mission_assignments

    stability = coord.evaluate_mission_stability(mission, mode="coalition")
    assert "equilibrium" in stability
    assert "arbitration" in stability


def test_multi_agent_arbitrator_contract_net_adapter() -> None:
    arbitrator = MultiAgentArbitrator()
    result = arbitrator.arbitrate_with_contract_net(
        task_id="adapter-task",
        proposals=[
            {"agent_id": "a1", "cost_estimate": 50.0, "time_estimate_ms": 2500.0, "capability_score": 0.9},
            {"agent_id": "a2", "cost_estimate": 70.0, "time_estimate_ms": 2400.0, "capability_score": 0.8},
        ],
    )
    assert result["task_id"] == "adapter-task"
    assert isinstance(result["success"], bool)

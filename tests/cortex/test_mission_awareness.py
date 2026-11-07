"""Mission-aware Cortex quarantine and MRC costing tests."""

from __future__ import annotations

from src.cop.event_bus import CopEventBus
from src.cortex.fixtures.cctv import build_cctv_twin
from src.cortex.mrc import MissionResponseCost
from src.cortex.models import BindingSource, MissionBinding, MissionFlow, NetworkEdge
from src.cortex.service import CortexMissionService
from src.cortex.twin import NetworkTwin
from src.planning.mission_planner import MultiDomainMissionPlanner


def test_activating_mission_adds_required_flows() -> None:
    twin = build_cctv_twin(activate_patrol=False)
    bus = CopEventBus()
    service = CortexMissionService(twin=twin, event_bus=bus)
    service.activate_mission("perimeter-watch")
    assert ("cameras", "video_wall", "video-wall-feed") in twin.required_flows
    assert "nvr-wall" in twin.protected_edges
    assert "cam-nvr" in twin.protected_edges


def test_mrc_avoids_cutting_active_mission_edge_when_alternative_exists() -> None:
    twin = build_cctv_twin(activate_patrol=True)
    mrc = MissionResponseCost()
    candidates = twin.candidate_disruption_edges("nvr_cluster")
    chosen = mrc.select_disruption_target(candidates, twin)
    assert chosen.edge_id != "nvr-wall"
    assert chosen.edge_id in {"nvr-admin", "nvr-backup", "nvr-internet"}


def test_cctv_minimal_profile_preserves_video_wall_feed() -> None:
    twin = build_cctv_twin(activate_patrol=True)
    planner = MultiDomainMissionPlanner(network_twin=twin)
    plan = planner.plan_minimal_profile("nvr_cluster")
    assert "nvr-wall" in plan.keep_edges
    assert "cam-nvr" in plan.keep_edges
    narrowed = {change.edge_id for change in plan.narrow_edges}
    assert narrowed == {"nvr-admin", "nvr-backup", "nvr-internet"}
    assert plan.escalates_to_human is False


def test_impossible_minimal_profile_escalates() -> None:
    twin = NetworkTwin()
    twin.add_edge(
        NetworkEdge(
            edge_id="a-suspect",
            source="sector_a",
            destination="suspect_bridge",
            purpose="link-a",
            partition="test",
        )
    )
    twin.add_edge(
        NetworkEdge(
            edge_id="suspect-b",
            source="suspect_bridge",
            destination="sector_b",
            purpose="link-b",
            partition="test",
        )
    )
    twin.store_binding(
        MissionBinding(
            mission_id="dual-route",
            name="Dual sector relay",
            priority=2,
            window_start="2026-11-07T00:00:00+00:00",
            window_end="2026-11-08T00:00:00+00:00",
            flows=[
                MissionFlow(
                    source="sector_a",
                    destination="sector_b",
                    purpose="primary",
                ),
                MissionFlow(
                    source="sector_a",
                    destination="sector_c",
                    purpose="secondary",
                ),
            ],
            source=BindingSource.OPERATOR,
            partition="test",
        )
    )
    twin.activate_binding("dual-route")
    planner = MultiDomainMissionPlanner(network_twin=twin)
    plan = planner.plan_minimal_profile("suspect_bridge")
    assert plan.escalates_to_human is True
    assert plan.keep_edges == []
    assert "sector_c" in plan.reason


def test_cortex_publishes_recommendation_to_cop_bus() -> None:
    twin = build_cctv_twin(activate_patrol=True)
    bus = CopEventBus()
    service = CortexMissionService(twin=twin, event_bus=bus)
    service.propose_minimal_profile("nvr_cluster")
    events = bus.recent(track="cyber_cortex", limit=5)
    assert events
    assert events[-1].event_type == "cortex_recommendation"
    assert events[-1].ai_context.route_hint == "planning"
    assert "keep_edges" in events[-1].payload

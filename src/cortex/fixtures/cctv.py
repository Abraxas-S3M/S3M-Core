"""CCTV sector fixture — NVR cluster with video-wall mission dependency.

Tactical context:
    Base perimeter CCTV often funnels camera streams through an NVR cluster before
    the operations video wall. Cortex tests lock quarantine behavior on that path.
"""

from __future__ import annotations

from src.cortex.models import BindingSource, MissionBinding, MissionFlow, NetworkEdge
from src.cortex.twin import NetworkTwin


def build_cctv_twin(*, activate_patrol: bool = False) -> NetworkTwin:
    twin = NetworkTwin()
    edges = [
        NetworkEdge(
            edge_id="cam-nvr",
            source="cameras",
            destination="nvr_cluster",
            purpose="ingest",
            partition="cctv",
            disruption_cost=1.0,
        ),
        NetworkEdge(
            edge_id="nvr-wall",
            source="nvr_cluster",
            destination="video_wall",
            purpose="video-wall-feed",
            partition="cctv",
            disruption_cost=2.0,
        ),
        NetworkEdge(
            edge_id="nvr-admin",
            source="nvr_cluster",
            destination="admin_workstation",
            purpose="administration",
            partition="cctv",
            disruption_cost=0.5,
        ),
        NetworkEdge(
            edge_id="nvr-backup",
            source="nvr_cluster",
            destination="backup_san",
            purpose="backup",
            partition="cctv",
            disruption_cost=0.5,
        ),
        NetworkEdge(
            edge_id="nvr-internet",
            source="nvr_cluster",
            destination="internet_gateway",
            purpose="vendor-updates",
            partition="cctv",
            disruption_cost=0.25,
        ),
    ]
    for edge in edges:
        twin.add_edge(edge)

    binding = MissionBinding(
        mission_id="perimeter-watch",
        name="Perimeter CCTV wall watch",
        priority=4,
        window_start="2026-11-07T00:00:00+00:00",
        window_end="2026-11-08T00:00:00+00:00",
        flows=[
            MissionFlow(
                source="cameras",
                destination="video_wall",
                purpose="video-wall-feed",
            )
        ],
        source=BindingSource.OPERATOR,
        partition="cctv",
    )
    twin.store_binding(binding)
    if activate_patrol:
        twin.activate_binding("perimeter-watch")
    return twin

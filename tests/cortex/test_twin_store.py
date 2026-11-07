"""Integration tests for Cortex bitemporal twin store (PostgreSQL)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib

from s3m_core.memory.knowledge_graph import S3MKnowledgeGraph

_twin_models = importlib.import_module("src.cortex.twin_store.models")
_twin_postgres = importlib.import_module("src.cortex.twin_store.postgres")
_twin_adapter = importlib.import_module("src.cortex.twin_store.knowledge_adapter")

EdgeRecord = _twin_models.EdgeRecord
NodeRecord = _twin_models.NodeRecord
SnapshotSource = _twin_models.SnapshotSource
PostgresTwinStore = _twin_postgres.PostgresTwinStore
TwinStoreKnowledgeAdapter = _twin_adapter.TwinStoreKnowledgeAdapter

pytest.importorskip("psycopg")

_T0 = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
_T1 = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
_T2 = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
_T3 = datetime(2025, 7, 1, 12, 0, tzinfo=timezone.utc)

_SOURCE = SnapshotSource(name="cortex_scanner", trust="high")


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _postgres_skip_reason() -> str | None:
    if not _docker_available():
        return "Docker is not available; skipping PostgreSQL twin store integration tests"
    return None


@pytest.fixture(scope="module")
def twin_store():
    reason = _postgres_skip_reason()
    if reason:
        pytest.skip(reason)

    container_name = f"s3m-cortex-twin-test-{uuid.uuid4().hex[:8]}"
    port = "54329"
    conninfo = f"postgresql://postgres:postgres@127.0.0.1:{port}/postgres"

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            "-e",
            "POSTGRES_PASSWORD=postgres",
            "-p",
            f"{port}:5432",
            "postgres:16-alpine",
        ],
        check=True,
        capture_output=True,
    )

    deadline = time.time() + 60
    ready = False
    while time.time() < deadline:
        probe = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "pg_isready",
                "-U",
                "postgres",
            ],
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            ready = True
            break
        time.sleep(1)

    if not ready:
        subprocess.run(["docker", "rm", "-f", container_name], check=False)
        pytest.skip("PostgreSQL test container failed to become ready within 60s")

    store = PostgresTwinStore(conninfo)
    try:
        store.apply_migrations()
    except Exception as exc:  # noqa: BLE001
        subprocess.run(["docker", "rm", "-f", container_name], check=False)
        pytest.skip(f"Could not apply twin migrations: {exc}")

    yield store

    subprocess.run(["docker", "rm", "-f", container_name], check=False)


def _cctv_fixture_nodes() -> list[NodeRecord]:
    return [
        NodeRecord("vpn_gateway", "system", {"role": "perimeter_vpn"}),
        NodeRecord("nvr", "system", {"role": "cctv_nvr"}),
        NodeRecord("cctv_cam_01", "system", {"role": "camera"}),
    ]


def _cctv_fixture_edges_v1() -> list[EdgeRecord]:
    return [
        EdgeRecord(
            "cctv_cam_01",
            "vpn_gateway",
            "connects_to",
            {"vlan": "cctv"},
            traversal_probability=0.95,
            required=True,
        ),
        EdgeRecord(
            "vpn_gateway",
            "nvr",
            "network_route",
            {"tunnel": "site_vpn"},
            traversal_probability=0.9,
            required=True,
            xiid_resource_id="xiid-vpn-nvr",
        ),
    ]


def _cctv_fixture_edges_v2() -> list[EdgeRecord]:
    """Post-hardening snapshot: VPN to NVR route removed."""
    return [
        EdgeRecord(
            "cctv_cam_01",
            "vpn_gateway",
            "connects_to",
            {"vlan": "cctv"},
            traversal_probability=0.95,
            required=True,
        ),
    ]


def test_update_preserves_history(twin_store: PostgresTwinStore) -> None:
    partition = "lab_segment_a"
    twin_store.upsert_snapshot(
        partition,
        [NodeRecord("sensor_a", "system", {"status": "online"})],
        [],
        _SOURCE,
        valid_from=_T0,
    )
    twin_store.upsert_snapshot(
        partition,
        [NodeRecord("sensor_a", "system", {"status": "degraded"})],
        [],
        _SOURCE,
        valid_from=_T2,
    )

    past = twin_store.graph_at(partition, _T1)
    present = twin_store.graph_at(partition, _T3)
    assert past.graph.nodes["sensor_a"]["attributes"]["status"] == "online"
    assert present.graph.nodes["sensor_a"]["attributes"]["status"] == "degraded"


def test_graph_at_returns_past_state_exactly(twin_store: PostgresTwinStore) -> None:
    partition = "lab_segment_b"
    twin_store.upsert_snapshot(
        partition,
        _cctv_fixture_nodes(),
        _cctv_fixture_edges_v1(),
        _SOURCE,
        valid_from=_T0,
    )
    twin_store.upsert_snapshot(
        partition,
        _cctv_fixture_nodes(),
        _cctv_fixture_edges_v2(),
        _SOURCE,
        valid_from=_T2,
    )

    before = twin_store.graph_at(partition, _T1)
    assert before.graph.has_edge("vpn_gateway", "nvr")

    after = twin_store.graph_at(partition, _T3)
    assert not after.graph.has_edge("vpn_gateway", "nvr")


def test_diff_shows_added_or_removed_edge(twin_store: PostgresTwinStore) -> None:
    partition = "lab_segment_c"
    twin_store.upsert_snapshot(
        partition,
        _cctv_fixture_nodes(),
        _cctv_fixture_edges_v1(),
        _SOURCE,
        valid_from=_T0,
    )
    twin_store.upsert_snapshot(
        partition,
        _cctv_fixture_nodes(),
        _cctv_fixture_edges_v2(),
        _SOURCE,
        valid_from=_T2,
    )

    delta = twin_store.diff(partition, _T1, _T3)
    assert ("vpn_gateway", "nvr", "network_route") in delta.removed_edges
    assert not delta.added_edges


def test_who_could_reach_cctv_vpn_nvr_path(twin_store: PostgresTwinStore) -> None:
    partition = "site_cctv_fixture"
    twin_store.upsert_snapshot(
        partition,
        _cctv_fixture_nodes(),
        _cctv_fixture_edges_v1(),
        _SOURCE,
        valid_from=_T0,
    )
    twin_store.upsert_snapshot(
        partition,
        _cctv_fixture_nodes(),
        _cctv_fixture_edges_v2(),
        _SOURCE,
        valid_from=_T2,
    )

    before_paths = twin_store.who_could_reach("nvr", _T1, partition_id=partition)
    assert before_paths
    vpn_path = next(
        (p for p in before_paths if "vpn_gateway" in p.node_path and p.target == "nvr"),
        None,
    )
    assert vpn_path is not None
    assert vpn_path.node_path[vpn_path.node_path.index("vpn_gateway") + 1] == "nvr"
    assert any(ev.get("kind") == "network_route" for ev in vpn_path.edge_evidence)

    after_paths = twin_store.who_could_reach("nvr", _T3, partition_id=partition)
    assert not any("vpn_gateway" in p.node_path for p in after_paths)


def test_knowledge_graph_adapter_loads_twin_snapshot(twin_store: PostgresTwinStore, tmp_path) -> None:
    partition = "site_cctv_fixture"
    twin_store.upsert_snapshot(
        partition,
        _cctv_fixture_nodes(),
        _cctv_fixture_edges_v1(),
        _SOURCE,
        valid_from=_T0,
    )

    kg_path = tmp_path / "knowledge_graph.json"
    kg = S3MKnowledgeGraph(storage_path=str(kg_path))
    adapter = TwinStoreKnowledgeAdapter(twin_store)
    adapter.load_snapshot(kg, partition, _T1)

    results = kg.query("site cctv nvr vpn")
    entity_ids = {item["entity_id"] for item in results if item.get("kind") == "entity"}
    assert any("nvr" in eid for eid in entity_ids)

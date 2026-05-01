"""Unit tests for packet routing into trainer assignments."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from src.pipeline import router as router_module
from src.pipeline.router import PacketRouter
from src.training.trainer_registry import TrainerRegistry


def test_route_packet_returns_manifest_and_updates_db(tmp_path: Path) -> None:
    db_conn = sqlite3.connect(":memory:")
    db_conn.row_factory = sqlite3.Row
    registry = TrainerRegistry(config_path=tmp_path / "tracks.yaml")
    router = PacketRouter(registry=registry, db_conn=db_conn)

    manifest = router.route_packet(
        packet_path=tmp_path / "packet-001.json",
        track="general",
        scenario="air_defense",
    )

    assert manifest["packet"].endswith("packet-001.json")
    assert manifest["track"] == "general"
    assert manifest["scenario"] == "air_defense"
    assert manifest["status"] == "routed"
    assert manifest["trainer_config"]["trainer_type"] == "causal_lm"

    row = db_conn.execute("SELECT status, trainer_assignment FROM packet_routes;").fetchone()
    assert row is not None
    assert row["status"] == "routed"
    assignment = json.loads(row["trainer_assignment"])
    assert assignment["batch_size"] == 8


def test_route_packet_writes_router_log(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "router.log"
    original_log_path = router_module._ROUTER_LOG_PATH
    router_module._ROUTER_LOG_PATH = log_path
    try:
        registry = TrainerRegistry(config_path=tmp_path / "tracks.yaml")
        router = PacketRouter(registry=registry, db_conn=None)
        router.route_packet(
            packet_path=tmp_path / "packet-xyz.json",
            track="cop_intel",
            scenario="isr_collection",
        )
    finally:
        router_module._ROUTER_LOG_PATH = original_log_path

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["status"] == "routed"
    assert entry["track"] == "cop_intel"


def test_route_batch_routes_all_packets(tmp_path: Path) -> None:
    registry = TrainerRegistry(config_path=tmp_path / "tracks.yaml")
    router = PacketRouter(registry=registry, db_conn=None)
    packets = [tmp_path / "p1.json", tmp_path / "p2.json", tmp_path / "p3.json"]

    manifests = router.route_batch(packets=packets, track="operations", scenario="mission_planning")

    assert len(manifests) == 3
    assert all(item["track"] == "operations" for item in manifests)
    assert all(item["status"] == "routed" for item in manifests)


def test_get_routing_stats_returns_aggregate_counts(tmp_path: Path) -> None:
    db_conn = sqlite3.connect(":memory:")
    db_conn.row_factory = sqlite3.Row
    registry = TrainerRegistry(config_path=tmp_path / "tracks.yaml")
    router = PacketRouter(registry=registry, db_conn=db_conn)

    router.route_packet(tmp_path / "a.json", "general", "scenario_1")
    router.route_packet(tmp_path / "b.json", "general", "scenario_1")
    router.route_packet(tmp_path / "c.json", "cop_intel", "scenario_2")

    stats = router.get_routing_stats()
    assert stats["total"] == 3
    assert stats["by_track"]["general"] == 2
    assert stats["by_track"]["cop_intel"] == 1
    assert stats["by_scenario"]["scenario_1"] == 2
    assert stats["by_status"]["routed"] == 3

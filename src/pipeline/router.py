"""Packet routing for assigning completed training packets to trainers.

Military/tactical context:
Reliable routing records ensure operators can audit which trainer consumed each
scenario packet, supporting mission replay and post-action accountability.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from src.training.trainer_registry import TrainerRegistry

_ROUTER_LOG_PATH = Path("/opt/s3m/logs/router.log")


class PacketRouter:
    """Route completed packets to trainer configurations."""

    def __init__(self, registry: TrainerRegistry, db_conn: Any = None) -> None:
        if not isinstance(registry, TrainerRegistry):
            raise TypeError("registry must be a TrainerRegistry instance")
        self._registry = registry
        self._db_conn = db_conn
        self._routing_history: list[dict[str, Any]] = []

    def route_packet(self, packet_path: Path, track: str, scenario: str) -> dict[str, Any]:
        """Route one packet and return the emitted routing manifest."""
        normalized_packet = self._normalize_packet_path(packet_path)
        track_key = self._normalize_route_key(track, "track")
        scenario_key = self._normalize_route_key(scenario, "scenario")
        trainer_config = self._registry.get_trainer_config(track_key, scenario_key)

        routed_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "packet": str(normalized_packet),
            "track": track_key,
            "scenario": scenario_key,
            "trainer_config": trainer_config,
            "routed_at": routed_at,
            "status": "routed",
        }

        self._update_packet_record(
            packet_path=normalized_packet,
            track=track_key,
            scenario=scenario_key,
            trainer_config=trainer_config,
            status="routed",
            routed_at=routed_at,
        )
        self._append_router_log(manifest)
        self._routing_history.append(dict(manifest))
        return manifest

    def route_batch(self, packets: list[Path], track: str, scenario: str) -> list[dict[str, Any]]:
        """Route a batch of packets under one track/scenario intent."""
        if not isinstance(packets, list):
            raise TypeError("packets must be a list of Path values")
        manifests: list[dict[str, Any]] = []
        for packet in packets:
            manifests.append(self.route_packet(packet, track, scenario))
        return manifests

    def get_routing_stats(self) -> dict[str, Any]:
        """Return routing counts aggregated by track, scenario, and status."""
        records = self._load_records_for_stats()
        by_track = Counter(record["track"] for record in records)
        by_scenario = Counter(record["scenario"] for record in records)
        by_status = Counter(record["status"] for record in records)
        return {
            "total": len(records),
            "by_track": dict(by_track),
            "by_scenario": dict(by_scenario),
            "by_status": dict(by_status),
        }

    @staticmethod
    def _normalize_packet_path(packet_path: Path) -> Path:
        normalized = Path(packet_path)
        if not str(normalized).strip():
            raise ValueError("packet_path cannot be empty")
        return normalized

    @staticmethod
    def _normalize_route_key(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError(f"{field_name} cannot be empty")
        return normalized

    def _update_packet_record(
        self,
        *,
        packet_path: Path,
        track: str,
        scenario: str,
        trainer_config: dict[str, Any],
        status: str,
        routed_at: str,
    ) -> None:
        if self._db_conn is None:
            return
        payload = json.dumps(trainer_config, ensure_ascii=True, sort_keys=True)
        cursor = self._db_conn.cursor() if hasattr(self._db_conn, "cursor") else self._db_conn
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS packet_routes (
                packet_path TEXT PRIMARY KEY,
                track TEXT NOT NULL,
                scenario TEXT NOT NULL,
                status TEXT NOT NULL,
                trainer_assignment TEXT NOT NULL,
                routed_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            INSERT INTO packet_routes (
                packet_path, track, scenario, status, trainer_assignment, routed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(packet_path) DO UPDATE SET
                track=excluded.track,
                scenario=excluded.scenario,
                status=excluded.status,
                trainer_assignment=excluded.trainer_assignment,
                routed_at=excluded.routed_at;
            """,
            (str(packet_path), track, scenario, status, payload, routed_at),
        )
        if hasattr(self._db_conn, "commit"):
            self._db_conn.commit()

    def _append_router_log(self, manifest: dict[str, Any]) -> None:
        _ROUTER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_line = json.dumps(manifest, ensure_ascii=True, sort_keys=True)
        with _ROUTER_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{log_line}\n")

    def _load_records_for_stats(self) -> list[dict[str, str]]:
        if self._db_conn is None:
            return [
                {
                    "track": str(record["track"]),
                    "scenario": str(record["scenario"]),
                    "status": str(record["status"]),
                }
                for record in self._routing_history
            ]

        cursor = self._db_conn.cursor() if hasattr(self._db_conn, "cursor") else self._db_conn
        cursor.execute(
            """
            SELECT track, scenario, status
            FROM packet_routes;
            """
        )
        rows = cursor.fetchall()
        records: list[dict[str, str]] = []
        for row in rows:
            if isinstance(row, dict):
                track = row.get("track", "")
                scenario = row.get("scenario", "")
                status = row.get("status", "")
            else:
                try:
                    track = row["track"]
                    scenario = row["scenario"]
                    status = row["status"]
                except Exception:
                    track = row[0]
                    scenario = row[1]
                    status = row[2]
            records.append(
                {
                    "track": str(track),
                    "scenario": str(scenario),
                    "status": str(status),
                }
            )
        return records

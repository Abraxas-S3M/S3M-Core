"""Scenario label validation gate for pre-training safety checks.

Military/tactical context:
This validator blocks training runs from drifting away from mission taxonomy by
verifying each scenario has the expected labels before data is admitted into the
training loop.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Any

import yaml


CACHE_TTL_SECONDS = 60.0
REGISTRATION_LOG_PATH = Path("/opt/s3m/logs/label_validator.log")
_CACHE_MISS = object()


_BUILTIN_DEFAULTS: dict[str, dict[str, Any]] = {
    "tracks": {
        "general": {
            "default_labels": [
                "intent",
                "location",
                "time_window",
                "asset",
                "priority",
                "confidence",
            ],
            "scenarios": {
                "convoy_brief": ["route", "threat_level", "asset", "time_window"],
                "checkpoint_screening": ["person", "vehicle", "risk_flag", "location"],
                "medevac_dispatch": ["casualty_count", "urgency", "pickup_zone", "asset"],
                "perimeter_watch": ["sector", "activity", "confidence", "time_window"],
                "route_recon": ["route", "obstacle", "threat_level", "location"],
                "supply_drop": ["asset", "cargo", "drop_zone", "eta"],
                "comms_degradation": ["network", "degradation_level", "time_window", "impact"],
                "civil_interaction": ["population_group", "location", "sentiment", "priority"],
                "training_rehearsal": ["objective", "unit", "readiness", "time_window"],
            },
        },
        "cop_intel": {
            "default_labels": [
                "subject",
                "indicator",
                "source",
                "confidence",
                "time_window",
                "location",
            ],
            "scenarios": {
                "pattern_of_life": ["subject", "movement_pattern", "time_window", "confidence"],
                "hvt_tracking": ["subject", "last_seen", "location", "confidence"],
                "signal_intercept": ["signal_type", "origin", "indicator", "time_window"],
                "geospatial_anomaly": ["location", "anomaly_type", "indicator", "priority"],
                "source_reliability": ["source", "reliability", "indicator", "confidence"],
                "imagery_triage": ["imagery_type", "object", "location", "confidence"],
                "network_link_analysis": ["subject", "link_type", "indicator", "confidence"],
                "watchlist_refresh": ["subject", "status", "indicator", "priority"],
                "threat_corroboration": ["indicator", "source", "confidence", "time_window"],
            },
        },
        "saudi_mod": {
            "default_labels": [
                "intent",
                "location",
                "time_window",
                "asset",
                "priority",
                "confidence",
                "arabic_text",
            ],
            "scenarios": {
                "gulf_port_security": ["location", "asset", "threat_level", "confidence"],
                "border_surveillance": ["sector", "activity", "indicator", "time_window"],
                "pilgrimage_crowd_safety": ["crowd_density", "location", "risk_flag", "priority"],
                "desert_convoy": ["route", "asset", "threat_level", "time_window"],
                "coastal_uav_intrusion": ["location", "uav_type", "indicator", "priority"],
                "critical_infrastructure": ["facility", "threat_level", "asset", "confidence"],
                "cross_border_smuggling": ["route", "cargo", "indicator", "source"],
                "oilfield_perimeter": ["facility", "sector", "activity", "time_window"],
                "bilingual_command_brief": ["arabic_text", "intent", "asset", "priority"],
                "rapid_response_qrf": ["unit", "objective", "location", "eta"],
            },
        },
        "operations": {
            "default_labels": [
                "objective",
                "location",
                "time_window",
                "unit",
                "priority",
                "status",
            ],
            "scenarios": {
                "mission_planning": ["objective", "unit", "location", "time_window"],
                "fires_deconfliction": ["unit", "fires_zone", "time_window", "priority"],
                "cas_request": ["asset", "target_type", "location", "urgency"],
                "battle_damage_assessment": ["target", "damage_level", "confidence", "time_window"],
                "force_rotation": ["unit", "relief_unit", "location", "eta"],
                "logistics_resupply": ["unit", "cargo", "route", "eta"],
                "contingency_branch": ["objective", "trigger", "unit", "priority"],
                "tactical_withdrawal": ["unit", "route", "threat_level", "time_window"],
                "command_post_jump": ["unit", "new_location", "time_window", "status"],
            },
        },
    }
}


class LabelValidator:
    """Thread-safe scenario label validator with DB+config fallback behavior."""

    def __init__(self, db_conn: Any, config_path: Path = Path("configs/labels.yaml")) -> None:
        self._db_conn = db_conn
        self._db_available = db_conn is not None
        self._config_path = Path(config_path)
        self._lock = RLock()
        self._cache: dict[str, tuple[float, Any]] = {}
        self._logger = logging.getLogger("s3m.db.label_validator")
        self._registration_logger = logging.getLogger("s3m.db.label_validator.registration")
        self._configure_registration_logger()
        self._scenario_defaults, self._track_defaults = self._load_defaults()
        if self._db_available:
            self._ensure_table_locked()

    def validate_scenario(self, track: str, scenario: str) -> bool:
        """Validate/auto-register a scenario before training begins."""
        normalized = self._normalize_track_scenario(track, scenario)
        if normalized is None:
            self._logger.info(
                "Scenario validation failed due to invalid input track=%r scenario=%r",
                track,
                scenario,
            )
            return False
        track_name, scenario_name = normalized

        with self._lock:
            existing = self._get_scenario_record_locked(track_name, scenario_name)
            if existing is not None:
                now = self._utcnow_iso()
                next_use_count = int(existing.get("use_count", 0)) + 1
                self._update_usage_locked(track_name, scenario_name, next_use_count, now)
                updated = dict(existing)
                updated["use_count"] = next_use_count
                updated["last_used_at"] = now
                self._set_cache_locked(self._record_cache_key(track_name, scenario_name), updated)
                self._logger.info(
                    "Validated scenario track=%s scenario=%s existing=True db_available=%s",
                    track_name,
                    scenario_name,
                    self._db_available,
                )
                return True

            self.register_scenario(track_name, scenario_name)
            self._logger.info(
                "Validated scenario track=%s scenario=%s existing=False db_available=%s",
                track_name,
                scenario_name,
                self._db_available,
            )
            return True

    def register_scenario(
        self, track: str, scenario: str, labels: list[str] | None = None
    ) -> dict[str, Any]:
        """Register an unexpected scenario, using track defaults when needed."""
        normalized = self._normalize_track_scenario(track, scenario)
        if normalized is None:
            return {}
        track_name, scenario_name = normalized
        requested_labels = self._normalize_label_list(labels or [])

        with self._lock:
            default_labels = self._default_labels_for_locked(track_name, scenario_name)
            merged_labels = self._merge_labels(default_labels, requested_labels)
            now = self._utcnow_iso()
            record: dict[str, Any] = {
                "track": track_name,
                "scenario": scenario_name,
                "labels": merged_labels,
                "use_count": 1,
                "created_at": now,
                "last_used_at": now,
            }

            if self._db_available:
                self._ensure_table_locked()
                labels_json = json.dumps(merged_labels, ensure_ascii=True)
                cursor = self._safe_db_execute_locked(
                    """
                    INSERT INTO scenarios (track, scenario, labels, use_count, created_at, last_used_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(track, scenario) DO UPDATE SET
                        labels = excluded.labels,
                        use_count = scenarios.use_count + 1,
                        last_used_at = excluded.last_used_at;
                    """,
                    (track_name, scenario_name, labels_json, 1, now, now),
                    commit=True,
                )
                if cursor is not None:
                    stored = self._safe_db_execute_locked(
                        """
                        SELECT track, scenario, labels, use_count, created_at, last_used_at
                        FROM scenarios
                        WHERE track = ? AND scenario = ?;
                        """,
                        (track_name, scenario_name),
                        fetchone=True,
                    )
                    parsed = self._row_to_record(stored)
                    if parsed is not None:
                        record = parsed

            self._set_cache_locked(self._record_cache_key(track_name, scenario_name), record)
            self._cache.pop("all_scenarios", None)
            self._registration_logger.warning(
                "Registered new scenario track=%s scenario=%s labels=%s",
                track_name,
                scenario_name,
                ",".join(merged_labels),
            )
            self._logger.warning(
                "Registered new scenario track=%s scenario=%s db_available=%s",
                track_name,
                scenario_name,
                self._db_available,
            )
            return deepcopy(record)

    def get_labels(self, track: str, scenario: str) -> list[str]:
        """Return labels from DB when possible, otherwise config defaults."""
        normalized = self._normalize_track_scenario(track, scenario)
        if normalized is None:
            return []
        track_name, scenario_name = normalized

        with self._lock:
            record = self._get_scenario_record_locked(track_name, scenario_name)
            if record is not None:
                return list(record.get("labels", []))
            return self._default_labels_for_locked(track_name, scenario_name)

    def validate_example(
        self, example: dict[str, Any], track: str, scenario: str
    ) -> tuple[bool, list[str]]:
        """Check that all required labels are present in one training example."""
        required_labels = self.get_labels(track, scenario)
        if not isinstance(example, dict):
            return (False, required_labels)

        missing: list[str] = []
        for label in required_labels:
            if label not in example or example.get(label) is None:
                missing.append(label)
        return (len(missing) == 0, missing)

    def get_all_scenarios(self) -> dict[str, dict[str, list[str]]]:
        """Return all known scenarios as track -> scenario -> labels."""
        with self._lock:
            cached = self._get_cache_locked("all_scenarios")
            if cached is not _CACHE_MISS:
                return cached

            all_scenarios: dict[str, dict[str, list[str]]] = {
                track: {scenario: list(labels) for scenario, labels in scenarios.items()}
                for track, scenarios in self._scenario_defaults.items()
            }
            if self._db_available:
                rows = self._safe_db_execute_locked(
                    "SELECT track, scenario, labels, use_count, created_at, last_used_at FROM scenarios;",
                    fetchall=True,
                )
                if isinstance(rows, list):
                    for row in rows:
                        record = self._row_to_record(row)
                        if record is None:
                            continue
                        all_scenarios.setdefault(record["track"], {})[record["scenario"]] = list(
                            record["labels"]
                        )

            self._set_cache_locked("all_scenarios", all_scenarios)
            return deepcopy(all_scenarios)

    def _load_defaults(self) -> tuple[dict[str, dict[str, list[str]]], dict[str, list[str]]]:
        payload: Any = {}
        try:
            if self._config_path.exists():
                payload = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._logger.warning("Failed loading label defaults from %s: %s", self._config_path, exc)
            payload = {}

        scenario_defaults, track_defaults = self._parse_defaults_payload(payload)
        if scenario_defaults or track_defaults:
            return scenario_defaults, track_defaults
        return self._parse_defaults_payload(_BUILTIN_DEFAULTS)

    def _parse_defaults_payload(
        self, payload: Any
    ) -> tuple[dict[str, dict[str, list[str]]], dict[str, list[str]]]:
        if not isinstance(payload, dict):
            return {}, {}

        root = payload.get("tracks")
        track_payloads = root if isinstance(root, dict) else payload

        scenario_defaults: dict[str, dict[str, list[str]]] = {}
        track_defaults: dict[str, list[str]] = {}

        for raw_track, raw_track_payload in track_payloads.items():
            if not isinstance(raw_track, str):
                continue
            track_name = raw_track.strip()
            if not track_name:
                continue

            if not isinstance(raw_track_payload, dict):
                continue

            default_labels = self._normalize_label_list(
                raw_track_payload.get("default_labels", raw_track_payload.get("defaults", []))
            )
            scenarios_node = raw_track_payload.get("scenarios")
            if isinstance(scenarios_node, dict):
                scenario_node = scenarios_node
            else:
                scenario_node = raw_track_payload

            track_scenarios: dict[str, list[str]] = {}
            for raw_scenario, raw_labels in scenario_node.items():
                if raw_scenario in {"default_labels", "defaults", "scenarios"}:
                    continue
                if not isinstance(raw_scenario, str):
                    continue
                scenario_name = raw_scenario.strip()
                if not scenario_name:
                    continue

                labels = self._normalize_label_list(raw_labels)
                if not labels and isinstance(raw_labels, dict):
                    labels = self._normalize_label_list(raw_labels.get("labels", []))
                if not labels:
                    labels = list(default_labels)
                if labels:
                    track_scenarios[scenario_name] = labels

            if track_scenarios:
                scenario_defaults[track_name] = track_scenarios
            if default_labels:
                track_defaults[track_name] = list(default_labels)
            elif track_scenarios:
                first_labels = next(iter(track_scenarios.values()))
                track_defaults[track_name] = list(first_labels)

        return scenario_defaults, track_defaults

    def _ensure_table_locked(self) -> None:
        if not self._db_available:
            return
        self._safe_db_execute_locked(
            """
            CREATE TABLE IF NOT EXISTS scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track TEXT NOT NULL,
                scenario TEXT NOT NULL,
                labels TEXT NOT NULL,
                use_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                UNIQUE(track, scenario)
            );
            """,
            commit=True,
        )

    def _get_scenario_record_locked(self, track: str, scenario: str) -> dict[str, Any] | None:
        cache_key = self._record_cache_key(track, scenario)
        cached = self._get_cache_locked(cache_key)
        if cached is not _CACHE_MISS:
            return cached

        if not self._db_available:
            self._set_cache_locked(cache_key, None)
            return None

        row = self._safe_db_execute_locked(
            """
            SELECT track, scenario, labels, use_count, created_at, last_used_at
            FROM scenarios
            WHERE track = ? AND scenario = ?;
            """,
            (track, scenario),
            fetchone=True,
        )
        record = self._row_to_record(row)
        self._set_cache_locked(cache_key, record)
        return record

    def _update_usage_locked(
        self, track: str, scenario: str, use_count: int, timestamp_iso: str
    ) -> None:
        if not self._db_available:
            return
        self._safe_db_execute_locked(
            """
            UPDATE scenarios
            SET use_count = ?, last_used_at = ?
            WHERE track = ? AND scenario = ?;
            """,
            (int(use_count), timestamp_iso, track, scenario),
            commit=True,
        )
        self._cache.pop("all_scenarios", None)

    def _safe_db_execute_locked(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
        *,
        fetchone: bool = False,
        fetchall: bool = False,
        commit: bool = False,
    ) -> Any:
        if not self._db_available or self._db_conn is None:
            return None
        try:
            cursor = self._db_conn.execute(sql, params)
            if commit:
                self._db_conn.commit()
            if fetchone:
                return cursor.fetchone()
            if fetchall:
                return cursor.fetchall()
            return cursor
        except Exception as exc:
            self._db_available = False
            self._logger.warning(
                "Label validator database unavailable, switching to config-only mode: %s",
                exc,
            )
            return None

    def _default_labels_for_locked(self, track: str, scenario: str) -> list[str]:
        track_scenarios = self._scenario_defaults.get(track, {})
        if scenario in track_scenarios:
            return list(track_scenarios[scenario])
        if track in self._track_defaults:
            return list(self._track_defaults[track])
        if track_scenarios:
            return list(next(iter(track_scenarios.values())))
        return []

    def _get_cache_locked(self, key: str) -> Any:
        item = self._cache.get(key)
        if item is None:
            return _CACHE_MISS
        inserted_at, value = item
        if monotonic() - inserted_at > CACHE_TTL_SECONDS:
            self._cache.pop(key, None)
            return _CACHE_MISS
        return deepcopy(value)

    def _set_cache_locked(self, key: str, value: Any) -> None:
        self._cache[key] = (monotonic(), deepcopy(value))

    @staticmethod
    def _normalize_label_list(raw_labels: Any) -> list[str]:
        if isinstance(raw_labels, str):
            labels = [raw_labels]
        elif isinstance(raw_labels, (list, tuple, set)):
            labels = [str(item) for item in raw_labels]
        else:
            return []

        cleaned: list[str] = []
        seen: set[str] = set()
        for raw_label in labels:
            label = str(raw_label).strip()
            if not label or label in seen:
                continue
            seen.add(label)
            cleaned.append(label)
        return cleaned

    @staticmethod
    def _merge_labels(defaults: list[str], provided: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for label in list(defaults) + list(provided):
            normalized = str(label).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged

    @staticmethod
    def _row_to_record(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None

        if hasattr(row, "keys"):
            payload = {str(key): row[key] for key in row.keys()}  # sqlite3.Row-compatible
        elif isinstance(row, dict):
            payload = dict(row)
        elif isinstance(row, (tuple, list)) and len(row) >= 6:
            payload = {
                "track": row[0],
                "scenario": row[1],
                "labels": row[2],
                "use_count": row[3],
                "created_at": row[4],
                "last_used_at": row[5],
            }
        else:
            return None

        raw_labels = payload.get("labels", [])
        if isinstance(raw_labels, str):
            try:
                parsed = json.loads(raw_labels)
            except json.JSONDecodeError:
                parsed = []
        else:
            parsed = raw_labels

        labels = LabelValidator._normalize_label_list(parsed)
        if not labels:
            return None

        return {
            "track": str(payload.get("track", "")).strip(),
            "scenario": str(payload.get("scenario", "")).strip(),
            "labels": labels,
            "use_count": int(payload.get("use_count", 0)),
            "created_at": str(payload.get("created_at", "")),
            "last_used_at": str(payload.get("last_used_at", "")),
        }

    def _configure_registration_logger(self) -> None:
        self._registration_logger.setLevel(logging.WARNING)
        for handler in self._registration_logger.handlers:
            if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == REGISTRATION_LOG_PATH:
                return
        try:
            REGISTRATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(REGISTRATION_LOG_PATH, encoding="utf-8")
            file_handler.setLevel(logging.WARNING)
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
            )
            self._registration_logger.addHandler(file_handler)
        except Exception as exc:
            self._logger.warning(
                "Could not initialize registration log file %s: %s",
                REGISTRATION_LOG_PATH,
                exc,
            )

    @staticmethod
    def _record_cache_key(track: str, scenario: str) -> str:
        return f"record:{track}:{scenario}"

    @staticmethod
    def _normalize_track_scenario(track: str, scenario: str) -> tuple[str, str] | None:
        if not isinstance(track, str) or not isinstance(scenario, str):
            return None
        track_name = track.strip()
        scenario_name = scenario.strip()
        if not track_name or not scenario_name:
            return None
        return track_name, scenario_name

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

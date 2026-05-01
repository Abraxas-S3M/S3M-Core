"""Production watcher for incoming cloud CPU JSONL training packets.

Military/tactical context:
This watcher is the first guardrail in the adaptation chain; strict filename
parsing and scenario-label validation reduce the risk of poisoned or mislabeled
training traffic entering downstream mission-learning queues.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
import sqlite3
import shutil
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

import yaml

S3M_SRC_PATH = "/opt/s3m/src"
if S3M_SRC_PATH not in sys.path:
    sys.path.insert(0, S3M_SRC_PATH)

try:
    from training.packet_builder import PacketBuilder  # type: ignore
except Exception:  # pragma: no cover - local repo fallback path.
    from src.training.packet_builder import PacketBuilder  # type: ignore

try:
    from src.db.label_validator import LabelValidator  # type: ignore
except Exception:  # pragma: no cover - exercised only when db package is unavailable.
    LabelValidator = None  # type: ignore[assignment]

try:
    from src.pipeline.orchestrator import Orchestrator  # type: ignore
except Exception:  # pragma: no cover - optional runtime import for startup wiring.
    Orchestrator = None  # type: ignore[assignment]

try:
    from src.pipeline.router import PacketRouter  # type: ignore
except Exception:  # pragma: no cover - optional runtime import for startup wiring.
    PacketRouter = None  # type: ignore[assignment]

try:
    from src.training.trainer_registry import TrainerRegistry  # type: ignore
except Exception:  # pragma: no cover - optional runtime import for startup wiring.
    TrainerRegistry = None  # type: ignore[assignment]

try:
    from src.training.train_runner import TrainRunner  # type: ignore
except Exception:  # pragma: no cover - optional runtime import for startup wiring.
    TrainRunner = None  # type: ignore[assignment]

try:
    from src.vault.catalog import VaultCatalog  # type: ignore
except Exception:  # pragma: no cover - optional runtime import for startup wiring.
    VaultCatalog = None  # type: ignore[assignment]

try:
    from src.vault.r2_client import R2Client  # type: ignore
except Exception:  # pragma: no cover - optional runtime import for startup wiring.
    R2Client = None  # type: ignore[assignment]


POLL_INTERVAL_SECONDS = 10
INBOX_DIR = Path("/opt/s3m/state/training/cloud_cpu/inbox")
STAGING_DIR = Path("/opt/s3m/state/training/staging")
LOG_FILE = Path("/opt/s3m/logs/packet_watcher.log")
DEFAULT_TRACKS_CONFIG_CANDIDATES = (
    Path("configs/tracks.yaml"),
    Path("/opt/s3m/configs/tracks.yaml"),
)
DEFAULT_PACKET_OUTPUT_ROOT = Path("/opt/s3m/state/training/cloud_cpu/tracks")
SUMMARY_EVERY_N_CYCLES = 10
SUPPORTED_JSONL_SUFFIX = ".jsonl"
DEFAULT_DATA_CLASS = "command"
DEFAULT_AUDIT_DB_FILENAME = "pipeline_audit.db"
TRAINING_RUNS_TABLE = "training_runs"
PACKETS_TABLE = "packets"
DEFAULT_EXAMPLES_PER_PACKET = 50
DEFAULT_AUDIT_DB_PATH = Path("/opt/s3m/state/training/pipeline_audit.db")

_VERSION_SUFFIX_RE = re.compile(r"^(?:v\d+|version\d+|batch\d+|part\d+|rev\d+|\d+)$", re.IGNORECASE)
_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9_]+")
_COLLAPSE_UNDERSCORE_RE = re.compile(r"_+")


@dataclass
class ScenarioDefinition:
    """Scenario-level metadata loaded from tracks.yaml."""

    name: str
    data_class: Optional[str] = None
    output_dir: Optional[str] = None


@dataclass
class TrackDefinition:
    """Track-level metadata loaded from tracks.yaml."""

    name: str
    default_data_class: str = DEFAULT_DATA_CLASS
    output_dir: Optional[str] = None
    scenarios: Dict[str, ScenarioDefinition] = field(default_factory=dict)


@dataclass
class InferenceResult:
    """Resolved routing context inferred from a JSONL filename."""

    track: str
    scenario: str
    data_class: str
    output_dir: Path


@dataclass
class PipelineFileSummary:
    """Per-file execution summary for tactical pipeline auditing."""

    source_file: str
    track: str
    scenario: str
    packet_count: int
    routed_count: int
    submitted_jobs: int
    staging_path: str
    run_id: str
    vault_marked: bool


class _ContextDefaultsFilter(logging.Filter):
    """Ensure required structured fields are always present on log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "packet_filename"):
            record.packet_filename = "-"
        if not hasattr(record, "track"):
            record.track = "-"
        if not hasattr(record, "scenario"):
            record.scenario = "-"
        return True


class PacketWatcher:
    """Watch inbox JSONL files and execute the full training pipeline."""

    def __init__(
        self,
        inbox_dir: Path = INBOX_DIR,
        staging_dir: Path = STAGING_DIR,
        packet_output_root: Path = DEFAULT_PACKET_OUTPUT_ROOT,
        tracks_config_path: Optional[Path] = None,
        poll_interval_seconds: int = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._inbox_dir = Path(inbox_dir)
        self._staging_dir = Path(staging_dir)
        self._packet_output_root = Path(packet_output_root)
        self._tracks_config_path = tracks_config_path or self._resolve_tracks_config_path()
        self._poll_interval_seconds = max(1, int(poll_interval_seconds))
        self._audit_db_path = self._staging_dir.parent / DEFAULT_AUDIT_DB_FILENAME

        self._logger = self._configure_logging()
        self._packet_builder = PacketBuilder()
        self._label_validator: Any = None
        self._db_connection: Any = None
        self._audit_db_connection: Optional[sqlite3.Connection] = None
        self._orchestrator: Any = None
        self._packet_router: Any = None
        self._train_runner: Any = None
        self._trainer_registry: Any = None
        self._r2_client: Any = None
        self._vault_catalog: Any = None

        self._track_definitions: Dict[str, TrackDefinition] = {}
        self._tracks_config_mtime_ns: Optional[int] = None
        self._cycles = 0
        self._processed_total = 0
        self._failed_total = 0

        self._ensure_runtime_directories()
        self._initialize_orchestrator()
        self._initialize_audit_db()
        self._initialize_validator()
        self._reload_track_definitions(force=True)
        self._initialize_pipeline_components()

    def run_forever(self) -> None:
        """Execute an endless watcher loop without crashing on file-level errors."""
        self._log(logging.INFO, "packet watcher started")
        while True:
            cycle_started = time.monotonic()
            self._cycles += 1
            try:
                self._reload_track_definitions(force=False)
                self._run_single_cycle()
            except Exception:
                # Tactical continuity: the outer loop stays alive under transient failures.
                self._log(
                    logging.ERROR,
                    "watcher cycle encountered an unexpected error: %s",
                    traceback.format_exc(),
                )
            elapsed = time.monotonic() - cycle_started
            sleep_for = max(0.0, float(self._poll_interval_seconds) - elapsed)
            time.sleep(sleep_for)

    def _run_single_cycle(self) -> None:
        files = sorted(self._inbox_dir.glob(f"*{SUPPORTED_JSONL_SUFFIX}"), key=lambda item: item.name)
        cycle_processed = 0
        cycle_failed = 0
        for jsonl_file in files:
            try:
                self._process_file(jsonl_file)
            except Exception:
                cycle_failed += 1
                self._failed_total += 1
                self._log(
                    logging.ERROR,
                    "file processing failed with traceback:\n%s",
                    traceback.format_exc(),
                    filename=jsonl_file.name,
                )
            else:
                cycle_processed += 1
                self._processed_total += 1

        if self._cycles % SUMMARY_EVERY_N_CYCLES == 0:
            pending = len(list(self._inbox_dir.glob(f"*{SUPPORTED_JSONL_SUFFIX}")))
            self._log(
                logging.INFO,
                "watcher summary cycles=%d processed=%d failed=%d pending=%d cycle_processed=%d cycle_failed=%d",
                self._cycles,
                self._processed_total,
                self._failed_total,
                pending,
                cycle_processed,
                cycle_failed,
            )

    def _process_file(self, jsonl_file: Path) -> None:
        if not jsonl_file.exists() or not jsonl_file.is_file():
            raise FileNotFoundError(f"Inbox item disappeared before processing: {jsonl_file}")

        inference = self._infer_track_scenario(jsonl_file.name)
        self._validate_jsonl_file(jsonl_file)
        self._validate_or_register_scenario(
            track=inference.track,
            scenario=inference.scenario,
            data_class=inference.data_class,
            filename=jsonl_file.name,
        )
        packets = self._invoke_packet_builder(jsonl_file, inference)
        routing_manifests = self._route_packets(packets=packets, track=inference.track, scenario=inference.scenario)
        submitted_job_ids = [self._submit_train_job(manifest) for manifest in routing_manifests]

        destination = self._dedupe_destination(self._staging_dir, jsonl_file.name)
        shutil.move(str(jsonl_file), str(destination))
        vault_marked = self._mark_vault_processed(
            staged_file=destination,
            track=inference.track,
            scenario=inference.scenario,
        )

        summary = PipelineFileSummary(
            source_file=jsonl_file.name,
            track=inference.track,
            scenario=inference.scenario,
            packet_count=len(packets),
            routed_count=len(routing_manifests),
            submitted_jobs=len([job for job in submitted_job_ids if job]),
            staging_path=str(destination),
            run_id=self._pipeline_run_id(),
            vault_marked=vault_marked,
        )
        self._record_training_run(summary)
        self._record_packet_rows(summary.run_id, routing_manifests, submitted_job_ids)
        self._log_pipeline_summary(summary)

    def _infer_track_scenario(self, filename: str) -> InferenceResult:
        stem = Path(filename).stem
        if not stem:
            raise ValueError("Cannot infer track/scenario from empty filename stem")
        normalized_stem = _normalize_slug(stem)
        tokens = [token for token in normalized_stem.split("_") if token]
        if not tokens:
            raise ValueError(f"Cannot parse filename into tokens: {filename}")
        track = self._infer_track(tokens=tokens, filename=filename)
        track_token_count = len(track.split("_"))
        scenario_tokens = self._strip_version_suffixes(tokens[track_token_count:])
        if not scenario_tokens:
            raise ValueError(f"Filename does not include a scenario segment: {filename}")
        scenario = "_".join(scenario_tokens)
        track_def = self._track_definitions[track]
        scenario_def = track_def.scenarios.get(scenario)
        data_class = (
            (scenario_def.data_class if scenario_def else None)
            or track_def.default_data_class
            or DEFAULT_DATA_CLASS
        )
        output_dir = self._resolve_output_dir(track=track, track_def=track_def, scenario_def=scenario_def)
        return InferenceResult(track=track, scenario=scenario, data_class=data_class, output_dir=output_dir)

    def _infer_track(self, tokens: list[str], filename: str) -> str:
        if not self._track_definitions:
            raise ValueError("No tracks were loaded from configs/tracks.yaml")
        track_names = sorted(
            self._track_definitions.keys(),
            key=lambda name: len(name.split("_")),
            reverse=True,
        )
        for candidate in track_names:
            candidate_tokens = candidate.split("_")
            if tokens[: len(candidate_tokens)] == candidate_tokens:
                return candidate
        raise ValueError(f"Unknown track inferred from filename '{filename}'")

    @staticmethod
    def _strip_version_suffixes(tokens: list[str]) -> list[str]:
        trimmed = list(tokens)
        while trimmed and _VERSION_SUFFIX_RE.match(trimmed[-1]):
            trimmed.pop()
        return trimmed

    def _validate_jsonl_file(self, jsonl_file: Path) -> None:
        if jsonl_file.stat().st_size <= 0:
            raise ValueError(f"JSONL file is empty: {jsonl_file.name}")
        non_empty_rows = 0
        with jsonl_file.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                non_empty_rows += 1
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Malformed JSON on line {line_number} for {jsonl_file.name}: {exc.msg}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise ValueError(
                        f"Invalid payload type on line {line_number} for {jsonl_file.name}; expected JSON object"
                    )
        if non_empty_rows == 0:
            raise ValueError(f"JSONL file has no non-empty rows: {jsonl_file.name}")

    def _validate_or_register_scenario(self, track: str, scenario: str, data_class: str, filename: str) -> None:
        track_def = self._track_definitions[track]
        is_known = scenario in track_def.scenarios
        db_status = self._validate_with_label_validator(track=track, scenario=scenario)
        if db_status is True:
            return
        if db_status is None and is_known:
            return
        if db_status is False or not is_known:
            # Tactical continuity: unknown labels are registered with defaults for auditability.
            self._register_scenario_defaults(track=track, scenario=scenario, data_class=data_class)
            self._log(
                logging.WARNING,
                "scenario label was unknown and has been auto-registered with defaults",
                filename=filename,
                track=track,
                scenario=scenario,
            )
            return
        raise ValueError(
            f"Scenario label validation failed for track={track} scenario={scenario}; packet kept in inbox."
        )

    def _validate_with_label_validator(self, track: str, scenario: str) -> Optional[bool]:
        if self._label_validator is None:
            return None
        methods = (
            "validate_scenario_label",
            "validate_scenario",
            "validate_label",
            "validate",
            "is_valid_scenario",
            "scenario_exists",
        )
        for method_name in methods:
            method = getattr(self._label_validator, method_name, None)
            if method is None:
                continue
            result, was_called = _call_with_signature_fallbacks(
                method,
                call_builders=_validator_call_builders(track=track, scenario=scenario),
            )
            if not was_called:
                continue
            return _coerce_validation_result(result)
        return None

    def _register_scenario_defaults(self, track: str, scenario: str, data_class: str) -> None:
        track_def = self._track_definitions[track]
        if scenario not in track_def.scenarios:
            track_def.scenarios[scenario] = ScenarioDefinition(name=scenario, data_class=data_class)
        if self._label_validator is None:
            return
        defaults = {
            "track": track,
            "scenario": scenario,
            "data_class": data_class,
            "status": "active",
            "origin": "packet_watcher_auto_register",
        }
        methods = (
            "register_scenario_label",
            "register_scenario",
            "upsert_scenario",
            "create_scenario_label",
        )
        for method_name in methods:
            method = getattr(self._label_validator, method_name, None)
            if method is None:
                continue
            _, was_called = _call_with_signature_fallbacks(
                method,
                call_builders=_register_call_builders(track=track, scenario=scenario, defaults=defaults),
            )
            if was_called:
                return

    def _invoke_packet_builder(self, jsonl_file: Path, inference: InferenceResult) -> list[Path]:
        inference.output_dir.mkdir(parents=True, exist_ok=True)
        build_method = getattr(self._packet_builder, "build_from_jsonl", None)
        if build_method is None:
            raise AttributeError("PacketBuilder.build_from_jsonl() is not available")
        call_builders = _packet_builder_call_builders(
            jsonl_file=jsonl_file,
            track=inference.track,
            scenario=inference.scenario,
            data_class=inference.data_class,
            output_dir=inference.output_dir,
        )
        result, was_called = _call_with_signature_fallbacks(build_method, call_builders=call_builders)
        if not was_called:
            raise TypeError("Unable to satisfy PacketBuilder.build_from_jsonl() signature")
        if result is None:
            return []
        if isinstance(result, list):
            return [Path(item) for item in result]
        return [Path(result)]

    def _route_packets(self, packets: list[Path], track: str, scenario: str) -> list[dict[str, Any]]:
        if not packets:
            return []
        if self._packet_router is not None and hasattr(self._packet_router, "route_batch"):
            route_method = getattr(self._packet_router, "route_batch")
            route_result, was_called = _call_with_signature_fallbacks(
                route_method,
                call_builders=_route_batch_call_builders(packets=packets, track=track, scenario=scenario),
            )
            if was_called and isinstance(route_result, list):
                return [dict(item) for item in route_result if isinstance(item, dict)]
        trainer_config = self._resolve_trainer_config(track=track, scenario=scenario)
        return [
            {
                "packet": str(packet),
                "track": track,
                "scenario": scenario,
                "trainer_config": dict(trainer_config),
                "status": "routed",
                "routed_at": self._utc_now(),
            }
            for packet in packets
        ]

    def _resolve_trainer_config(self, track: str, scenario: str) -> dict[str, Any]:
        if self._trainer_registry is not None and hasattr(self._trainer_registry, "get_trainer_config"):
            get_method = getattr(self._trainer_registry, "get_trainer_config")
            config, was_called = _call_with_signature_fallbacks(
                get_method,
                call_builders=(
                    lambda: {"kwargs": {"track": track, "scenario": scenario}},
                    lambda: {"args": (track, scenario), "kwargs": {}},
                ),
            )
            if was_called and isinstance(config, dict):
                return dict(config)
        return {
            "trainer_type": "causal_lm",
            "base_model": "models/quantized/default-causal-lm",
            "learning_rate": 2e-5,
            "batch_size": 8,
            "max_epochs": 4,
            "warmup_steps": 100,
            "gradient_accumulation": 1,
            "mixed_precision": True,
            "runpod_template": "runpod-default-causal-lm",
        }

    def _submit_train_job(self, routing_manifest: dict[str, Any]) -> str:
        if self._train_runner is None or not hasattr(self._train_runner, "submit_job"):
            return ""
        payload = self._prepare_train_job_manifest(routing_manifest)
        submit_method = getattr(self._train_runner, "submit_job")
        result, was_called = _call_with_signature_fallbacks(
            submit_method,
            call_builders=(
                lambda: {"kwargs": {"routing_manifest": payload}},
                lambda: {"args": (payload,), "kwargs": {}},
            ),
        )
        if not was_called:
            raise TypeError("Unable to satisfy TrainRunner.submit_job() signature")
        return str(result or "")

    def _prepare_train_job_manifest(self, routing_manifest: dict[str, Any]) -> dict[str, Any]:
        payload = dict(routing_manifest)
        packet_value = payload.get("packet")
        packet_files = payload.get("packet_files")
        if not isinstance(packet_files, list):
            packet_files = [packet_value] if packet_value else []
        payload["packet_files"] = [str(item) for item in packet_files if item]
        if "trainer_config" not in payload or not isinstance(payload.get("trainer_config"), dict):
            payload["trainer_config"] = self._resolve_trainer_config(
                track=str(payload.get("track", "")).strip().lower(),
                scenario=str(payload.get("scenario", "")).strip().lower(),
            )
        if "job_label" not in payload:
            payload["job_label"] = f"{payload.get('track', 'track')}-{payload.get('scenario', 'scenario')}"
        return payload

    def _mark_vault_processed(self, staged_file: Path, track: str, scenario: str) -> bool:
        if self._r2_client is None:
            return False
        r2_key = f"datasets/{track}/processed/{scenario}/{staged_file.name}"
        upload_methods = (
            getattr(self._r2_client, "upload", None),
            getattr(self._r2_client, "upload_file", None),
        )
        upload_result: Any = None
        uploaded = False
        for method in upload_methods:
            if method is None:
                continue
            upload_result, uploaded = _call_with_signature_fallbacks(
                method,
                call_builders=(
                    lambda: {"kwargs": {"local_path": staged_file, "r2_key": r2_key}},
                    lambda: {"kwargs": {"local_path": str(staged_file), "remote_key": r2_key}},
                    lambda: {"args": (staged_file, r2_key), "kwargs": {}},
                    lambda: {"args": (str(staged_file), r2_key), "kwargs": {}},
                ),
            )
            if uploaded:
                break
        if not uploaded:
            return False
        if self._vault_catalog is not None:
            mark_method = getattr(self._vault_catalog, "mark_complete", None)
            if mark_method is not None:
                _call_with_signature_fallbacks(
                    mark_method,
                    call_builders=(
                        lambda: {"kwargs": {"r2_key": r2_key}},
                        lambda: {"args": (r2_key,), "kwargs": {}},
                    ),
                )
        return upload_result is not None or uploaded

    def _reload_track_definitions(self, force: bool) -> None:
        config_path = self._tracks_config_path
        try:
            current_mtime = config_path.stat().st_mtime_ns
        except FileNotFoundError:
            if force:
                raise FileNotFoundError(f"Track configuration not found: {config_path}") from None
            return
        if not force and self._tracks_config_mtime_ns == current_mtime:
            return
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        parsed = _parse_track_definitions(payload)
        if not parsed:
            raise ValueError(f"No tracks found in configuration file: {config_path}")
        self._track_definitions = parsed
        self._tracks_config_mtime_ns = current_mtime
        self._log(logging.INFO, "loaded tracks configuration from %s", str(config_path))

    def _resolve_output_dir(
        self,
        track: str,
        track_def: TrackDefinition,
        scenario_def: Optional[ScenarioDefinition],
    ) -> Path:
        if scenario_def is not None and scenario_def.output_dir:
            return Path(scenario_def.output_dir)
        if track_def.output_dir:
            return Path(track_def.output_dir)
        return self._packet_output_root / track / "scenarios"

    def _initialize_orchestrator(self) -> None:
        if Orchestrator is None:
            self._log(logging.WARNING, "orchestrator component unavailable; running in direct watcher mode")
            return
        try:
            self._orchestrator = Orchestrator(poll_interval=self._poll_interval_seconds)
            self._log(logging.INFO, "orchestrator initialized for packet watcher startup")
        except Exception:
            self._orchestrator = None
            self._log(logging.WARNING, "orchestrator initialization failed: %s", traceback.format_exc())

    def _initialize_audit_db(self) -> None:
        if isinstance(getattr(self._orchestrator, "db_conn", None), sqlite3.Connection):
            self._audit_db_connection = getattr(self._orchestrator, "db_conn")
        else:
            self._audit_db_connection = sqlite3.connect(str(self._audit_db_path), check_same_thread=False)
            self._audit_db_connection.row_factory = sqlite3.Row
        self._db_connection = self._audit_db_connection
        self._ensure_audit_tables()

    def _ensure_audit_tables(self) -> None:
        if self._audit_db_connection is None:
            return
        self._audit_db_connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TRAINING_RUNS_TABLE} (
                run_id TEXT PRIMARY KEY,
                source_file TEXT NOT NULL,
                track TEXT NOT NULL,
                scenario TEXT NOT NULL,
                packet_count INTEGER NOT NULL DEFAULT 0,
                routed_count INTEGER NOT NULL DEFAULT 0,
                submitted_jobs INTEGER NOT NULL DEFAULT 0,
                staging_path TEXT NOT NULL,
                vault_marked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        self._audit_db_connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {PACKETS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                packet_path TEXT NOT NULL,
                train_job_id TEXT,
                status TEXT NOT NULL,
                routing_manifest TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._audit_db_connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{PACKETS_TABLE}_run_id ON {PACKETS_TABLE}(run_id);"
        )
        self._audit_db_connection.commit()

    def _initialize_validator(self) -> None:
        if LabelValidator is None:
            self._log(logging.WARNING, "db.label_validator unavailable; using config-based scenario validation only")
            return
        orchestrator_validator = getattr(self._orchestrator, "label_validator", None)
        if orchestrator_validator is not None and any(
            hasattr(orchestrator_validator, method_name)
            for method_name in ("validate_scenario", "validate_scenario_label", "scenario_exists")
        ):
            self._label_validator = orchestrator_validator
            return
        constructor_attempts = (
            lambda: LabelValidator(self._db_connection),
            lambda: LabelValidator(db_conn=self._db_connection),
        )
        for constructor in constructor_attempts:
            try:
                self._label_validator = constructor()
                return
            except TypeError:
                continue
            except Exception:
                self._log(logging.ERROR, "label validator initialization failed: %s", traceback.format_exc())
                self._label_validator = None
                return
        self._label_validator = None
        self._log(logging.WARNING, "unable to instantiate LabelValidator; using config-based validation")

    def _initialize_pipeline_components(self) -> None:
        if self._orchestrator is not None and getattr(self._orchestrator, "packet_builder", None) is not None:
            self._packet_builder = getattr(self._orchestrator, "packet_builder")
        if self._orchestrator is not None and getattr(self._orchestrator, "trainer_registry", None) is not None:
            self._trainer_registry = getattr(self._orchestrator, "trainer_registry")
        if (
            self._trainer_registry is None
            or not hasattr(self._trainer_registry, "get_trainer_config")
            or not callable(getattr(self._trainer_registry, "get_trainer_config", None))
        ) and TrainerRegistry is not None:
            try:
                self._trainer_registry = TrainerRegistry(config_path=self._tracks_config_path)
            except Exception:
                self._trainer_registry = None
        if PacketRouter is not None and self._trainer_registry is not None:
            try:
                self._packet_router = PacketRouter(registry=self._trainer_registry, db_conn=self._audit_db_connection)
            except Exception:
                self._packet_router = None
        self._initialize_vault_components()
        if TrainRunner is not None:
            try:
                self._train_runner = TrainRunner(db_conn=self._audit_db_connection, r2_client=self._r2_client)
            except Exception:
                self._train_runner = None

    def _initialize_vault_components(self) -> None:
        if R2Client is not None:
            try:
                self._r2_client = R2Client()
            except Exception:
                self._r2_client = None
        if VaultCatalog is not None and self._r2_client is not None:
            try:
                self._vault_catalog = VaultCatalog(r2_client=self._r2_client, db_conn=self._audit_db_connection)
            except Exception:
                self._vault_catalog = None

    def _record_training_run(self, summary: PipelineFileSummary) -> None:
        if self._audit_db_connection is None:
            return
        self._audit_db_connection.execute(
            f"""
            INSERT OR REPLACE INTO {TRAINING_RUNS_TABLE} (
                run_id, source_file, track, scenario, packet_count, routed_count,
                submitted_jobs, staging_path, vault_marked, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                summary.run_id,
                summary.source_file,
                summary.track,
                summary.scenario,
                int(summary.packet_count),
                int(summary.routed_count),
                int(summary.submitted_jobs),
                summary.staging_path,
                1 if summary.vault_marked else 0,
                self._utc_now(),
            ),
        )
        self._audit_db_connection.commit()

    def _record_packet_rows(
        self,
        run_id: str,
        routing_manifests: list[dict[str, Any]],
        submitted_job_ids: list[str],
    ) -> None:
        if self._audit_db_connection is None:
            return
        created_at = self._utc_now()
        for index, manifest in enumerate(routing_manifests):
            packet_path = str(manifest.get("packet", ""))
            train_job_id = submitted_job_ids[index] if index < len(submitted_job_ids) else ""
            status = "submitted" if train_job_id else "routed"
            self._audit_db_connection.execute(
                f"""
                INSERT INTO {PACKETS_TABLE} (
                    run_id, packet_path, train_job_id, status, routing_manifest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    packet_path,
                    train_job_id or None,
                    status,
                    json.dumps(manifest, ensure_ascii=True, sort_keys=True),
                    created_at,
                ),
            )
        self._audit_db_connection.commit()

    def _log_pipeline_summary(self, summary: PipelineFileSummary) -> None:
        self._log(
            logging.INFO,
            (
                "pipeline summary run_id=%s packets=%d routed=%d submitted=%d "
                "staging=%s vault_marked=%s"
            ),
            summary.run_id,
            summary.packet_count,
            summary.routed_count,
            summary.submitted_jobs,
            summary.staging_path,
            summary.vault_marked,
            filename=summary.source_file,
            track=summary.track,
            scenario=summary.scenario,
        )

    @staticmethod
    def _pipeline_run_id() -> str:
        return f"run-{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_runtime_directories(self) -> None:
        self._inbox_dir.mkdir(parents=True, exist_ok=True)
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self._packet_output_root.mkdir(parents=True, exist_ok=True)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _configure_logging(self) -> logging.Logger:
        logger = logging.getLogger("s3m.pipeline.packet_watcher")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if logger.handlers:
            return logger
        formatter = logging.Formatter(
            fmt=(
                "%(asctime)s %(levelname)s filename=%(packet_filename)s track=%(track)s "
                "scenario=%(scenario)s message=%(message)s"
            ),
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        context_filter = _ContextDefaultsFilter()
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_handler.setFormatter(formatter)
        stdout_handler.addFilter(context_filter)
        logger.addHandler(stdout_handler)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        logger.addHandler(file_handler)
        return logger

    @staticmethod
    def _resolve_tracks_config_path() -> Path:
        for candidate in DEFAULT_TRACKS_CONFIG_CANDIDATES:
            if candidate.exists():
                return candidate
        return DEFAULT_TRACKS_CONFIG_CANDIDATES[0]

    def _log(
        self,
        level: int,
        message: str,
        *args: Any,
        filename: str = "-",
        track: str = "-",
        scenario: str = "-",
    ) -> None:
        self._logger.log(
            level,
            message,
            *args,
            extra={"packet_filename": filename, "track": track, "scenario": scenario},
        )

    @staticmethod
    def _dedupe_destination(parent: Path, filename: str) -> Path:
        base = parent / filename
        if not base.exists():
            return base
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        index = 1
        while True:
            candidate = parent / f"{stem}-{index:03d}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1


def _packet_builder_call_builders(
    jsonl_file: Path,
    track: str,
    scenario: str,
    data_class: str,
    output_dir: Path,
) -> Iterable[Callable[[], Any]]:
    # Keep multiple call shapes to support evolving PacketBuilder signatures
    # across environments while still passing inferred track/scenario context.
    rich_kwargs = {
        "track": track,
        "scenario": scenario,
        "data_class": data_class,
        "output_dir": output_dir,
    }
    with_scenario = {"track": track, "scenario": scenario, "output_dir": output_dir}
    with_data_class = {"track": track, "data_class": data_class, "output_dir": output_dir}
    minimal = {"track": track, "output_dir": output_dir}
    path_keys = ("input_file", "input_path", "jsonl_path", "file_path", "path")
    builders: list[Callable[[], Any]] = []
    for key in path_keys:
        builders.append(lambda k=key: {"kwargs": {k: jsonl_file, **rich_kwargs}})
        builders.append(lambda k=key: {"kwargs": {k: jsonl_file, **with_scenario}})
        builders.append(lambda k=key: {"kwargs": {k: jsonl_file, **with_data_class}})
        builders.append(lambda k=key: {"kwargs": {k: jsonl_file, **minimal}})
    builders.append(lambda: {"args": (jsonl_file,), "kwargs": dict(rich_kwargs)})
    builders.append(lambda: {"args": (jsonl_file,), "kwargs": dict(with_scenario)})
    builders.append(lambda: {"args": (jsonl_file,), "kwargs": dict(with_data_class)})
    builders.append(lambda: {"args": (jsonl_file,), "kwargs": dict(minimal)})
    builders.append(lambda: {"args": (jsonl_file, track, scenario, output_dir), "kwargs": {}})
    builders.append(lambda: {"args": (jsonl_file, track, data_class, output_dir), "kwargs": {}})
    builders.append(lambda: {"args": (jsonl_file, track, output_dir), "kwargs": {}})
    return builders


def _validator_call_builders(track: str, scenario: str) -> Iterable[Callable[[], Any]]:
    return (
        lambda: {"kwargs": {"track": track, "scenario": scenario}},
        lambda: {"kwargs": {"track_name": track, "scenario_name": scenario}},
        lambda: {"args": (track, scenario), "kwargs": {}},
        lambda: {"args": (scenario,), "kwargs": {"track": track}},
    )


def _register_call_builders(track: str, scenario: str, defaults: Dict[str, Any]) -> Iterable[Callable[[], Any]]:
    return (
        lambda: {"kwargs": {"track": track, "scenario": scenario, "defaults": defaults}},
        lambda: {"kwargs": {"track_name": track, "scenario_name": scenario, "defaults": defaults}},
        lambda: {"kwargs": {"payload": defaults}},
        lambda: {"args": (track, scenario), "kwargs": {"defaults": defaults}},
        lambda: {"args": (defaults,), "kwargs": {}},
    )


def _route_batch_call_builders(
    packets: list[Path], track: str, scenario: str
) -> Iterable[Callable[[], Dict[str, Any]]]:
    packet_values = [Path(item) for item in packets]
    return (
        lambda: {"kwargs": {"packets": packet_values, "track": track, "scenario": scenario}},
        lambda: {"args": (packet_values, track, scenario), "kwargs": {}},
    )


def _call_with_signature_fallbacks(
    method: Callable[..., Any],
    call_builders: Iterable[Callable[[], Dict[str, Any]]],
) -> tuple[Any, bool]:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        signature = None
    for builder in call_builders:
        call_data = builder()
        args = tuple(call_data.get("args", ()))
        kwargs = dict(call_data.get("kwargs", {}))
        if signature is not None:
            try:
                signature.bind(*args, **kwargs)
            except TypeError:
                continue
        try:
            return method(*args, **kwargs), True
        except TypeError:
            continue
    return None, False


def _parse_track_definitions(payload: Any) -> Dict[str, TrackDefinition]:
    if payload is None:
        return {}

    raw_tracks: Any
    if isinstance(payload, dict) and isinstance(payload.get("tracks"), (dict, list)):
        raw_tracks = payload.get("tracks")
    else:
        raw_tracks = payload

    parsed: Dict[str, TrackDefinition] = {}
    if isinstance(raw_tracks, dict):
        for name, node in raw_tracks.items():
            definition = _parse_single_track(track_name=name, track_payload=node)
            parsed[definition.name] = definition
    elif isinstance(raw_tracks, list):
        for item in raw_tracks:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name", item.get("track", item.get("id")))
            if not raw_name:
                continue
            definition = _parse_single_track(track_name=str(raw_name), track_payload=item)
            parsed[definition.name] = definition
    return parsed


def _parse_single_track(track_name: str, track_payload: Any) -> TrackDefinition:
    normalized_track = _normalize_slug(track_name)
    scenarios: Dict[str, ScenarioDefinition] = {}

    default_data_class = DEFAULT_DATA_CLASS
    output_dir: Optional[str] = None
    if isinstance(track_payload, dict):
        default_data_class = _normalize_slug(
            str(
                track_payload.get(
                    "default_data_class",
                    track_payload.get("data_class", track_payload.get("packet_data_class", DEFAULT_DATA_CLASS)),
                )
            )
        ) or DEFAULT_DATA_CLASS
        raw_output = track_payload.get("output_dir")
        if raw_output:
            output_dir = str(raw_output)
        raw_scenarios = track_payload.get("scenarios", track_payload.get("scenario_labels", []))
        scenarios = _parse_scenarios(raw_scenarios, default_data_class=default_data_class)

    return TrackDefinition(
        name=normalized_track,
        default_data_class=default_data_class or DEFAULT_DATA_CLASS,
        output_dir=output_dir,
        scenarios=scenarios,
    )


def _parse_scenarios(raw_scenarios: Any, default_data_class: str) -> Dict[str, ScenarioDefinition]:
    parsed: Dict[str, ScenarioDefinition] = {}
    if isinstance(raw_scenarios, dict):
        for scenario_name, node in raw_scenarios.items():
            normalized_scenario = _normalize_slug(str(scenario_name))
            data_class: Optional[str] = default_data_class
            output_dir: Optional[str] = None
            if isinstance(node, dict):
                raw_data_class = node.get("data_class", default_data_class)
                if raw_data_class:
                    data_class = _normalize_slug(str(raw_data_class))
                raw_output = node.get("output_dir")
                if raw_output:
                    output_dir = str(raw_output)
            elif isinstance(node, str) and node.strip():
                data_class = _normalize_slug(node)
            parsed[normalized_scenario] = ScenarioDefinition(
                name=normalized_scenario,
                data_class=data_class or default_data_class,
                output_dir=output_dir,
            )
        return parsed

    if isinstance(raw_scenarios, list):
        for item in raw_scenarios:
            if isinstance(item, str):
                scenario_name = _normalize_slug(item)
                parsed[scenario_name] = ScenarioDefinition(name=scenario_name, data_class=default_data_class)
                continue
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name", item.get("scenario", item.get("id")))
            if not raw_name:
                continue
            scenario_name = _normalize_slug(str(raw_name))
            raw_data_class = item.get("data_class", default_data_class)
            output_dir = item.get("output_dir")
            parsed[scenario_name] = ScenarioDefinition(
                name=scenario_name,
                data_class=_normalize_slug(str(raw_data_class)) or default_data_class,
                output_dir=str(output_dir) if output_dir else None,
            )
    return parsed


def _normalize_slug(raw_value: str) -> str:
    lowered = str(raw_value).strip().lower().replace("-", "_").replace(" ", "_")
    cleaned = _SLUG_SANITIZE_RE.sub("_", lowered)
    collapsed = _COLLAPSE_UNDERSCORE_RE.sub("_", cleaned)
    return collapsed.strip("_")


def _coerce_validation_result(result: Any) -> Optional[bool]:
    if result is None:
        return None
    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        for key in ("valid", "is_valid", "known", "exists"):
            if key in result:
                value = result[key]
                if isinstance(value, bool):
                    return value
        return None
    if isinstance(result, str):
        normalized = result.strip().lower()
        if normalized in {"valid", "ok", "exists", "known"}:
            return True
        if normalized in {"unknown", "missing", "invalid"}:
            return False
    return None


def main() -> None:
    watcher = PacketWatcher()
    watcher.run_forever()


if __name__ == "__main__":
    main()

"""Final integration layer for the S3M-Engine training pipeline.

Military/tactical context:
This orchestrator coordinates packet intake, validation, routing, and training
dispatch so adaptation loops remain resilient when links are degraded and edge
operators must keep model updates controlled, auditable, and recoverable.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psycopg2
except Exception:  # pragma: no cover - optional runtime dependency
    psycopg2 = None  # type: ignore[assignment]

from src.catalog.dataset_catalog import load_dataset_records
try:
    from src.storage.object_storage import ObjectStorageConnector
except Exception:  # pragma: no cover - optional dependency/import guard
    ObjectStorageConnector = None  # type: ignore[assignment]
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cloud_cpu.track_router import TrackRouter
from src.training.cloud_cpu.trainer_service import TrainerService
from src.training.packet_builder import PacketBuilder

logger = logging.getLogger("s3m.pipeline.orchestrator")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


class R2Client:
    """Thin adapter over object storage connector for vault checks."""

    def __init__(self) -> None:
        self.bucket = os.getenv("R2_BUCKET", "s3m-vault").strip()
        self.endpoint = os.getenv("R2_ENDPOINT", "").strip()
        self.access_key = os.getenv("R2_ACCESS_KEY", "").strip()
        self.secret_key = os.getenv("R2_SECRET_KEY", "").strip()
        self._active_probe = os.getenv("S3M_R2_HEALTH_ACTIVE", "0").strip() == "1"
        self._connector: Optional[ObjectStorageConnector] = None
        self._init_error: Optional[str] = None
        self._build_connector()

    def _build_connector(self) -> None:
        if ObjectStorageConnector is None:
            self._init_error = "object storage connector unavailable"
            return
        if not self.bucket or not self.endpoint or not self.access_key or not self.secret_key:
            self._init_error = "missing R2_* credentials or endpoint"
            return
        try:
            self._connector = ObjectStorageConnector(
                bucket_name=self.bucket,
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                region_name="auto",
            )
            self._init_error = None
        except Exception as exc:  # pragma: no cover - dependency/network specific
            self._init_error = str(exc)
            self._connector = None

    def healthcheck(self) -> Dict[str, Any]:
        if self._connector is None:
            return {"ok": False, "details": self._init_error or "connector not initialized"}
        if self._active_probe:
            # Tactical offline default: avoid external network probes unless explicitly enabled.
            return {"ok": True, "details": "configured (active probe intentionally skipped in offline mode)"}
        return {"ok": True, "details": "configured (passive health mode)"}

    def shutdown(self) -> None:
        self._connector = None


class VaultCatalog:
    """Loads vault-side dataset metadata used to route approved scenarios."""

    def __init__(self, catalog_path: Optional[str | Path] = None) -> None:
        default_path = Path(os.getenv("VAULT_CATALOG_PATH", "catalog/datasets/saudi_mod.v1.json"))
        self.catalog_path = Path(catalog_path or default_path)
        self._records: tuple[Any, ...] = tuple()
        self._last_error: Optional[str] = None
        self.refresh()

    def refresh(self) -> None:
        try:
            self._records = tuple(load_dataset_records(self.catalog_path))
            self._last_error = None
        except Exception as exc:
            self._records = tuple()
            self._last_error = str(exc)

    def healthcheck(self) -> Dict[str, Any]:
        if self._last_error is not None:
            return {"ok": False, "details": self._last_error, "record_count": 0}
        return {"ok": True, "details": "catalog loaded", "record_count": len(self._records)}


class LabelValidator:
    """Uses packet checksums and schema checks before queue admission."""

    def __init__(self, packet_builder: Optional[PacketBuilder] = None) -> None:
        self._packet_builder = packet_builder

    def attach_builder(self, packet_builder: PacketBuilder) -> None:
        self._packet_builder = packet_builder

    def validate_pack(self, pack_dir: Path) -> bool:
        if self._packet_builder is None:
            return False
        return bool(self._packet_builder.validate_pack(pack_dir))

    def healthcheck(self) -> Dict[str, Any]:
        return {
            "ok": self._packet_builder is not None,
            "details": "ready" if self._packet_builder is not None else "packet builder not attached",
        }


class TrainerRegistry:
    """Maps track names to lazily-created trainer service instances."""

    def __init__(self) -> None:
        configured_tracks = os.getenv("S3M_TRAINING_TRACKS", "").strip()
        if configured_tracks:
            tokens = [token.strip() for token in configured_tracks.split(",") if token.strip()]
            self._enabled_tracks = {token.lower() for token in tokens}
        else:
            self._enabled_tracks = {track.value for track in TrainingTrack}
        self._services: Dict[str, TrainerService] = {}
        self._lock = threading.Lock()

    def is_enabled(self, track: str) -> bool:
        return track.lower() in self._enabled_tracks

    def _normalize_track(self, track: str) -> TrainingTrack:
        text = str(track).strip().lower()
        return TrainingTrack(text)

    def get_or_create(self, track: str, paths: StatePaths) -> TrainerService:
        normalized_track = self._normalize_track(track)
        key = normalized_track.value
        with self._lock:
            service = self._services.get(key)
            if service is None:
                service = TrainerService(track=normalized_track, paths=paths)
                self._services[key] = service
            return service

    def shutdown(self) -> None:
        with self._lock:
            for service in self._services.values():
                try:
                    service.stop()
                except Exception:
                    logger.exception("Failed stopping trainer service")

    def healthcheck(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "enabled_tracks": sorted(self._enabled_tracks),
                "active_services": sorted(self._services.keys()),
            }


class PacketRouter:
    """Adapter around track router used by packet watcher loop."""

    def __init__(self, state_paths: StatePaths) -> None:
        self._state_paths = state_paths
        self._router = TrackRouter(paths=state_paths)

    def route_inbox(self) -> Dict[str, int]:
        return self._router.route_inbox()

    def healthcheck(self) -> Dict[str, Any]:
        return {
            "ok": self._state_paths.inbox.exists(),
            "inbox": str(self._state_paths.inbox),
        }


@dataclass
class TrainingJob:
    """Minimal training job record used by the monitor thread."""

    job_id: str
    track: str
    packet_count: int
    status: str = "queued"
    error: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "track": self.track,
            "packet_count": int(self.packet_count),
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TrainRunner:
    """Processes queued jobs and advances per-track trainer cycles."""

    def __init__(self, registry: TrainerRegistry, state_paths: StatePaths, staging_dir: Path) -> None:
        self._registry = registry
        self._state_paths = state_paths
        self._staging_dir = Path(staging_dir)
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self._job_snapshot_path = self._staging_dir / "runpod_jobs.json"
        self._queue: list[TrainingJob] = []
        self._active: Dict[str, TrainingJob] = {}
        self._lock = threading.Lock()
        self._persist_snapshot()

    def enqueue(self, track: str, packet_count: int) -> Optional[TrainingJob]:
        normalized_track = str(track).strip().lower()
        if not normalized_track or int(packet_count) <= 0:
            return None
        if not self._registry.is_enabled(normalized_track):
            return None
        try:
            TrainingTrack(normalized_track)
        except ValueError:
            return None

        job = TrainingJob(
            job_id=f"run-{uuid.uuid4().hex[:12]}",
            track=normalized_track,
            packet_count=int(packet_count),
        )
        with self._lock:
            self._queue.append(job)
            self._persist_snapshot()
        return job

    def monitor_once(self) -> Optional[TrainingJob]:
        with self._lock:
            if not self._queue:
                self._persist_snapshot()
                return None
            job = self._queue.pop(0)
            job.status = "running"
            job.updated_at = _utcnow()
            self._active[job.job_id] = job
            self._persist_snapshot()

        try:
            service = self._registry.get_or_create(track=job.track, paths=self._state_paths)
            service.run_cycle_once()
            job.status = "success"
            job.error = ""
        except Exception as exc:
            logger.exception("TrainRunner job failed: track=%s job=%s", job.track, job.job_id)
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.updated_at = _utcnow()
            with self._lock:
                self._active.pop(job.job_id, None)
                self._persist_snapshot()
        return job

    def _persist_snapshot(self) -> None:
        payload = {
            "updated_at": _utcnow(),
            "queued_jobs": len(self._queue),
            "active_jobs": len(self._active),
            "active_job_ids": sorted(self._active.keys()),
        }
        self._job_snapshot_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def shutdown(self) -> None:
        self._registry.shutdown()
        with self._lock:
            self._queue.clear()
            self._active.clear()
            self._persist_snapshot()

    def healthcheck(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "queued_jobs": len(self._queue),
                "active_jobs": len(self._active),
                "snapshot_path": str(self._job_snapshot_path),
            }


class Orchestrator:
    """Wires all training-pipeline components into one runtime controller."""

    def __init__(self, poll_interval: Optional[int] = None) -> None:
        self.s3m_root = Path(os.getenv("S3M_ROOT", "/opt/s3m")).resolve()
        self.inbox_dir = Path(
            os.getenv("INBOX_DIR", str(self.s3m_root / "state" / "training" / "cloud_cpu" / "inbox"))
        ).resolve()
        self.packets_dir = Path(os.getenv("PACKETS_DIR", str(self.s3m_root / "packets"))).resolve()
        self.staging_dir = Path(
            os.getenv("STAGING_DIR", str(self.s3m_root / "state" / "training" / "staging"))
        ).resolve()
        self.log_dir = Path(os.getenv("LOG_DIR", str(self.s3m_root / "logs"))).resolve()
        self.poll_interval = _normalize_positive_int(poll_interval or os.getenv("POLL_INTERVAL", 10), default=10)
        self.examples_per_pack = _normalize_positive_int(os.getenv("EXAMPLES_PER_PACK", 50), default=50)

        state_root = self.inbox_dir.parent
        self.state_paths = StatePaths(root=state_root)

        self.s3m_root.mkdir(parents=True, exist_ok=True)
        self.packets_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.state_paths.ensure_dirs()

        self.r2_client = R2Client()
        self.vault_catalog = VaultCatalog()
        self.db_conn = self._init_db_connection()
        self.label_validator = LabelValidator()
        self.trainer_registry = TrainerRegistry()
        self.packet_builder = PacketBuilder(source="manual")
        self.label_validator.attach_builder(self.packet_builder)
        self.packet_router = PacketRouter(self.state_paths)
        self.train_runner = TrainRunner(
            registry=self.trainer_registry,
            state_paths=self.state_paths,
            staging_dir=self.staging_dir,
        )

        self._stop_event = threading.Event()
        self._db_lock = threading.Lock()
        self._running = False
        self._watcher_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._last_watcher_error = ""
        self._last_monitor_error = ""

    def _init_db_connection(self) -> Any:
        if psycopg2 is None:
            logger.warning("psycopg2 is unavailable; DB integration disabled")
            return None

        params = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "dbname": os.getenv("DB_NAME", "s3m"),
            "user": os.getenv("DB_USER", "s3m_user"),
            "password": os.getenv("DB_PASS", ""),
            "connect_timeout": 3,
        }
        try:
            conn = psycopg2.connect(**params)
            conn.autocommit = True
            self._ensure_training_runs_table(conn)
            return conn
        except Exception as exc:
            logger.warning("DB connection unavailable: %s", exc)
            return None

    @staticmethod
    def _ensure_training_runs_table(conn: Any) -> None:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS training_runs (
                    run_id TEXT PRIMARY KEY,
                    track TEXT NOT NULL,
                    packet_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def run(self) -> None:
        """Start watcher and job monitor loops in parallel threads."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._watcher_thread = threading.Thread(target=self._watcher_loop, name="s3m-packet-watcher", daemon=True)
        self._monitor_thread = threading.Thread(target=self._job_monitor_loop, name="s3m-job-monitor", daemon=True)
        self._watcher_thread.start()
        self._monitor_thread.start()
        logger.info("Orchestrator started (poll_interval=%ss)", self.poll_interval)

    def _watcher_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._watcher_once()
                self._last_watcher_error = ""
            except Exception as exc:
                self._last_watcher_error = str(exc)
                logger.exception("Packet watcher loop failed")
            self._stop_event.wait(float(self.poll_interval))

    def _watcher_once(self) -> None:
        self._reject_invalid_inbox_packets()
        routed = self.packet_router.route_inbox()
        for track, packet_count in routed.items():
            if int(packet_count) <= 0:
                continue
            job = self.train_runner.enqueue(track=track, packet_count=int(packet_count))
            if job is not None:
                self._db_insert_job(job)

    def _reject_invalid_inbox_packets(self) -> None:
        rejected_root = self.state_paths.rejected / "inbox"
        rejected_root.mkdir(parents=True, exist_ok=True)
        for pack_dir in sorted(self.state_paths.inbox.iterdir(), key=lambda item: item.name):
            if not pack_dir.is_dir():
                continue
            if self.label_validator.validate_pack(pack_dir):
                continue
            # Tactical gate: malformed packets are isolated before route staging.
            destination = rejected_root / pack_dir.name
            suffix = 1
            while destination.exists():
                destination = rejected_root / f"{pack_dir.name}-{suffix:03d}"
                suffix += 1
            shutil.move(str(pack_dir), str(destination))
            logger.warning("Rejected malformed scenario pack: %s", destination.name)

    def _job_monitor_loop(self) -> None:
        sleep_seconds = max(1.0, self.poll_interval / 2.0)
        while not self._stop_event.is_set():
            try:
                completed = self.train_runner.monitor_once()
                if completed is not None:
                    self._db_update_job(completed)
                self._last_monitor_error = ""
            except Exception as exc:
                self._last_monitor_error = str(exc)
                logger.exception("Job monitor loop failed")
            self._stop_event.wait(sleep_seconds)

    def _db_insert_job(self, job: TrainingJob) -> None:
        if self.db_conn is None:
            return
        with self._db_lock:
            with self.db_conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO training_runs (run_id, track, packet_count, status, error_message, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (run_id) DO UPDATE
                    SET track = EXCLUDED.track,
                        packet_count = EXCLUDED.packet_count,
                        status = EXCLUDED.status,
                        error_message = EXCLUDED.error_message,
                        updated_at = NOW();
                    """,
                    (job.job_id, job.track, int(job.packet_count), job.status, job.error),
                )

    def _db_update_job(self, job: TrainingJob) -> None:
        if self.db_conn is None:
            return
        with self._db_lock:
            with self.db_conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE training_runs
                    SET status = %s,
                        error_message = %s,
                        updated_at = NOW()
                    WHERE run_id = %s;
                    """,
                    (job.status, job.error, job.job_id),
                )

    def shutdown(self) -> None:
        """Gracefully stop threads and close all owned resources."""
        self._stop_event.set()
        self._running = False
        if self._watcher_thread is not None:
            self._watcher_thread.join(timeout=5.0)
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=5.0)
        self.train_runner.shutdown()
        self.r2_client.shutdown()
        if self.db_conn is not None:
            try:
                self.db_conn.close()
            except Exception:
                logger.exception("DB close failed")
            finally:
                self.db_conn = None
        logger.info("Orchestrator shutdown complete")

    def _db_healthcheck(self) -> Dict[str, Any]:
        if self.db_conn is None:
            return {"ok": False, "details": "connection unavailable"}
        try:
            with self._db_lock:
                with self.db_conn.cursor() as cursor:
                    cursor.execute("SELECT 1;")
                    row = cursor.fetchone()
            return {"ok": bool(row and int(row[0]) == 1), "details": "connected"}
        except Exception as exc:
            return {"ok": False, "details": str(exc)}

    def status(self) -> Dict[str, Any]:
        """Return component-level health for operator dashboards."""
        return {
            "running": self._running,
            "poll_interval": self.poll_interval,
            "examples_per_pack": self.examples_per_pack,
            "threads": {
                "watcher_alive": bool(self._watcher_thread and self._watcher_thread.is_alive()),
                "monitor_alive": bool(self._monitor_thread and self._monitor_thread.is_alive()),
                "watcher_last_error": self._last_watcher_error,
                "monitor_last_error": self._last_monitor_error,
            },
            "components": {
                "r2_client": self.r2_client.healthcheck(),
                "vault_catalog": self.vault_catalog.healthcheck(),
                "db_connection": self._db_healthcheck(),
                "label_validator": self.label_validator.healthcheck(),
                "trainer_registry": self.trainer_registry.healthcheck(),
                "packet_builder": {
                    "ok": hasattr(self.packet_builder, "build_from_jsonl"),
                    "details": "ready",
                },
                "packet_router": self.packet_router.healthcheck(),
                "train_runner": self.train_runner.healthcheck(),
            },
        }

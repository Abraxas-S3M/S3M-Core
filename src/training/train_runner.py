"""RunPod training execution bridge for S3M-Engine packet routing.

Military/tactical context:
This runner stages packetized supervision payloads into sovereign R2 storage,
dispatches short-lived RunPod training sorties, and continuously tracks mission
state so command operators can recover trained artifacts without manual polling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("s3m.training.train_runner")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class _StoredJob:
    job_id: str
    status: str
    progress: float
    eta_seconds: int
    output_path: str | None
    error: str | None
    artifacts_downloaded: bool
    artifacts_local_path: str | None


class TrainRunner:
    """Submit and monitor RunPod serverless training jobs."""

    _DB_PATH = Path("/workspace/state/training/train_runner.db")
    _DB_TABLE = "training_jobs"
    _VALID_STATES = {"pending", "running", "completed", "failed"}
    _RUNPOD_API_BASE = "https://api.runpod.ai/v2"

    def __init__(self, db_conn: Any = None, r2_client: Any = None) -> None:
        self._owns_db_conn = db_conn is None
        self.db_conn = db_conn or self._build_default_db()
        self._ensure_db_schema()

        self.r2_client = r2_client or self._build_default_r2_client()
        self.r2_bucket = self._required_env("R2_BUCKET")
        self.r2_endpoint = self._required_env("R2_ENDPOINT")
        self.runpod_api_key = os.getenv("RUNPOD_API_KEY", "").strip()
        self.runpod_endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "").strip()
        self.runpod_api_base = os.getenv("RUNPOD_API_BASE", self._RUNPOD_API_BASE).rstrip("/")
        self.callback_url_default = os.getenv("TRAIN_RUNNER_CALLBACK_URL", "").strip() or None
        self.offline_mode = os.getenv("RUNPOD_OFFLINE_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
        self.artifact_root = Path("/workspace/state/training/runpod_artifacts")
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def submit_job(self, routing_manifest: dict) -> str:
        """Stage packet files to R2, launch RunPod training, persist job metadata."""
        manifest = self._validate_routing_manifest(routing_manifest)
        packet_paths = self._extract_packet_paths(manifest)
        trainer_config = self._extract_trainer_config(manifest)
        callback_url = self._extract_callback_url(manifest)
        provisional_job_id = f"job-{uuid.uuid4().hex}"

        packet_records = [
            self._stage_packet_file(
                local_path=packet_path,
                staging_prefix=f"training/staging/{provisional_job_id}/packets/",
            )
            for packet_path in packet_paths
        ]
        output_path = self._normalize_output_path(manifest, provisional_job_id)

        runpod_payload = {
            "input": {
                "packets": packet_records,
                "packet_urls": [record["url"] for record in packet_records],
                "trainer_config": trainer_config,
                "model_output_path": output_path,
                "callback_url": callback_url,
                "job_label": str(manifest.get("job_label", provisional_job_id)),
            }
        }

        runpod_response = self._submit_runpod_job(runpod_payload)
        job_id = self._extract_runpod_job_id(runpod_response) or provisional_job_id
        status = self._normalize_status(runpod_response.get("status", "pending"))

        self._insert_job(
            job_id=job_id,
            status=status,
            progress=self._extract_progress(runpod_response),
            eta_seconds=self._extract_eta(runpod_response),
            output_path=output_path,
            error=self._extract_error(runpod_response),
            routing_manifest=manifest,
            packet_keys=[str(record["r2_uri"]) for record in packet_records],
        )
        logger.info("Submitted RunPod training job=%s packets=%d", job_id, len(packet_records))
        return job_id

    def check_job_status(self, job_id: str) -> dict:
        """Fetch and persist normalized status payload for one job."""
        normalized_job_id = self._validate_job_id(job_id)
        stored = self._get_job(normalized_job_id)
        if stored is None:
            raise ValueError(f"Unknown job_id: {normalized_job_id}")

        if stored.status in {"completed", "failed"}:
            return self._status_payload(stored)

        runpod_status = self._fetch_runpod_status(normalized_job_id)
        merged_status = self._normalize_status(runpod_status.get("status", stored.status))
        merged_progress = self._extract_progress(runpod_status, fallback=stored.progress)
        merged_eta = self._extract_eta(runpod_status, fallback=stored.eta_seconds)
        merged_output = self._extract_output_path(runpod_status) or stored.output_path
        merged_error = self._extract_error(runpod_status) or stored.error

        self._update_job(
            job_id=normalized_job_id,
            status=merged_status,
            progress=merged_progress,
            eta_seconds=merged_eta,
            output_path=merged_output,
            error=merged_error,
        )
        refreshed = self._get_job(normalized_job_id)
        if refreshed is None:
            raise RuntimeError(f"Job vanished while updating state: {normalized_job_id}")
        return self._status_payload(refreshed)

    def monitor_jobs(self) -> None:
        """Poll all active jobs; download completion artifacts and log outcomes."""
        for job_id in self._list_active_job_ids():
            try:
                status = self.check_job_status(job_id)
            except Exception as exc:
                logger.exception("Failed to refresh status for job=%s: %s", job_id, exc)
                continue

            if status["status"] != "completed":
                if status["status"] == "failed":
                    logger.error("RunPod job failed job_id=%s error=%s", job_id, status.get("error"))
                continue

            stored = self._get_job(job_id)
            if stored is None or stored.artifacts_downloaded:
                continue

            output_path = status.get("output_path")
            if not isinstance(output_path, str) or not output_path.strip():
                logger.warning("Completed job missing output path job_id=%s", job_id)
                continue

            try:
                local_dir = self._download_artifacts(job_id=job_id, output_path=output_path)
                self._mark_artifacts_downloaded(job_id=job_id, local_path=str(local_dir))
                logger.info("Downloaded completed artifacts for job=%s into %s", job_id, local_dir)
            except Exception as exc:
                logger.exception("Artifact download failed for job=%s: %s", job_id, exc)

    def run_local(self, routing_manifest: dict) -> dict:
        """Fallback CPU-only local train path for deterministic integration testing."""
        manifest = self._validate_routing_manifest(routing_manifest)
        packet_paths = self._extract_packet_paths(manifest)
        examples = self._load_examples(packet_paths)
        if not examples:
            raise ValueError("No training examples were found in packet files.")

        trainer_config = self._extract_trainer_config(manifest)
        max_steps = int(trainer_config.get("max_steps", 10))
        learning_rate = float(trainer_config.get("learning_rate", 1e-3))
        output_dir = Path(str(trainer_config.get("output_dir", "/workspace/state/training/local_cpu_runs")))
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            import torch
            from torch.utils.data import Dataset
            from transformers import Trainer, TrainingArguments
        except Exception as exc:
            logger.warning("Transformers stack unavailable for local fallback: %s", exc)
            return {
                "status": "failed",
                "error": f"transformers runtime unavailable: {exc}",
                "examples_trained": len(examples),
            }

        class _ToyDataset(Dataset):
            def __init__(self, rows: list[tuple[str, str]]) -> None:
                self._rows = rows

            def __len__(self) -> int:
                return len(self._rows)

            def __getitem__(self, idx: int) -> dict[str, Any]:
                prompt, completion = self._rows[idx]
                feature = torch.tensor(
                    [len(prompt.encode("utf-8")), len(completion.encode("utf-8"))],
                    dtype=torch.float32,
                )
                # Tactical heuristic: completion length is a stand-in training target.
                label = torch.tensor([float(len(completion.encode("utf-8")))], dtype=torch.float32)
                return {"input_ids": feature, "labels": label}

        class _ToyModel(torch.nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.linear = torch.nn.Linear(2, 1)

            def forward(self, input_ids: Any = None, labels: Any = None, **_: Any) -> dict[str, Any]:
                logits = self.linear(input_ids.float())
                loss = None
                if labels is not None:
                    loss = torch.nn.functional.mse_loss(logits, labels.float())
                return {"loss": loss, "logits": logits}

        def _collate_fn(batch: list[dict[str, Any]]) -> dict[str, Any]:
            return {
                "input_ids": torch.stack([item["input_ids"] for item in batch]),
                "labels": torch.stack([item["labels"] for item in batch]),
            }

        train_output_dir = output_dir / f"local-{uuid.uuid4().hex[:8]}"
        args = TrainingArguments(
            output_dir=str(train_output_dir),
            per_device_train_batch_size=max(1, int(trainer_config.get("batch_size", 4))),
            max_steps=max_steps,
            learning_rate=learning_rate,
            logging_steps=max(1, min(10, max_steps)),
            save_steps=max(1, max_steps),
            report_to=[],
            no_cuda=True,
        )
        trainer = Trainer(
            model=_ToyModel(),
            args=args,
            train_dataset=_ToyDataset(examples),
            data_collator=_collate_fn,
        )
        training_result = trainer.train()
        metrics = dict(training_result.metrics)
        metrics["status"] = "completed"
        metrics["examples_trained"] = len(examples)
        metrics["output_dir"] = str(train_output_dir)
        return metrics

    def close(self) -> None:
        if self._owns_db_conn and hasattr(self.db_conn, "close"):
            self.db_conn.close()

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _build_default_db(self) -> sqlite3.Connection:
        self._DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db_schema(self) -> None:
        self.db_conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._DB_TABLE} (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0.0,
                eta_seconds INTEGER NOT NULL DEFAULT -1,
                output_path TEXT,
                error TEXT,
                routing_manifest TEXT NOT NULL,
                packet_keys TEXT NOT NULL DEFAULT '[]',
                artifacts_downloaded INTEGER NOT NULL DEFAULT 0,
                artifacts_local_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.db_conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{self._DB_TABLE}_status ON {self._DB_TABLE}(status)"
        )
        self.db_conn.commit()

    def _build_default_r2_client(self) -> Any:
        access_key = self._required_env("R2_ACCESS_KEY")
        secret_key = self._required_env("R2_SECRET_KEY")
        endpoint = self._required_env("R2_ENDPOINT")
        bucket = self._required_env("R2_BUCKET")
        try:
            from src.storage.object_storage import ObjectStorageConnector
        except Exception as exc:  # pragma: no cover - protective path
            raise RuntimeError(f"ObjectStorageConnector unavailable: {exc}") from exc
        return ObjectStorageConnector(
            access_key=access_key,
            secret_key=secret_key,
            endpoint=endpoint,
            bucket_name=bucket,
            region_name="auto",
        )

    @staticmethod
    def _required_env(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value

    @staticmethod
    def _validate_job_id(job_id: str) -> str:
        value = str(job_id).strip()
        if not value:
            raise ValueError("job_id must be a non-empty string")
        return value

    def _validate_routing_manifest(self, routing_manifest: dict) -> dict:
        if not isinstance(routing_manifest, dict):
            raise ValueError("routing_manifest must be a dictionary")
        if "trainer_config" not in routing_manifest:
            raise ValueError("routing_manifest.trainer_config is required")
        return routing_manifest

    def _extract_trainer_config(self, manifest: dict) -> dict:
        config = manifest.get("trainer_config")
        if not isinstance(config, dict):
            raise ValueError("routing_manifest.trainer_config must be a dict")
        return config

    def _extract_callback_url(self, manifest: dict) -> str | None:
        callback_url = manifest.get("callback_url", self.callback_url_default)
        if callback_url is None:
            return None
        value = str(callback_url).strip()
        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            return value
        raise ValueError("callback_url must be an http(s) URL")

    def _extract_packet_paths(self, manifest: dict) -> list[Path]:
        raw_packets = manifest.get("packet_files")
        if raw_packets is None:
            raw_packets = manifest.get("packet_paths")
        if raw_packets is None:
            raw_packets = manifest.get("packets")
        if not isinstance(raw_packets, list) or not raw_packets:
            raise ValueError("routing_manifest must provide packet_files as a non-empty list")

        packet_paths: list[Path] = []
        for item in raw_packets:
            raw_path: str | None
            if isinstance(item, str):
                raw_path = item
            elif isinstance(item, dict):
                candidate = item.get("path") or item.get("local_path") or item.get("file")
                raw_path = candidate if isinstance(candidate, str) else None
            else:
                raw_path = None
            if not raw_path:
                raise ValueError("Each packet entry must provide a local path string")
            resolved = Path(raw_path).expanduser().resolve()
            if not resolved.exists() or not resolved.is_file():
                raise FileNotFoundError(f"Packet file not found: {resolved}")
            packet_paths.append(resolved)
        return packet_paths

    def _normalize_output_path(self, manifest: dict, provisional_job_id: str) -> str:
        raw = manifest.get("model_output_path")
        if raw is None:
            return f"r2://{self.r2_bucket}/training/output/{provisional_job_id}/"
        value = str(raw).strip()
        if not value:
            raise ValueError("model_output_path must be non-empty when provided")
        if value.startswith("r2://"):
            return value
        normalized = value.lstrip("/")
        return f"r2://{self.r2_bucket}/{normalized}"

    def _stage_packet_file(self, local_path: Path, staging_prefix: str) -> dict[str, Any]:
        object_key = f"{staging_prefix.rstrip('/')}/{local_path.name}"
        self._r2_upload_file(local_path=local_path, object_key=object_key)
        r2_uri = f"r2://{self.r2_bucket}/{object_key}"
        url = self._r2_get_url(object_key)
        return {
            "name": local_path.name,
            "r2_uri": r2_uri,
            "url": url,
            "sha256": self._sha256(local_path),
            "size_bytes": int(local_path.stat().st_size),
        }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _submit_runpod_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.offline_mode:
            fake_id = f"offline-{uuid.uuid4().hex[:12]}"
            return {"id": fake_id, "status": "IN_QUEUE", "output": payload.get("input", {})}
        self._require_runpod_credentials()
        return self._runpod_request("POST", f"/{self.runpod_endpoint_id}/run", payload=payload)

    def _fetch_runpod_status(self, job_id: str) -> dict[str, Any]:
        if self.offline_mode:
            # Offline mode auto-completes so integration tests can verify artifact flow.
            return {
                "id": job_id,
                "status": "COMPLETED",
                "progress": 1.0,
                "delayTime": 0,
            }
        self._require_runpod_credentials()
        return self._runpod_request("GET", f"/{self.runpod_endpoint_id}/status/{job_id}")

    def _require_runpod_credentials(self) -> None:
        if not self.runpod_api_key:
            raise RuntimeError("Missing required environment variable: RUNPOD_API_KEY")
        if not self.runpod_endpoint_id:
            raise RuntimeError("Missing required environment variable: RUNPOD_ENDPOINT_ID")

    def _runpod_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.runpod_api_base}{path}"
        body = None
        headers = {"Authorization": f"Bearer {self.runpod_api_key}"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url=url, data=body, headers=headers, method=method)

        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = response.read().decode("utf-8")
                parsed = json.loads(data) if data else {}
                if not isinstance(parsed, dict):
                    raise RuntimeError("RunPod response must be a JSON object")
                return parsed
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt >= 3:
                    raise RuntimeError(f"RunPod request failed ({method} {path}): {exc}") from exc
                time.sleep(2 ** (attempt - 1))
        raise RuntimeError(f"RunPod request exhausted retries ({method} {path})")

    @staticmethod
    def _extract_runpod_job_id(payload: dict[str, Any]) -> str | None:
        for key in ("id", "job_id", "jobId"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        data = payload.get("data")
        if isinstance(data, dict):
            return TrainRunner._extract_runpod_job_id(data)
        return None

    def _insert_job(
        self,
        *,
        job_id: str,
        status: str,
        progress: float,
        eta_seconds: int,
        output_path: str | None,
        error: str | None,
        routing_manifest: dict,
        packet_keys: list[str],
    ) -> None:
        now = _utc_now_iso()
        self.db_conn.execute(
            f"""
            INSERT OR REPLACE INTO {self._DB_TABLE} (
                job_id, status, progress, eta_seconds, output_path, error,
                routing_manifest, packet_keys, artifacts_downloaded, artifacts_local_path,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                status,
                float(progress),
                int(eta_seconds),
                output_path,
                error,
                json.dumps(routing_manifest, ensure_ascii=False, sort_keys=True),
                json.dumps(packet_keys, ensure_ascii=False, sort_keys=True),
                0,
                None,
                now,
                now,
            ),
        )
        self.db_conn.commit()

    def _update_job(
        self,
        *,
        job_id: str,
        status: str,
        progress: float,
        eta_seconds: int,
        output_path: str | None,
        error: str | None,
    ) -> None:
        self.db_conn.execute(
            f"""
            UPDATE {self._DB_TABLE}
            SET status = ?, progress = ?, eta_seconds = ?, output_path = ?, error = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (
                status,
                float(progress),
                int(eta_seconds),
                output_path,
                error,
                _utc_now_iso(),
                job_id,
            ),
        )
        self.db_conn.commit()

    def _mark_artifacts_downloaded(self, *, job_id: str, local_path: str) -> None:
        self.db_conn.execute(
            f"""
            UPDATE {self._DB_TABLE}
            SET artifacts_downloaded = 1, artifacts_local_path = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (local_path, _utc_now_iso(), job_id),
        )
        self.db_conn.commit()

    def _get_job(self, job_id: str) -> _StoredJob | None:
        cursor = self.db_conn.execute(
            f"""
            SELECT job_id, status, progress, eta_seconds, output_path, error,
                   artifacts_downloaded, artifacts_local_path
            FROM {self._DB_TABLE}
            WHERE job_id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return _StoredJob(
            job_id=str(row["job_id"] if isinstance(row, sqlite3.Row) else row[0]),
            status=str(row["status"] if isinstance(row, sqlite3.Row) else row[1]),
            progress=float(row["progress"] if isinstance(row, sqlite3.Row) else row[2]),
            eta_seconds=int(row["eta_seconds"] if isinstance(row, sqlite3.Row) else row[3]),
            output_path=(row["output_path"] if isinstance(row, sqlite3.Row) else row[4]),
            error=(row["error"] if isinstance(row, sqlite3.Row) else row[5]),
            artifacts_downloaded=bool(row["artifacts_downloaded"] if isinstance(row, sqlite3.Row) else row[6]),
            artifacts_local_path=(row["artifacts_local_path"] if isinstance(row, sqlite3.Row) else row[7]),
        )

    def _list_active_job_ids(self) -> list[str]:
        cursor = self.db_conn.execute(
            f"SELECT job_id FROM {self._DB_TABLE} WHERE status IN ('pending', 'running') ORDER BY created_at ASC"
        )
        rows = cursor.fetchall()
        return [str((row["job_id"] if isinstance(row, sqlite3.Row) else row[0])) for row in rows]

    def _status_payload(self, job: _StoredJob) -> dict:
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress": float(min(max(job.progress, 0.0), 1.0)),
            "eta_seconds": int(max(job.eta_seconds, 0)),
            "output_path": job.output_path,
            "error": job.error,
        }

    def _extract_progress(self, payload: dict[str, Any], fallback: float = 0.0) -> float:
        candidates = [
            payload.get("progress"),
            payload.get("progress_fraction"),
            self._nested_value(payload, ("output", "progress")),
            self._nested_value(payload, ("output", "progress_fraction")),
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                value = float(candidate)
                if value > 1.0:
                    value = value / 100.0
                return min(max(value, 0.0), 1.0)
            except (TypeError, ValueError):
                continue
        return min(max(float(fallback), 0.0), 1.0)

    def _extract_eta(self, payload: dict[str, Any], fallback: int = -1) -> int:
        candidates = [
            payload.get("eta_seconds"),
            payload.get("eta"),
            payload.get("delayTime"),
            self._nested_value(payload, ("output", "eta_seconds")),
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                return max(0, int(float(candidate)))
            except (TypeError, ValueError):
                continue
        return max(0, int(fallback))

    def _extract_output_path(self, payload: dict[str, Any]) -> str | None:
        candidates = [
            payload.get("model_output_path"),
            self._nested_value(payload, ("output", "model_output_path")),
            self._nested_value(payload, ("output", "output_path")),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def _extract_error(self, payload: dict[str, Any]) -> str | None:
        candidates = [
            payload.get("error"),
            payload.get("message"),
            self._nested_value(payload, ("output", "error")),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def _normalize_status(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        mapping = {
            "queued": "pending",
            "queue": "pending",
            "in_queue": "pending",
            "pending": "pending",
            "initializing": "pending",
            "running": "running",
            "in_progress": "running",
            "processing": "running",
            "completed": "completed",
            "done": "completed",
            "succeeded": "completed",
            "success": "completed",
            "failed": "failed",
            "error": "failed",
            "cancelled": "failed",
            "canceled": "failed",
            "aborted": "failed",
            "timed_out": "failed",
        }
        normalized = mapping.get(text, "pending")
        if normalized not in self._VALID_STATES:
            return "pending"
        return normalized

    @staticmethod
    def _nested_value(payload: dict[str, Any], path: Iterable[str]) -> Any:
        current: Any = payload
        for segment in path:
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
        return current

    def _r2_upload_file(self, *, local_path: Path, object_key: str) -> None:
        methods = [
            lambda: self.r2_client.upload_file(str(local_path), object_key),
            lambda: self.r2_client.upload_file(local_path=local_path, remote_key=object_key),
            lambda: self.r2_client.upload_file(local_path=str(local_path), remote_key=object_key),
            lambda: self.r2_client.upload_file(file_path=str(local_path), remote_key=object_key),
        ]
        for method in methods:
            try:
                method()
                return
            except AttributeError:
                break
            except TypeError:
                continue
        raise RuntimeError("R2 client does not expose a compatible upload_file method")

    def _r2_get_url(self, object_key: str) -> str:
        if hasattr(self.r2_client, "generate_presigned_url"):
            try:
                return str(self.r2_client.generate_presigned_url(object_key, expires_in=86400))
            except TypeError:
                try:
                    return str(self.r2_client.generate_presigned_url(remote_key=object_key, expires_in=86400))
                except TypeError:
                    pass
        return f"{self.r2_endpoint.rstrip('/')}/{self.r2_bucket}/{object_key.lstrip('/')}"

    def _download_artifacts(self, *, job_id: str, output_path: str) -> Path:
        bucket, key = self._parse_r2_uri(output_path)
        if bucket != self.r2_bucket:
            logger.warning("Output path bucket mismatch for job=%s bucket=%s", job_id, bucket)
        output_prefix = key.rstrip("/")
        destination = self.artifact_root / job_id
        destination.mkdir(parents=True, exist_ok=True)

        if output_path.endswith("/"):
            downloaded = self._sync_prefix_to_local(output_prefix + "/", destination)
            if downloaded:
                return destination

        if self._r2_key_exists(output_prefix):
            target = destination / Path(output_prefix).name
            self._download_one_file(output_prefix, target)
            return destination

        prefix = output_prefix + "/"
        keys = self._list_keys(prefix)
        if not keys:
            raise FileNotFoundError(f"No output artifacts found under {output_path}")
        for remote_key in keys:
            relative = remote_key[len(prefix) :] if remote_key.startswith(prefix) else Path(remote_key).name
            local_path = destination / relative
            local_path.parent.mkdir(parents=True, exist_ok=True)
            self._download_one_file(remote_key, local_path)
        return destination

    def _parse_r2_uri(self, uri: str) -> tuple[str, str]:
        value = str(uri).strip()
        if not value.startswith("r2://"):
            raise ValueError(f"Unsupported output path URI (expected r2://): {uri}")
        remainder = value[len("r2://") :]
        if "/" not in remainder:
            return remainder, ""
        bucket, key = remainder.split("/", 1)
        return bucket, key

    def _sync_prefix_to_local(self, prefix: str, destination: Path) -> bool:
        methods = [
            lambda: self.r2_client.sync_down(prefix, str(destination)),
            lambda: self.r2_client.sync_prefix_to_local(prefix=prefix, local_dir=str(destination)),
        ]
        for method in methods:
            try:
                result = method()
            except AttributeError:
                continue
            if result is None:
                return True
            if isinstance(result, list):
                return bool(result)
            if isinstance(result, dict):
                return int(result.get("downloaded", 0)) > 0
            return bool(result)
        return False

    def _list_keys(self, prefix: str) -> list[str]:
        if hasattr(self.r2_client, "list_keys"):
            return [str(k) for k in self.r2_client.list_keys(prefix)]
        return []

    def _r2_key_exists(self, key: str) -> bool:
        methods = [
            lambda: self.r2_client.file_exists(key),
            lambda: self.r2_client.exists(key),
        ]
        for method in methods:
            try:
                return bool(method())
            except AttributeError:
                continue
        return False

    def _download_one_file(self, key: str, target: Path) -> None:
        methods = [
            lambda: self.r2_client.download_file(key, str(target)),
            lambda: self.r2_client.download_file(remote_key=key, local_path=str(target)),
        ]
        for method in methods:
            try:
                method()
                return
            except AttributeError:
                break
            except TypeError:
                continue
        raise RuntimeError("R2 client does not expose a compatible download_file method")

    def _load_examples(self, packet_paths: list[Path]) -> list[tuple[str, str]]:
        examples: list[tuple[str, str]] = []
        for packet_path in packet_paths:
            suffix = packet_path.suffix.lower()
            if suffix == ".jsonl":
                examples.extend(self._examples_from_jsonl(packet_path))
            elif suffix == ".json":
                examples.extend(self._examples_from_json(packet_path))
            else:
                logger.warning("Skipping unsupported packet extension: %s", packet_path)
        return examples

    @staticmethod
    def _examples_from_jsonl(path: Path) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL line in {path}:{line_number}: {exc.msg}") from exc
                pair = TrainRunner._extract_example_pair(payload)
                if pair is not None:
                    rows.append(pair)
        return rows

    @staticmethod
    def _examples_from_json(path: Path) -> list[tuple[str, str]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records: list[Any]
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = [payload]
        else:
            return []
        rows: list[tuple[str, str]] = []
        for record in records:
            pair = TrainRunner._extract_example_pair(record)
            if pair is not None:
                rows.append(pair)
        return rows

    @staticmethod
    def _extract_example_pair(payload: Any) -> tuple[str, str] | None:
        if not isinstance(payload, dict):
            return None
        candidates = [("prompt", "completion"), ("instruction", "output"), ("input", "response")]
        for prompt_key, completion_key in candidates:
            prompt = payload.get(prompt_key)
            completion = payload.get(completion_key)
            if isinstance(prompt, str) and isinstance(completion, str) and prompt.strip():
                return prompt.strip(), completion
        return None


def _run_monitor_forever() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    runner = TrainRunner()
    logger.info("Starting TrainRunner monitor loop interval=30s")
    try:
        while True:
            try:
                runner.monitor_jobs()
            except Exception as exc:
                logger.exception("monitor_jobs iteration failed: %s", exc)
            time.sleep(30)
    finally:
        runner.close()


if __name__ == "__main__":
    _run_monitor_forever()

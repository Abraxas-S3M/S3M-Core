"""S3M Hybrid Training Orchestrator — RunPod GPU ↔ Hetzner CPU Bridge.

Military/tactical context:
Coordinates the two-stage adaptation ladder:
  - Stage 1 (CPU) emits and validates candidate adapters.
  - Stage 2 (GPU) refines only cpu_cleared adapters and re-validates before
    promotion to mission artifact vault paths.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.storage.object_storage import ObjectStorageConnector
from src.storage.vault_paths import VaultPaths
from src.training.cloud_cpu.contracts import CheckpointMeta
from src.training.cloud_cpu.promotion_gate import PromotionGate
from src.training.validation.grok_oracle import GrokValidationOracle, VerdictRequest

logger = logging.getLogger("s3m.training.gpu.hybrid_orchestrator")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PROMOTED = "promoted"


class JobType(str, Enum):
    LORA_FINETUNE = "lora_finetune"
    QLORA_FINETUNE = "qlora_finetune"
    DPO_TRAINING = "dpo_training"
    FULL_FINETUNE = "full_finetune"
    EVAL_ONLY = "eval_only"


@dataclass
class TrainingJob:
    job_id: str
    engine_id: str
    job_type: JobType
    dataset_path: str
    status: JobStatus = JobStatus.PENDING
    priority: int = 5  # 1=highest, 10=lowest
    max_steps: int = 2000
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    adapter_path: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    resume_from: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingJob":
        payload = dict(data)
        payload["status"] = JobStatus(payload.get("status", "pending"))
        payload["job_type"] = JobType(payload.get("job_type", "qlora_finetune"))
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


class JobQueue:
    """Filesystem-based job queue for hybrid training orchestration."""

    def __init__(self, queue_dir: str = "state/training/job_queue") -> None:
        self.root = Path(queue_dir)
        for status in JobStatus:
            (self.root / status.value).mkdir(parents=True, exist_ok=True)

    def submit(self, job: TrainingJob) -> str:
        job.status = JobStatus.PENDING
        path = self.root / "pending" / f"{job.job_id}.json"
        path.write_text(json.dumps(job.to_dict(), indent=2, default=str), encoding="utf-8")
        logger.info("Job submitted: %s engine=%s type=%s", job.job_id, job.engine_id, job.job_type.value)
        return job.job_id

    def claim_next(self) -> Optional[TrainingJob]:
        """Claim the highest-priority pending job (FIFO within priority)."""
        pending_dir = self.root / "pending"
        candidates = sorted(pending_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        jobs = []
        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                jobs.append((path, TrainingJob.from_dict(data)))
            except Exception:
                continue
        if not jobs:
            return None

        jobs.sort(key=lambda x: x[1].priority)
        path, job = jobs[0]

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc).isoformat()
        dest = self.root / "running" / path.name
        dest.write_text(json.dumps(job.to_dict(), indent=2, default=str), encoding="utf-8")
        path.unlink()
        logger.info("Job claimed: %s", job.job_id)
        return job

    def complete(self, job: TrainingJob, success: bool = True) -> None:
        running_path = self.root / "running" / f"{job.job_id}.json"
        job.status = JobStatus.COMPLETED if success else JobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc).isoformat()
        target_dir = self.root / job.status.value
        dest = target_dir / f"{job.job_id}.json"
        dest.write_text(json.dumps(job.to_dict(), indent=2, default=str), encoding="utf-8")
        if running_path.exists():
            running_path.unlink()
        logger.info("Job %s: %s", job.status.value, job.job_id)

    def list_jobs(self, status: Optional[JobStatus] = None) -> List[TrainingJob]:
        jobs = []
        dirs = [self.root / status.value] if status else [self.root / s.value for s in JobStatus]
        for d in dirs:
            for path in d.glob("*.json"):
                try:
                    jobs.append(TrainingJob.from_dict(json.loads(path.read_text(encoding="utf-8"))))
                except Exception:
                    continue
        return sorted(jobs, key=lambda j: j.created_at)

    def get_status(self) -> Dict[str, int]:
        return {s.value: len(list((self.root / s.value).glob("*.json"))) for s in JobStatus}


class CheckpointSyncer:
    """Sync checkpoints between GPU and CPU nodes via object storage vault."""

    def __init__(
        self,
        gpu_checkpoint_dir: str = "checkpoints/gpu",
        cpu_checkpoint_dir: str = "/opt/s3m/state/training",
        connector: Optional[Any] = None,
    ) -> None:
        self.gpu_dir = Path(gpu_checkpoint_dir)
        self.cpu_dir = cpu_checkpoint_dir
        if connector is not None:
            self.connector = connector
            return
        try:
            self.connector = ObjectStorageConnector()
        except Exception:
            self.connector = ObjectStorageConnector(emulation_root=Path("state/training/object-storage"))

    def push_to_vault(self, adapter_path: str, engine_id: str, track: str) -> bool:
        """Push completed adapter from GPU pod to object storage vault."""
        return bool(self.push_to_vault_with_keys(adapter_path, engine_id, track))

    def push_to_vault_with_keys(self, adapter_path: str, engine_id: str, track: str) -> List[str]:
        remote_prefix = VaultPaths.fp16_adapter(engine_id, track)
        local_path = Path(adapter_path)
        try:
            if local_path.is_file():
                destination_key = f"{remote_prefix}{local_path.name}"
                if hasattr(self.connector, "upload_file"):
                    self.connector.upload_file(str(local_path), destination_key)
                elif hasattr(self.connector, "put_bytes"):
                    self.connector.put_bytes(destination_key, local_path.read_bytes())
                else:
                    raise AttributeError("Object storage connector does not support file upload")
                return [destination_key]

            if hasattr(self.connector, "sync_up"):
                uploaded = self.connector.sync_up(str(local_path), remote_prefix)
                if isinstance(uploaded, list):
                    return [str(item) for item in uploaded]
                return []
            if hasattr(self.connector, "sync_local_to_prefix"):
                self.connector.sync_local_to_prefix(local_dir=str(local_path), prefix=remote_prefix)
                return []
        except Exception as exc:
            logger.error("Vault push failed: %s", exc)
            return []
        return []

    def pull_from_vault(self, engine_id: str, track: str, local_path: str) -> bool:
        """Pull checkpoint/adapter from object storage to local path."""
        remote = VaultPaths.fp16_adapter(engine_id, track)
        try:
            if hasattr(self.connector, "sync_down"):
                self.connector.sync_down(remote, local_path)
                return True
            if hasattr(self.connector, "sync_prefix_to_local"):
                self.connector.sync_prefix_to_local(prefix=remote, local_dir=local_path)
                return True
            return False
        except Exception as exc:
            logger.error("Vault pull failed: %s", exc)
            return False


class HybridOrchestrator:
    """Top-level coordinator for hybrid GPU/CPU training."""

    def __init__(
        self,
        queue_dir: str = "state/training/job_queue",
        mode: str = "cpu",  # "cpu" = Hetzner side, "gpu" = RunPod side
        config_path: str = "configs/gpu_training.yaml",
        oracle: Optional[GrokValidationOracle] = None,
        promotion_gate: Optional[PromotionGate] = None,
        object_storage_connector: Optional[Any] = None,
        trainer_factory: Optional[Any] = None,
    ) -> None:
        self.queue = JobQueue(queue_dir)
        self._config = self._load_config(config_path)
        self.syncer = CheckpointSyncer(connector=object_storage_connector)
        self._storage = self.syncer.connector
        self._oracle = oracle or GrokValidationOracle(mode="offline", object_storage_connector=self._storage)
        self._promotion_gate = promotion_gate or PromotionGate(config_path=Path("configs/training/promotion_gate.yaml"))
        self._last_promoted_by_track: Dict[str, Dict[str, Any]] = {}
        self._trainer_factory = trainer_factory

        stage_cfg = self._config.get("hybrid", {}).get("stage_pipeline", {})
        self._artifact_prefix = str(stage_cfg.get("artifact_prefix", "training/artifacts")).strip("/")
        self._recycle_prefix = str(stage_cfg.get("recycle_prefix", "training/stage1/recycle")).strip("/")
        self._cpu_cleared_prefix = str(stage_cfg.get("cpu_cleared_prefix", "training/stage1/cpu_cleared")).strip("/")
        self.mode = mode

    def submit_training_job(
        self,
        engine_id: str,
        dataset_path: str,
        job_type: str = "qlora_finetune",
        max_steps: int = 2000,
        priority: int = 5,
        track: str = "saudi_mod",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """CPU-side: submit a new training job for the GPU."""
        merged_metadata = {"track": str(track)}
        if isinstance(metadata, dict):
            merged_metadata.update(metadata)
        job = TrainingJob(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            engine_id=engine_id,
            job_type=JobType(job_type),
            dataset_path=dataset_path,
            max_steps=max_steps,
            priority=priority,
            metadata=merged_metadata,
        )
        return self.queue.submit(job)

    def queue_cpu_cleared_adapter(
        self,
        engine_id: str,
        track: str,
        cpu_adapter_key: str,
        session_id: str,
        dataset_path: str,
        metadata: Optional[Dict[str, Any]] = None,
        max_steps: int = 2000,
        priority: int = 3,
    ) -> str:
        """Queue a Stage-2 GPU refinement job for a cpu_cleared adapter."""
        merged_metadata = {
            "track": str(track),
            "status_tag": "cpu_cleared",
            "cpu_adapter_key": str(cpu_adapter_key),
            "session_id": str(session_id),
            "stage": "stage_2_gpu_refinement",
        }
        if isinstance(metadata, dict):
            merged_metadata.update(metadata)
        return self.submit_training_job(
            engine_id=engine_id,
            dataset_path=dataset_path,
            job_type=JobType.QLORA_FINETUNE.value,
            max_steps=max_steps,
            priority=priority,
            track=track,
            metadata=merged_metadata,
        )

    def gpu_poll_and_run(self) -> Optional[Dict[str, Any]]:
        """GPU-side: claim next job, run training, validate stage-2 promotion."""
        job = self.queue.claim_next()
        if not job:
            return None

        try:
            trainer = self._build_trainer(job.engine_id)
            metrics = trainer.train(
                dataset_path=job.dataset_path,
                resume_from=job.resume_from,
            )
            job.adapter_path = metrics.get("adapter_path")
            job.metrics = dict(metrics)

            stage2_result: Dict[str, Any] = {"state": "training_completed", "promoted": False}
            if job.adapter_path:
                track = str(job.metadata.get("track", "saudi_mod"))
                uploaded_keys = self.syncer.push_to_vault_with_keys(job.adapter_path, job.engine_id, track)
                job.metadata["enhanced_adapter_keys"] = uploaded_keys
                if str(job.metadata.get("status_tag", "")).strip() == "cpu_cleared":
                    stage2_result = self._run_stage_two_validation(job=job, uploaded_keys=uploaded_keys)
            metrics["stage2"] = stage2_result

            self.queue.complete(job, success=True)
            return {"job_id": job.job_id, **metrics}

        except Exception as exc:
            job.error = str(exc)
            self.queue.complete(job, success=False)
            logger.exception("Training job failed: %s", job.job_id)
            return {"job_id": job.job_id, "error": str(exc)}

    def _run_stage_two_validation(self, job: TrainingJob, uploaded_keys: List[str]) -> Dict[str, Any]:
        track = str(job.metadata.get("track", "saudi_mod"))
        session_id = str(job.metadata.get("session_id", f"gpu-{job.job_id}"))
        enhanced_key = self._select_primary_adapter_key(uploaded_keys=uploaded_keys)
        if not enhanced_key:
            feedback = self._recycle_to_stage_one(
                job=job,
                enhanced_adapter_key="",
                verdict_score=0.0,
                verdict_reason="GPU refinement produced no uploadable adapter artifact",
                gate_reason="missing_enhanced_adapter",
            )
            return {
                "state": "recycled",
                "promoted": False,
                "reason": "missing enhanced adapter",
                "recycle_feedback_key": feedback,
            }

        request = VerdictRequest(
            artifact_id=f"{job.job_id}-stage2",
            engine_id=job.engine_id,
            track=track,
            artifact_type="adapter",
            object_key=enhanced_key,
            session_id=session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._write_json(
            f"grok-verdicts/pending/{job.job_id}-stage2.request.json",
            {**asdict(request), "validation_stage": "gpu_stage2"},
        )
        verdict = self._oracle.evaluate_artifact(request, validation_stage="gpu_stage2")
        gate_passed, gate_reason = self._promotion_gate_passed(job=job, score=verdict.score)
        passed = bool(verdict.passed) and gate_passed
        if passed:
            promoted = self._promote_to_artifact_vault(job=job, enhanced_adapter_key=enhanced_key, verdict=verdict)
            return {
                "state": "promoted",
                "promoted": True,
                "artifact_key": promoted["artifact_key"],
                "metadata_key": promoted["metadata_key"],
                "grok_score": float(verdict.score),
            }

        feedback_key = self._recycle_to_stage_one(
            job=job,
            enhanced_adapter_key=enhanced_key,
            verdict_score=float(verdict.score),
            verdict_reason=verdict.reason,
            gate_reason=gate_reason,
        )
        return {
            "state": "recycled",
            "promoted": False,
            "grok_score": float(verdict.score),
            "reason": verdict.reason,
            "promotion_gate_reason": gate_reason,
            "recycle_feedback_key": feedback_key,
        }

    def _promotion_gate_passed(self, job: TrainingJob, score: float) -> tuple[bool, str]:
        track = str(job.metadata.get("track", "saudi_mod"))
        step = int(job.metadata.get("cpu_step", 0) or job.metrics.get("global_step", 0) or job.max_steps)
        checkpoint = CheckpointMeta(
            checkpoint_id=job.job_id,
            track=track,
            step=step,
            epoch=0,
        )
        decision = self._promotion_gate.evaluate(
            checkpoint_meta=checkpoint,
            eval_results={"overall": float(score), "grok_score": float(score)},
            last_promoted_results=self._last_promoted_by_track.get(track),
        )
        if decision.passed:
            self._last_promoted_by_track[track] = {
                "step": step,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "eval_scores": {"overall": float(score), "grok_score": float(score)},
            }
        return bool(decision.passed), str(decision.reason)

    def _promote_to_artifact_vault(self, job: TrainingJob, enhanced_adapter_key: str, verdict: Any) -> Dict[str, str]:
        track = str(job.metadata.get("track", "saudi_mod"))
        engine = str(job.engine_id)
        session_id = str(job.metadata.get("session_id", f"gpu-{job.job_id}"))
        timestamp = datetime.now(timezone.utc).isoformat()

        destination_prefix = f"{self._artifact_prefix}/{track}/{engine}".strip("/")
        artifact_name = Path(enhanced_adapter_key).name or f"{job.job_id}.adapter.bin"
        destination_key = f"{destination_prefix}/{artifact_name}"
        self._copy_object(enhanced_adapter_key, destination_key)

        metadata = {
            "track": track,
            "engine": engine,
            "session_id": session_id,
            "grok_score": float(verdict.score),
            "timestamp": timestamp,
            "job_id": job.job_id,
            "source_adapter_key": enhanced_adapter_key,
            "artifact_key": destination_key,
            "validation_stage": "gpu_stage2",
        }
        metadata_key = f"{destination_prefix}/{Path(artifact_name).stem}.metadata.json"
        self._write_json(metadata_key, metadata)
        logger.info("Promoted enhanced adapter to artifact vault: %s", destination_key)
        return {"artifact_key": destination_key, "metadata_key": metadata_key}

    def _recycle_to_stage_one(
        self,
        job: TrainingJob,
        enhanced_adapter_key: str,
        verdict_score: float,
        verdict_reason: str,
        gate_reason: str,
    ) -> str:
        track = str(job.metadata.get("track", "saudi_mod"))
        engine = str(job.engine_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        feedback_key = f"{self._recycle_prefix}/{track}/{engine}/{job.job_id}-{timestamp}.json".strip("/")
        payload = {
            "job_id": job.job_id,
            "track": track,
            "engine": engine,
            "session_id": str(job.metadata.get("session_id", f"gpu-{job.job_id}")),
            "status": "recycle_stage_1",
            "source": str(job.metadata.get("cpu_adapter_key", self._cpu_cleared_prefix)),
            "enhanced_adapter_key": enhanced_adapter_key,
            "grok_score": float(verdict_score),
            "reason": verdict_reason,
            "promotion_gate_reason": gate_reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(feedback_key, payload)
        logger.info("Recycled enhanced adapter back to stage-1 feedback queue: %s", feedback_key)
        return feedback_key

    @staticmethod
    def _select_primary_adapter_key(uploaded_keys: List[str]) -> str:
        candidates = [str(item) for item in uploaded_keys if str(item).strip()]
        if candidates:
            non_tokenizer = [item for item in candidates if "tokenizer" not in item.lower()]
            return non_tokenizer[0] if non_tokenizer else candidates[0]
        return ""

    def _build_trainer(self, engine_id: str) -> Any:
        if self._trainer_factory is not None:
            return self._trainer_factory(engine_id)
        from src.training.gpu.lora_trainer import S3MLoRATrainer

        return S3MLoRATrainer(engine_id=engine_id)

    def _copy_object(self, source_key: str, destination_key: str) -> None:
        if hasattr(self._storage, "copy"):
            self._storage.copy(source_key, destination_key)
            return
        if hasattr(self._storage, "copy_object"):
            self._storage.copy_object(source_key, destination_key)
            return
        payload = self._read_bytes(source_key)
        self._write_bytes(destination_key, payload)

    def _write_json(self, key: str, payload: Dict[str, Any]) -> None:
        if hasattr(self._storage, "put_json"):
            self._storage.put_json(key, payload)
            return
        if hasattr(self._storage, "write_json"):
            self._storage.write_json(key, payload)
            return
        if hasattr(self._storage, "upload_json"):
            self._storage.upload_json(key, payload)
            return
        self._write_bytes(key, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _read_bytes(self, key: str) -> bytes:
        if hasattr(self._storage, "get_bytes"):
            return self._storage.get_bytes(key)
        if hasattr(self._storage, "read_bytes"):
            return self._storage.read_bytes(key)
        raise AttributeError("Object storage connector does not support byte reads")

    def _write_bytes(self, key: str, payload: bytes) -> None:
        if hasattr(self._storage, "put_bytes"):
            self._storage.put_bytes(key, payload)
            return
        if hasattr(self._storage, "upload_bytes"):
            self._storage.upload_bytes(key, payload)
            return
        raise AttributeError("Object storage connector does not support byte writes")

    @staticmethod
    def _load_config(config_path: str) -> Dict[str, Any]:
        path = Path(config_path)
        if not path.exists():
            return {}
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return parsed if isinstance(parsed, dict) else {}

    def get_dashboard(self) -> Dict[str, Any]:
        """Return queue status for monitoring."""
        return {
            "queue": self.queue.get_status(),
            "jobs": [j.to_dict() for j in self.queue.list_jobs()],
            "mode": self.mode,
        }

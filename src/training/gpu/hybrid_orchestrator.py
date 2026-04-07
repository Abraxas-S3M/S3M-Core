"""S3M Hybrid Training Orchestrator — RunPod GPU ↔ Hetzner CPU Bridge.

Military/tactical context:
Coordinates training workloads between RunPod 4090 GPUs (fine-tuning) and
Hetzner CCX CPUs (data prep, eval, merge, GGUF conversion, serving).
Uses a filesystem-based job queue for simplicity and air-gap compatibility.

Job lifecycle:
  1. CPU submits training job → queue/pending/
  2. GPU polls, claims job     → queue/running/
  3. GPU completes, writes adapter → queue/completed/
  4. CPU picks up adapter, runs eval, merges if promoted

Checkpoint sync via rsync over SSH (bidirectional).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        data["status"] = JobStatus(data.get("status", "pending"))
        data["job_type"] = JobType(data.get("job_type", "qlora_finetune"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


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
    """Sync checkpoints between RunPod GPU and Hetzner CPU via rsync/SSH."""

    def __init__(
        self,
        remote_host: str = "",
        remote_user: str = "root",
        ssh_key: str = "",
        gpu_checkpoint_dir: str = "checkpoints/gpu",
        cpu_checkpoint_dir: str = "/opt/s3m/state/training",
    ) -> None:
        self.remote_host = remote_host or os.environ.get("S3M_HETZNER_HOST", "")
        self.remote_user = remote_user
        self.ssh_key = ssh_key or os.environ.get("S3M_HETZNER_SSH_KEY", "~/.ssh/s3m_hetzner")
        self.gpu_dir = Path(gpu_checkpoint_dir)
        self.cpu_dir = cpu_checkpoint_dir

    def push_to_cpu(self, adapter_path: str) -> bool:
        """Push completed adapter from GPU pod to Hetzner CPU."""
        if not self.remote_host:
            logger.warning("No HETZNER_HOST configured; skipping sync")
            return False
        src = Path(adapter_path).resolve()
        dest = f"{self.remote_user}@{self.remote_host}:{self.cpu_dir}/adapters/{src.name}"
        return self._rsync(str(src) + "/", dest)

    def pull_from_cpu(self, remote_path: str, local_path: str) -> bool:
        """Pull dataset or checkpoint from Hetzner to GPU pod."""
        if not self.remote_host:
            return False
        src = f"{self.remote_user}@{self.remote_host}:{remote_path}"
        return self._rsync(src, local_path)

    def _rsync(self, src: str, dest: str) -> bool:
        cmd = [
            "rsync", "-avz", "--progress",
            "-e", f"ssh -i {self.ssh_key} -o StrictHostKeyChecking=no",
            src, dest,
        ]
        logger.info("Sync: %s → %s", src, dest)
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.error("Sync failed: %s", exc)
            return False


class HybridOrchestrator:
    """Top-level coordinator for hybrid GPU/CPU training."""

    def __init__(
        self,
        queue_dir: str = "state/training/job_queue",
        mode: str = "cpu",  # "cpu" = Hetzner side, "gpu" = RunPod side
    ) -> None:
        self.queue = JobQueue(queue_dir)
        self.syncer = CheckpointSyncer()
        self.mode = mode

    def submit_training_job(
        self,
        engine_id: str,
        dataset_path: str,
        job_type: str = "qlora_finetune",
        max_steps: int = 2000,
        priority: int = 5,
    ) -> str:
        """CPU-side: submit a new training job for the GPU."""
        job = TrainingJob(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            engine_id=engine_id,
            job_type=JobType(job_type),
            dataset_path=dataset_path,
            max_steps=max_steps,
            priority=priority,
        )
        return self.queue.submit(job)

    def gpu_poll_and_run(self) -> Optional[Dict[str, Any]]:
        """GPU-side: claim next job, run training, report results."""
        job = self.queue.claim_next()
        if not job:
            return None

        try:
            from src.training.gpu.lora_trainer import S3MLoRATrainer

            trainer = S3MLoRATrainer(engine_id=job.engine_id)
            metrics = trainer.train(
                dataset_path=job.dataset_path,
                resume_from=job.resume_from,
            )
            job.adapter_path = metrics.get("adapter_path")
            job.metrics = metrics

            # Sync adapter back to CPU
            if job.adapter_path:
                self.syncer.push_to_cpu(job.adapter_path)

            self.queue.complete(job, success=True)
            return metrics

        except Exception as exc:
            job.error = str(exc)
            self.queue.complete(job, success=False)
            logger.exception("Training job failed: %s", job.job_id)
            return {"job_id": job.job_id, "error": str(exc)}

    def get_dashboard(self) -> Dict[str, Any]:
        """Return queue status for monitoring."""
        return {
            "queue": self.queue.get_status(),
            "jobs": [j.to_dict() for j in self.queue.list_jobs()],
            "mode": self.mode,
        }

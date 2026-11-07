"""Persistent private-network vLLM adapter for Le Chonk planning role."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from src.integrations.lechonk.circuit_breaker import CircuitBreaker
from src.llm_core.backends.vllm_backend import VllmBackend

logger = logging.getLogger("s3m.lechonk.planning_backend")


def _sanitize_error_message(message: str) -> str:
    text = (message or "").strip()
    if len(text) > 240:
        text = text[:237] + "..."
    return text or "inference_error"


@dataclass
class PlanningJob:
    job_id: str
    prompt: str
    created_at: float
    status: str = "queued"
    result_text: Optional[str] = None
    error: Optional[str] = None


class LeChonkPlanningBackend:
    """
    Wraps VllmBackend with concurrency limits, timeouts, and a circuit breaker.

    Does not connect to quarantined weights directly; expects a private endpoint
    configured via environment / vault (never public internet).
    """

    def __init__(
        self,
        backend: VllmBackend,
        *,
        max_concurrent: int = 2,
        request_timeout_s: Optional[float] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        idempotency_cache: Optional[Dict[str, str]] = None,
    ) -> None:
        self._backend = backend
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrent))
        self._breaker = circuit_breaker or CircuitBreaker()
        self._timeout_s = float(request_timeout_s or backend.config.get("request_timeout_s", 120.0))
        self._jobs: Dict[str, PlanningJob] = {}
        self._idempotency: Dict[str, str] = idempotency_cache if idempotency_cache is not None else {}
        self._lock = threading.Lock()
        self.inference_verified: bool = False

    @classmethod
    def from_vllm_config(cls, model_name: str, config: Dict[str, Any]) -> LeChonkPlanningBackend:
        merged = dict(config)
        merged.setdefault("task_type", "planning")
        merged.setdefault("model_name", model_name)
        merged.setdefault("max_output_tokens_by_task", {"planning": int(merged.get("max_tokens", 1024))})
        backend = VllmBackend(model_path=model_name, config=merged)
        return cls(
            backend,
            max_concurrent=int(merged.get("max_concurrent_requests", 2)),
            request_timeout_s=float(merged.get("request_timeout_s", 120.0)),
        )

    def load(self) -> bool:
        return bool(self._backend.load())

    def health_check(self) -> Dict[str, Any]:
        if not self._breaker.allow_request():
            return {"reachable": False, "reason": "circuit_open", "breaker": self._breaker.state.value}
        health = self._backend.health_check()
        if health.get("reachable"):
            self._breaker.record_success()
        else:
            self._breaker.record_failure()
        health["breaker"] = self._breaker.state.value
        return health

    def submit_async(self, prompt: str, *, idempotency_key: Optional[str] = None) -> PlanningJob:
        key = idempotency_key or ""
        if key:
            cached = self._idempotency.get(key)
            if cached:
                existing = self._jobs.get(cached)
                if existing:
                    return existing
        job_id = f"lechonk-{uuid.uuid4().hex[:12]}"
        job = PlanningJob(job_id=job_id, prompt=prompt, created_at=time.time())
        with self._lock:
            self._jobs[job_id] = job
            if key:
                self._idempotency[key] = job_id
        return job

    def run_job(self, job: PlanningJob) -> PlanningJob:
        if not self._breaker.allow_request():
            job.status = "rejected"
            job.error = "circuit_open"
            return job
        if not self._backend.is_loaded:
            job.status = "failed"
            job.error = "backend_not_loaded"
            self._breaker.record_failure()
            return job

        acquired = self._semaphore.acquire(timeout=self._timeout_s)
        if not acquired:
            job.status = "failed"
            job.error = "concurrency_timeout"
            self._breaker.record_failure()
            return job
        try:
            job.status = "running"
            result = self._backend.generate(job.prompt, max_tokens=int(self._backend.config.get("max_tokens", 512)))
            if result.get("success"):
                job.status = "completed"
                job.result_text = str(result.get("text") or "")
                self._breaker.record_success()
            else:
                job.status = "failed"
                job.error = _sanitize_error_message(str(result.get("error") or "generate_failed"))
                self._breaker.record_failure()
        except Exception as exc:  # pragma: no cover - defensive
            job.status = "failed"
            job.error = _sanitize_error_message(str(exc))
            logger.warning("Le Chonk planning job failed: %s", job.error)
            self._breaker.record_failure()
        finally:
            self._semaphore.release()
        return job

    def generate_planning(self, prompt: str, *, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Synchronous planning call with audit-friendly metadata (no fabricated success)."""
        job = self.submit_async(prompt, idempotency_key=idempotency_key)
        job = self.run_job(job)
        provenance = {
            "backend": "vllm",
            "model_path": self._backend.model_path,
            "human_review_required": True,
            "inference_verified": self.inference_verified,
            "job_id": job.job_id,
        }
        if job.status != "completed":
            return {
                "success": False,
                "error": job.error or job.status,
                "provenance": provenance,
            }
        return {
            "success": True,
            "text": job.result_text or "",
            "provenance": provenance,
        }

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in {"completed", "failed", "rejected"}:
                return False
            job.status = "cancelled"
            job.error = "cancelled"
            return True

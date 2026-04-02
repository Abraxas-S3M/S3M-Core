"""
Live engine runtime adapter for the S3M unified quad-engine pipeline.

This module replaces simulated output generation by executing real engine
queries through EnginePool and returning structured mission artifacts.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from threading import RLock
from typing import Dict, Iterable, Optional, Union

from .engine_output import (
    EngineHealth,
    StructuredEngineOutput,
    parse_raw_text_to_structured,
)
from .engine_pool import EnginePool
from .engine_registry import EngineID
from .inference_engine import InferenceResult


class EngineRuntimeAdapter:
    """
    Runtime adapter that bridges EnginePool results into structured outputs.

    Tactical context:
    - This adapter enforces live execution semantics and never emits synthetic
      mission recommendations that could mask degraded compute reality.
    """

    def __init__(self, *, max_workers: int = 4, timeout_seconds: float = 20.0) -> None:
        self.max_workers = max(1, int(max_workers))
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._pool_lock = RLock()
        self._pool: Optional[EnginePool] = None

    def _get_pool(self) -> EnginePool:
        """Lazily initialize EnginePool to avoid eager model initialization cost."""
        if self._pool is not None:
            return self._pool
        with self._pool_lock:
            if self._pool is None:
                self._pool = EnginePool()
            return self._pool

    def execute_engines(
        self,
        *,
        engine_ids: Iterable[Union[EngineID, str]],
        prompt: str,
        task_id: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[Union[EngineID, str], StructuredEngineOutput]:
        """
        Execute multiple engines in parallel and return structured outputs.

        Returns:
            Mapping from original engine identifier object to structured output.
        """
        ids = list(engine_ids)
        if not ids:
            return {}

        pool = self._get_pool()
        timeout = self.timeout_seconds if timeout_seconds is None else max(0.1, timeout_seconds)
        by_future = {}
        outputs: Dict[Union[EngineID, str], StructuredEngineOutput] = {}
        max_workers = min(self.max_workers, len(ids))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for requested_id in ids:
                canonical = self._to_engine_id(requested_id)
                if canonical is None:
                    outputs[requested_id] = StructuredEngineOutput(
                        engine_id=str(requested_id),
                        task_id=task_id,
                        raw_text=f"[ERROR] Unknown engine id: {requested_id}",
                        health=EngineHealth.ERROR,
                        confidence=0.0,
                        metadata={"error": "unknown_engine_id"},
                    )
                    continue
                future = executor.submit(
                    pool.query_engine,
                    canonical,
                    prompt,
                    system_prompt,
                    max_tokens,
                    temperature,
                )
                by_future[future] = (requested_id, canonical)

            # Process results as futures complete and convert each into the
            # canonical structured schema used by reconciliation.
            try:
                for future in as_completed(by_future, timeout=timeout):
                    requested_id, canonical = by_future[future]
                    try:
                        result = future.result(timeout=0)
                    except TimeoutError:
                        outputs[requested_id] = StructuredEngineOutput(
                            engine_id=canonical.value,
                            task_id=task_id,
                            raw_text=f"[ERROR] Timeout querying {canonical.value}",
                            health=EngineHealth.TIMEOUT,
                            confidence=0.0,
                            metadata={"error": "timeout"},
                        )
                        continue
                    except Exception as exc:  # pragma: no cover - defensive runtime path
                        outputs[requested_id] = StructuredEngineOutput(
                            engine_id=canonical.value,
                            task_id=task_id,
                            raw_text=f"[ERROR] Runtime failure: {exc}",
                            health=EngineHealth.ERROR,
                            confidence=0.0,
                            metadata={"error": "runtime_exception", "detail": str(exc)},
                        )
                        continue

                    outputs[requested_id] = self._wrap_inference_result(
                        inference=result,
                        task_id=task_id,
                    )
            except TimeoutError:
                # Remaining futures are materialized below as timeout outputs.
                pass

        # Any future not completed before timeout gets graceful timeout output.
        for future, (requested_id, canonical) in by_future.items():
            if requested_id in outputs:
                continue
            if not future.done():
                future.cancel()
                outputs[requested_id] = StructuredEngineOutput(
                    engine_id=canonical.value,
                    task_id=task_id,
                    raw_text=f"[ERROR] Timeout querying {canonical.value}",
                    health=EngineHealth.TIMEOUT,
                    confidence=0.0,
                    metadata={"error": "timeout"},
                )
        return outputs

    def _wrap_inference_result(
        self,
        *,
        inference: InferenceResult,
        task_id: str,
    ) -> StructuredEngineOutput:
        """Convert InferenceResult into StructuredEngineOutput."""
        response_text = (inference.response or "").strip()
        lowered = response_text.lower()

        if "not loaded" in lowered:
            return StructuredEngineOutput(
                engine_id=inference.engine_id.value,
                task_id=task_id,
                raw_text=response_text,
                health=EngineHealth.NOT_LOADED,
                confidence=0.0,
                latency_ms=float(inference.latency_ms),
                tokens_generated=int(inference.tokens_generated),
                metadata={
                    "model_name": inference.model_name,
                    "prompt_tokens": int(inference.prompt_tokens),
                    "tokens_per_second": float(inference.tokens_per_second),
                },
            )

        if response_text.startswith("[ERROR]"):
            return StructuredEngineOutput(
                engine_id=inference.engine_id.value,
                task_id=task_id,
                raw_text=response_text,
                health=EngineHealth.ERROR,
                confidence=0.0,
                latency_ms=float(inference.latency_ms),
                tokens_generated=int(inference.tokens_generated),
                metadata={
                    "model_name": inference.model_name,
                    "prompt_tokens": int(inference.prompt_tokens),
                    "tokens_per_second": float(inference.tokens_per_second),
                },
            )

        structured = parse_raw_text_to_structured(
            response_text,
            engine_id=inference.engine_id.value,
            task_id=task_id,
            health=EngineHealth.HEALTHY,
            base_confidence=0.72,
            metadata={
                "model_name": inference.model_name,
                "prompt_tokens": int(inference.prompt_tokens),
                "tokens_per_second": float(inference.tokens_per_second),
            },
        )
        structured.latency_ms = float(inference.latency_ms)
        structured.tokens_generated = int(inference.tokens_generated)
        return structured

    @staticmethod
    def _to_engine_id(engine_id: Union[EngineID, str]) -> Optional[EngineID]:
        """Normalize user-provided identifier into EngineID."""
        if isinstance(engine_id, EngineID):
            return engine_id
        if isinstance(engine_id, str):
            for item in EngineID:
                if engine_id == item.value:
                    return item
        return None

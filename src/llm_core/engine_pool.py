"""
S3M Engine Pool
Manages all four inference engines as a pool.
Handles loading, unloading, and parallel query execution.
"""

import time
import logging
from typing import Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from .engine_registry import EngineID, TaskDomain, DOMAIN_ROUTING
from .failover_system import FailoverSystem
from .inference_engine import InferenceEngine, InferenceResult
from .model_registry import ModelRegistry
from .predictive_preload import PredictivePreloader

logger = logging.getLogger("s3m.pool")


class EnginePool:
    """
    Holds all four InferenceEngine instances.
    Supports single-engine queries and multi-engine consensus.
    """

    def __init__(
        self,
        n_gpu_layers: int = -1,
        preloader: Optional[PredictivePreloader] = None,
        model_registry: Optional[ModelRegistry] = None,
        failover: Optional[FailoverSystem] = None,
    ):
        self.n_gpu_layers = n_gpu_layers
        self.engines: Dict[EngineID, InferenceEngine] = {}
        self.preloader = preloader or PredictivePreloader()
        self.model_registry = model_registry or ModelRegistry()
        self.failover = failover or FailoverSystem()
        self._initialize_engines()
        logger.info("EnginePool initialized with Failover & Preload support")

    def _initialize_engines(self):
        for engine_id in EngineID:
            self.engines[engine_id] = InferenceEngine(
                engine_id=engine_id,
                n_gpu_layers=self.n_gpu_layers,
            )
            logger.info(f"Initialized engine slot: {engine_id.value}")

    def load_engine(self, engine_id: EngineID) -> bool:
        engine = self.engines.get(engine_id)
        if engine is None:
            logger.error(f"Unknown engine: {engine_id}")
            return False
        return engine.load()

    def load_all_available(self) -> Dict[str, bool]:
        results = {}
        for engine_id, engine in self.engines.items():
            if engine.is_available():
                results[engine_id.value] = engine.load()
            else:
                results[engine_id.value] = False
                logger.warning(f"Skipping {engine_id.value}: not available")
        return results

    def unload_engine(self, engine_id: EngineID):
        engine = self.engines.get(engine_id)
        if engine:
            engine.unload()

    def unload_all(self):
        for engine in self.engines.values():
            engine.unload()

    def query_engine(
        self,
        engine_id: EngineID,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> InferenceResult:
        """Query one engine while recording failover health telemetry."""
        try:
            result = self._do_query(
                engine_id=engine_id,
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if result.response.startswith("[ERROR]"):
                self.failover.mark_failure(
                    engine_id,
                    reason=result.response,
                    context={"prompt_length": len(prompt)},
                )
            else:
                self.failover.mark_success(engine_id)
            return result
        except Exception as exc:
            self.failover.mark_failure(
                engine_id,
                reason=str(exc),
                context={"prompt_length": len(prompt)},
            )
            raise

    def _do_query(
        self,
        engine_id: EngineID,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> InferenceResult:
        """Execute engine query without failover side-effects."""
        engine = self.engines.get(engine_id)
        if engine is None or not engine.loaded:
            return InferenceResult(
                engine_id=engine_id,
                prompt=prompt,
                response=f"[ERROR] Engine {engine_id.value} not loaded",
                tokens_generated=0,
                prompt_tokens=0,
                latency_ms=0.0,
                tokens_per_second=0.0,
                model_name=engine_id.value,
            )
        return engine.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def route_and_query(
        self,
        prompt: str,
        domain: Optional[TaskDomain] = None,
        system_prompt: Optional[str] = None,
    ) -> InferenceResult:
        if domain is None:
            domain = self._classify(prompt)
        engine_id = DOMAIN_ROUTING[domain]
        return self.query_engine(engine_id, prompt, system_prompt)

    def query_engine_with_tracking(
        self,
        engine_id: EngineID,
        prompt: str,
        domain: Optional[TaskDomain] = None,
        **kwargs,
    ) -> InferenceResult:
        """Query engine and track preload+failover state."""
        inferred_domain = domain or TaskDomain.TACTICAL
        try:
            result = self.query_engine(engine_id=engine_id, prompt=prompt, **kwargs)
            succeeded = not result.response.startswith("[ERROR]")
            self.preloader.record_request(
                domain=inferred_domain,
                engine_id=engine_id,
                success=succeeded,
                latency_ms=result.latency_ms,
            )
            return result
        except Exception:
            self.preloader.record_request(
                domain=inferred_domain,
                engine_id=engine_id,
                success=False,
                latency_ms=0.0,
            )
            raise

    def query_engine_with_preload_tracking(
        self,
        engine_id: EngineID,
        prompt: str,
        domain: Optional[TaskDomain] = None,
        **kwargs,
    ) -> InferenceResult:
        """Backward-compatible alias for query_engine_with_tracking."""
        return self.query_engine_with_tracking(
            engine_id=engine_id,
            prompt=prompt,
            domain=domain,
            **kwargs,
        )

    def select_healthy_engines(self, candidate_engines: List[EngineID]) -> List[EngineID]:
        """Filter candidates to currently healthy/degraded engines."""
        healthy = set(self.failover.get_healthy_engines())
        return [engine_id for engine_id in candidate_engines if engine_id in healthy]

    def get_engine_availability(self) -> Dict[str, Dict]:
        """Get detailed engine availability and failover state."""
        health = self.failover.get_health_snapshot()
        return {
            engine_id: {
                "available": str(state.get("state", "")).lower() != "unavailable",
                "state": state.get("state"),
                "success_rate": state.get("success_rate"),
            }
            for engine_id, state in health.items()
            if isinstance(state, dict)
        }

    def suggest_preload(
        self,
        domain_hint: Optional[TaskDomain] = None,
        count: int = 2,
    ) -> List[EngineID]:
        """Suggest engines to preload from deterministic prediction."""
        prediction = self.preloader.predict_next_engines(domain_hint=domain_hint, limit=count)
        return prediction.predicted_engines

    def get_pool_metrics(self) -> Dict:
        """Return pool-level health and preload telemetry."""
        health = self.failover.get_health_snapshot()
        preload_stats = self.preloader.get_stats()
        healthy = degraded = unavailable = 0
        for state in health.values():
            if not isinstance(state, dict):
                continue
            normalized = str(state.get("state", "")).lower()
            if normalized == "healthy":
                healthy += 1
            elif normalized == "degraded":
                degraded += 1
            elif normalized == "unavailable":
                unavailable += 1
        return {
            "engines_healthy": healthy,
            "engines_degraded": degraded,
            "engines_unavailable": unavailable,
            "preload_stats": preload_stats,
            "total_requests_tracked": preload_stats.get("total_requests", 0),
        }

    def preload_predicted_engines(
        self,
        domain_hint: Optional[TaskDomain] = None,
    ) -> Dict:
        """
        Build explicit preload plan from deterministic prediction.

        This method only returns planning artifacts and does not auto-load models.
        """
        prediction = self.preloader.predict_next_engines(domain_hint=domain_hint)
        plan = self.preloader.build_preload_plan(prediction=prediction)
        logger.info("Preload plan ready:\n%s", plan.summary())
        return {
            "prediction": prediction,
            "plan": plan,
            "status": "ready_for_loading",
        }

    def consensus_query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> List[InferenceResult]:
        loaded = [eid for eid, eng in self.engines.items() if eng.loaded]
        if not loaded:
            logger.error("No engines loaded for consensus")
            return []

        results: List[InferenceResult] = []

        with ThreadPoolExecutor(max_workers=len(loaded)) as executor:
            futures = {}
            for engine_id in loaded:
                future = executor.submit(
                    self.query_engine,
                    engine_id,
                    prompt,
                    system_prompt,
                    max_tokens,
                )
                futures[future] = engine_id

            for future in as_completed(futures):
                engine_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Consensus failed for {engine_id.value}: {e}")

        return results

    def _classify(self, prompt: str) -> TaskDomain:
        prompt_lower = prompt.lower()
        arabic_indicators = ["ما", "كيف", "أين", "متى", "لماذا", "عربي", "arabic", "translate"]
        tactical_indicators = ["position", "grid", "threat", "enemy", "patrol", "sector", "contact", "movement", "sitrep"]
        planning_indicators = ["plan", "schedule", "route", "logistics", "generate", "build", "create", "code"]
        reasoning_indicators = ["analyze", "compare", "evaluate", "assess", "why", "explain", "implications"]

        if any(kw in prompt_lower for kw in arabic_indicators):
            return TaskDomain.ARABIC_NLP
        if any(kw in prompt_lower for kw in tactical_indicators):
            return TaskDomain.TACTICAL
        if any(kw in prompt_lower for kw in planning_indicators):
            return TaskDomain.PLANNING
        if any(kw in prompt_lower for kw in reasoning_indicators):
            return TaskDomain.REASONING
        return TaskDomain.TACTICAL

    def pool_status(self) -> Dict:
        status = {"total_engines": len(self.engines), "loaded": 0, "engines": {}}
        for engine_id, engine in self.engines.items():
            health = engine.health_check()
            status["engines"][engine_id.value] = health
            if health["loaded"]:
                status["loaded"] += 1
        return status

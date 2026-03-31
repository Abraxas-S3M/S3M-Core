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
from .inference_engine import InferenceEngine, InferenceResult

logger = logging.getLogger("s3m.pool")


class EnginePool:
    """
    Holds all four InferenceEngine instances.
    Supports single-engine queries and multi-engine consensus.
    """

    def __init__(self, n_gpu_layers: int = -1):
        self.n_gpu_layers = n_gpu_layers
        self.engines: Dict[EngineID, InferenceEngine] = {}
        self._initialize_engines()

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

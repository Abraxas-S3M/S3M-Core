"""
S3M Session Manager
High-level interface for running the full quad-engine system.
"""

import logging
from typing import Optional, Dict, List

from .engine_registry import EngineID, TaskDomain
from .engine_pool import EnginePool
from .inference_engine import InferenceResult
from .tactical_prompts import get_system_prompt, format_consensus_query

logger = logging.getLogger("s3m.session")


class S3MSession:
    """
    Top-level entry point for the S3M system.
    Initialize a session, load engines, run queries.
    """

    def __init__(self, n_gpu_layers: int = -1):
        self.pool = EnginePool(n_gpu_layers=n_gpu_layers)
        self.query_log: List[Dict] = []
        logger.info("S3M Session initialized")

    def startup(self, engines: Optional[List[EngineID]] = None) -> Dict[str, bool]:
        if engines:
            results = {}
            for eid in engines:
                results[eid.value] = self.pool.load_engine(eid)
            return results
        return self.pool.load_all_available()

    def shutdown(self):
        self.pool.unload_all()
        logger.info("S3M Session shutdown complete")

    def query(
        self,
        prompt: str,
        domain: Optional[str] = None,
        engine: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> InferenceResult:

        task_domain = None
        if domain:
            task_domain = TaskDomain(domain)

        system_prompt = get_system_prompt(domain or "tactical")

        if engine:
            engine_id = EngineID(engine)
            result = self.pool.query_engine(
                engine_id=engine_id,
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            result = self.pool.route_and_query(
                prompt=prompt,
                domain=task_domain,
                system_prompt=system_prompt,
            )

        self.query_log.append(result.to_dict())
        return result

    def consensus(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
    ) -> List[InferenceResult]:

        formatted = format_consensus_query(prompt)
        system_prompt = get_system_prompt("consensus")

        results = self.pool.consensus_query(
            prompt=formatted,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

        for r in results:
            self.query_log.append(r.to_dict())

        return results

    def status(self) -> Dict:
        pool_status = self.pool.pool_status()
        pool_status["total_queries"] = len(self.query_log)
        return pool_status

    def get_log(self) -> List[Dict]:
        return self.query_log

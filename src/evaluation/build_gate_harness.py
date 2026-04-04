"""
Build-gate evaluation harness for local model health checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from src.llm_core.inference_engine import InferenceResult


@dataclass
class HarnessCaseResult:
    prompt: str
    passed: bool
    response_preview: str
    latency_ms: float
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "prompt": self.prompt,
            "passed": self.passed,
            "response_preview": self.response_preview,
            "latency_ms": self.latency_ms,
            "reason": self.reason,
        }


@dataclass
class HarnessReport:
    model_id: str
    smoke_test: bool
    passed: bool
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: List[HarnessCaseResult]

    def to_dict(self) -> Dict[str, object]:
        return {
            "model_id": self.model_id,
            "smoke_test": self.smoke_test,
            "passed": self.passed,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "results": [item.to_dict() for item in self.results],
        }


class BuildGateHarness:
    """Evaluates inference behavior against lightweight mission-ready checks."""

    def evaluate(
        self,
        model_id: str,
        prompts: List[str],
        infer_fn: Callable[[str, str], InferenceResult],
        smoke_test: bool = False,
    ) -> HarnessReport:
        rows: List[HarnessCaseResult] = []
        for prompt in prompts:
            inference = infer_fn(model_id, prompt)
            text = str(inference.response or "").strip()
            passed = bool(text) and not text.startswith("[ERROR]")
            reason = "ok" if passed else "empty_or_error_response"
            rows.append(
                HarnessCaseResult(
                    prompt=prompt,
                    passed=passed,
                    response_preview=text[:120],
                    latency_ms=float(inference.latency_ms),
                    reason=reason,
                )
            )
        passed_cases = sum(1 for item in rows if item.passed)
        total_cases = len(rows)
        failed_cases = total_cases - passed_cases
        return HarnessReport(
            model_id=model_id,
            smoke_test=bool(smoke_test),
            passed=failed_cases == 0,
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            results=rows,
        )

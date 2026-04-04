#!/usr/bin/env python3
"""
CPU smoke-test runner for manifest-driven S3M inference.
"""

from __future__ import annotations

from typing import Dict, List

from src.edge_runtime.cpu_orchestrator import CPUOrchestrator
from src.edge_runtime.hardware_profiler import HardwareProfiler


TEST_PROMPTS: List[str] = [
    "Summarize the tactical situation in one sentence.",
    "Generate a short defensive patrol checklist for sector delta.",
    "قدّم ملخصًا قصيرًا عن حالة الدوريات في القطاع الشرقي.",
]


def _format_table(rows: List[Dict[str, object]]) -> str:
    headers = ["model_id", "inference_pass", "evaluation_pass", "failed_inference_cases"]
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(str(row.get(header, ""))))

    line = " | ".join(header.ljust(widths[header]) for header in headers)
    sep = "-+-".join("-" * widths[header] for header in headers)
    body = [
        " | ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers)
        for row in rows
    ]
    return "\n".join([line, sep, *body])


def main() -> int:
    profile = HardwareProfiler().run()
    orchestrator = CPUOrchestrator(profile=profile)
    if not orchestrator.initialize():
        print("CPU smoke test failed: no manifests were loaded.")
        return 1

    rows: List[Dict[str, object]] = []
    global_pass = True

    for model_id in sorted(orchestrator.manifests.keys()):
        failed_inference_cases = 0
        for prompt in TEST_PROMPTS:
            result = orchestrator.infer(model_id=model_id, prompt=prompt, max_tokens=96)
            if str(result.response).startswith("[ERROR]"):
                failed_inference_cases += 1
        inference_pass = failed_inference_cases == 0

        report = orchestrator.evaluate(model_id=model_id, test_prompts=TEST_PROMPTS)
        evaluation_pass = bool(report.passed)

        model_pass = inference_pass and evaluation_pass
        global_pass = global_pass and model_pass
        rows.append(
            {
                "model_id": model_id,
                "inference_pass": inference_pass,
                "evaluation_pass": evaluation_pass,
                "failed_inference_cases": failed_inference_cases,
            }
        )

    print(f"CPU smoke test mode: {orchestrator.controller.current_mode.value}")
    print(_format_table(rows))
    print(f"overall_pass={global_pass}")
    return 0 if global_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

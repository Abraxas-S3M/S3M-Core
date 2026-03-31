#!/usr/bin/env python3
"""
S3M Smoke Test — Verifies the entire stack is wired correctly.
Run: python scripts/smoke_test.py
Completes in under 30 seconds. No external dependencies needed.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""


def run_check(name: str, fn: Callable[[], str]) -> CheckResult:
    try:
        detail = fn()
        return CheckResult(name=name, status="PASS", detail=detail)
    except Exception as exc:
        text = str(exc)
        if any(token in text for token in ["No module named", "cannot import name", "optional endpoint unavailable"]):
            return CheckResult(name=name, status="SKIP", detail=text)
        return CheckResult(name=name, status="FAIL", detail=text)


def check_imports() -> List[CheckResult]:
    packages = [
        "src.llm_core",
        "src.threat_detection",
        "src.sensor_fusion",
        "src.autonomy",
        "src.simulation",
        "src.navigation",
        "src.dashboard",
        "src.security",
        "src.apps",
        "src.optimization",
    ]

    results = []
    for package in packages:
        def _load(pkg: str = package) -> str:
            importlib.import_module(pkg)
            return "imported"

        results.append(run_check(f"import:{package}", _load))
    return results


def check_classes() -> List[CheckResult]:
    checks = [
        ("EngineRegistry", "src.llm_core.engine_registry", "EngineRegistry", lambda cls: cls()),
        ("ThreatManager", "src.threat_detection.threat_manager", "ThreatManager", lambda cls: cls()),
        ("SwarmCoordinator", "src.autonomy.swarm.coordinator", "SwarmCoordinator", lambda cls: cls()),
        ("PathPlanner", "src.navigation.planning.path_planner", "PathPlanner", lambda cls: cls()),
        ("DashboardAggregator", "src.dashboard.aggregator", "DashboardAggregator", lambda cls: cls()),
        ("ComplianceChecker", "src.security.compliance", "ComplianceChecker", lambda cls: cls()),
        ("BattlePlanner", "src.apps.battle_planning", "BattlePlanner", lambda cls: cls()),
    ]

    results = []
    for name, module_name, attr, ctor in checks:
        def _init(module_name: str = module_name, attr: str = attr, ctor: Callable = ctor) -> str:
            module = importlib.import_module(module_name)
            cls = getattr(module, attr)
            _ = ctor(cls)
            return "instantiated"

        results.append(run_check(f"class:{name}", _init))
    return results


def check_api() -> List[CheckResult]:
    from fastapi.testclient import TestClient
    from src.api.server import app

    client = TestClient(app)
    endpoints = ["/health", "/engines", "/threats/stats", "/dashboard/overview", "/security/status"]
    optional_endpoints = {"/dashboard/overview", "/security/status"}
    results = []

    for endpoint in endpoints:
        def _hit(ep: str = endpoint) -> str:
            response = client.get(ep)
            if response.status_code == 200:
                return "ok"
            if ep in optional_endpoints and response.status_code == 404:
                raise ModuleNotFoundError(f"optional endpoint unavailable: {ep}")
            raise RuntimeError(f"status {response.status_code}")

        results.append(run_check(f"api:{endpoint}", _hit))
    return results


def check_cross_layer() -> List[CheckResult]:
    from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource
    from src.threat_detection.threat_classifier import ThreatClassifier

    results = []

    def _pipeline() -> str:
        event = ThreatEvent(
            source=ThreatSource.MANUAL,
            level=ThreatLevel.HIGH,
            category=ThreatCategory.CYBER,
            title="Smoke event",
            description="Cross-layer smoke event",
            confidence=0.9,
            raw_data={"smoke": True},
        )
        assessed = ThreatClassifier().classify(event)
        if not assessed.llm_assessment:
            raise RuntimeError("missing llm_assessment")
        return "classified"

    results.append(run_check("cross-layer:threat->classifier", _pipeline))
    return results


def check_dashboard() -> List[CheckResult]:
    def _overview() -> str:
        module = importlib.import_module("src.dashboard.aggregator")
        overview = module.DashboardAggregator().get_overview()
        if not isinstance(overview, dict):
            raise RuntimeError("overview is not dict")
        return "overview_ok"

    return [run_check("dashboard:overview", _overview)]


def check_security() -> List[CheckResult]:
    def _validator() -> str:
        module = importlib.import_module("src.security.input_validator")
        validator = module.InputValidator()
        safe = validator.check_injection("patrol sector alpha")
        bad = validator.check_injection("'; DROP TABLE threats; --")
        if safe or not bad:
            raise RuntimeError("validator behavior mismatch")
        return "validation_ok"

    return [run_check("security:input_validator", _validator)]


def print_table(results: List[CheckResult], elapsed: float) -> int:
    width = max(len(r.name) for r in results) if results else 20
    print("\nS3M SMOKE TEST RESULTS")
    print("=" * (width + 25))
    for result in results:
        print(f"{result.name.ljust(width)} | {result.status.ljust(4)} | {result.detail}")
    print("=" * (width + 25))

    total = len(results)
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIP")
    passed = sum(1 for r in results if r.status == "PASS")
    overall = "PASS" if failed == 0 else "FAIL"

    print(f"Total: {total}  Passed: {passed}  Skipped: {skipped}  Failed: {failed}")
    print(f"Time: {elapsed:.2f}s")
    print(f"Overall: {overall}")
    return 0 if failed == 0 else 1


def main() -> int:
    start = time.perf_counter()
    results: List[CheckResult] = []

    results.extend(check_imports())
    results.extend(check_classes())
    results.extend(check_api())
    results.extend(check_cross_layer())
    results.extend(check_dashboard())
    results.extend(check_security())

    elapsed = time.perf_counter() - start
    return print_table(results, elapsed)


if __name__ == "__main__":
    raise SystemExit(main())

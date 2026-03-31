"""Layer startup sequencing with memory-aware orchestration."""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.optimization.memory_budget_manager import MemoryBudgetManager


class StartupSequencer:
    """Bring S3M layers online in deterministic mission-safe order.

    Tactical context:
    A fixed startup order ensures security controls initialize before mission logic
    and avoids race conditions during rapid redeployments.
    """

    DEFAULT_ORDER = [
        "security",
        "llm_core",
        "threat_detection",
        "sensor_fusion",
        "autonomy",
        "navigation",
        "simulation",
        "dashboard",
        "apps",
    ]

    MODULE_MAP = {
        "security": "src.security",
        "llm_core": "src.llm_core",
        "threat_detection": "src.threat_detection",
        "sensor_fusion": "src.sensor_fusion",
        "autonomy": "src.autonomy",
        "navigation": "src.navigation",
        "simulation": "src.simulation",
        "dashboard": "src.dashboard",
        "apps": "src.apps",
    }

    LAYER_ESTIMATE_MB = {
        "security": 150.0,
        "llm_core": 12000.0,
        "threat_detection": 500.0,
        "sensor_fusion": 100.0,
        "autonomy": 400.0,
        "navigation": 350.0,
        "simulation": 800.0,
        "dashboard": 200.0,
        "apps": 400.0,
    }

    def __init__(self, memory_manager: MemoryBudgetManager = None, config: dict = None):
        self.memory_manager = memory_manager or MemoryBudgetManager()
        self.config = config or self._load_config()
        self.startup_order = list(self.config.get("startup", {}).get("order", self.DEFAULT_ORDER))
        self.details: List[dict] = []
        self.layer_status: Dict[str, dict] = {}

        for layer in self.startup_order:
            estimate = self.LAYER_ESTIMATE_MB.get(layer, 200.0)
            if layer not in self.memory_manager.registry:
                self.memory_manager.register(name=layer, layer=layer, estimated_memory_mb=estimate, priority=3)

    def _load_config(self) -> dict:
        cfg_path = Path("configs/s3m.yaml")
        if not cfg_path.exists():
            return {}
        with cfg_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def sequence(self) -> List[dict]:
        self.details = []
        for layer in self.startup_order:
            t0 = time.perf_counter()
            module_name = self.MODULE_MAP.get(layer, f"src.{layer}")

            if not self.memory_manager.can_load(layer):
                item = {
                    "layer": layer,
                    "status": "skipped_memory",
                    "time_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                    "error": "Insufficient memory budget",
                }
                self.details.append(item)
                self.layer_status[layer] = item
                continue

            try:
                importlib.import_module(module_name)
                self.memory_manager.mark_loaded(layer)
                item = {
                    "layer": layer,
                    "status": "loaded",
                    "time_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                    "error": None,
                }
            except Exception as exc:
                item = {
                    "layer": layer,
                    "status": "unavailable",
                    "time_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                    "error": str(exc),
                }
            self.details.append(item)
            self.layer_status[layer] = item
        return list(self.details)

    def run(self) -> dict:
        t0 = time.perf_counter()
        details = self.sequence()
        loaded = sum(1 for item in details if item["status"] == "loaded")
        skipped = sum(1 for item in details if item["status"] == "skipped_memory")
        unavailable = sum(1 for item in details if item["status"] == "unavailable")
        usage = self.memory_manager.get_usage()
        return {
            "layers_loaded": loaded,
            "layers_skipped": skipped,
            "layers_unavailable": unavailable,
            "total_memory_mb": usage["used_mb"],
            "startup_time_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "details": details,
        }

    def get_status(self) -> dict:
        return {
            "order": list(self.startup_order),
            "layers": dict(self.layer_status),
            "memory": self.memory_manager.get_usage(),
        }

    def shutdown_layer(self, layer: str) -> None:
        if not isinstance(layer, str) or not layer.strip():
            raise ValueError("layer must be a non-empty string")
        if layer in self.memory_manager.registry:
            self.memory_manager.mark_unloaded(layer)
        self.layer_status[layer] = {
            "layer": layer,
            "status": "unloaded",
            "time_ms": 0.0,
            "error": None,
        }

    def get_recommended_config(self, available_memory_gb: float) -> dict:
        if not isinstance(available_memory_gb, (int, float)) or float(available_memory_gb) <= 0:
            raise ValueError("available_memory_gb must be a positive number")

        mem = float(available_memory_gb)
        if mem < 16:
            return {
                "profile": "minimal",
                "llm_engines": 1,
                "layers": ["threat_detection"],
                "note": "Use one tactical engine and threat detection only.",
            }
        if mem < 32:
            return {
                "profile": "reduced",
                "llm_engines": 2,
                "layers": ["threat_detection", "autonomy", "navigation"],
                "note": "Prioritize mission autonomy and mobility with two engines.",
            }
        if mem < 48:
            return {
                "profile": "balanced",
                "llm_engines": 3,
                "layers": ["security", "llm_core", "threat_detection", "sensor_fusion", "autonomy", "navigation", "dashboard", "apps"],
                "note": "Run full mission stack except simulation.",
            }
        return {
            "profile": "full",
            "llm_engines": 4,
            "layers": list(self.DEFAULT_ORDER),
            "note": "Run full S3M stack with all four engines.",
        }

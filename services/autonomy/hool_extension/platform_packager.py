"""Packaging utility for deploying HOOL agents to companion compute.

Military context:
Packaging is designed for air-gapped USB transfer to tactical platforms with
strict RAM/power constraints and deterministic offline installation steps.
"""

from __future__ import annotations

from typing import List, Optional

from services.autonomy.hool_extension.models import CompanionCompute, MissionEnvelope, PlatformClass


class PlatformPackager:
    """Build and validate deployable HOOL bundles per platform profile."""

    def __init__(self):
        self._storage_budget_mb = {
            PlatformClass.UAV_QUADROTOR: 32000.0,
            PlatformClass.UAV_FIXED_WING: 64000.0,
            PlatformClass.UAV_VTOL: 64000.0,
            PlatformClass.UGV_WHEELED: 32000.0,
            PlatformClass.UGV_TRACKED: 64000.0,
            PlatformClass.USV_SURFACE: 16000.0,
            PlatformClass.UUV_UNDERWATER: 16000.0,
        }

    def package_for_platform(
        self,
        platform_class: PlatformClass,
        mission_envelope: MissionEnvelope,
        models: Optional[List[str]] = None,
    ) -> dict:
        """Generate package manifest constrained by platform compute limits."""
        compute = CompanionCompute.for_platform(platform_class)
        files = [
            "services/autonomy/hool_extension/__init__.py",
            "services/autonomy/hool_extension/models.py",
            "services/autonomy/hool_extension/envelope_checker.py",
            "services/autonomy/hool_extension/hool_behavior_tree.py",
            "services/autonomy/hool_extension/hool_agent.py",
        ]
        selected_models: List[str] = list(models or [])
        size_mb = 45.0
        memory_required_mb = 900.0

        cpu_label = compute.cpu_model.lower()
        if "orin nx" in cpu_label:
            selected_models.extend(["yolov8-nano.onnx", "phi3-medium-int4.gguf"])
            size_mb += 4800.0
            memory_required_mb += 2600.0
        elif "xavier nx" in cpu_label:
            selected_models.extend(["yolov8-medium.onnx", "phi3-medium-int4.gguf"])
            size_mb += 6200.0
            memory_required_mb += 3200.0
        elif "orin nano" in cpu_label:
            selected_models.extend(["yolov8-nano.onnx", "phi3-medium-int4.gguf"])
            size_mb += 4300.0
            memory_required_mb += 2400.0
        elif "raspberry pi 5" in cpu_label:
            selected_models.extend(["rule_based_bt_only.marker"])
            size_mb += 120.0
            memory_required_mb += 450.0
        else:
            selected_models.extend(["minimal_rule_bt.marker"])
            size_mb += 80.0
            memory_required_mb += 350.0

        selected_models = sorted(set(selected_models))
        return {
            "platform": platform_class.value,
            "files": files,
            "models": selected_models,
            "total_size_mb": round(size_mb, 2),
            "memory_required_mb": round(memory_required_mb, 2),
            "transfer_method": "usb",
            "install_script": self.generate_install_script(platform_class),
            "envelope_id": mission_envelope.envelope_id,
        }

    def generate_install_script(self, platform_class: PlatformClass) -> str:
        """Generate deterministic offline install script for companion deployment."""
        return "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "# Tactical offline deployment for HOOL companion package",
                'PKG_DIR="${1:-/opt/s3m/hool_package}"',
                'python3 -m venv "$PKG_DIR/.venv"',
                'source "$PKG_DIR/.venv/bin/activate"',
                "python -m pip install --upgrade pip",
                'python -m pip install --no-index --find-links "$PKG_DIR/wheels" -r "$PKG_DIR/requirements.txt"',
                'mkdir -p /opt/s3m/models && cp -r "$PKG_DIR/models/." /opt/s3m/models/ || true',
                'mkdir -p /etc/s3m && cp "$PKG_DIR/config/hool_agent.yaml" /etc/s3m/hool_agent.yaml',
                f'echo "Installed HOOL package for {platform_class.value}"',
            ]
        )

    def validate_package(self, package: dict) -> tuple[bool, List[str]]:
        """Validate package size, RAM fit, and required capability compatibility."""
        issues: List[str] = []
        try:
            platform = PlatformClass(package.get("platform"))
        except Exception:
            return False, ["invalid package platform"]

        compute = CompanionCompute.for_platform(platform)
        size_mb = float(package.get("total_size_mb", 0.0))
        memory_mb = float(package.get("memory_required_mb", 0.0))
        models = list(package.get("models", []))

        if size_mb > self._storage_budget_mb.get(platform, 16000.0):
            issues.append("package exceeds companion storage budget")
        if memory_mb > compute.ram_mb:
            issues.append("package memory requirement exceeds companion RAM")
        if any("phi3" in m.lower() for m in models) and not compute.llm_capable:
            issues.append("package includes LLM model but platform is not llm_capable")
        if any("yolo" in m.lower() for m in models) and not compute.gpu_available:
            issues.append("package includes ATR model but platform has no GPU")
        return (len(issues) == 0, issues)

#!/usr/bin/env python3
"""Start the S3M API Server - deployment-mode aware."""

import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _normalize_deployment_mode(raw_mode: Any) -> str:
    """Normalize deployment mode into a lowercase string identifier."""
    mode = raw_mode
    if hasattr(raw_mode, "value"):
        mode = raw_mode.value
    if mode is None:
        return "jetson_edge"
    return str(mode).strip().lower()


def _resolve_mode_details(mode: str) -> tuple[str, str]:
    """Map deployment mode to a platform label and mission-mode banner."""
    mode_labels = {
        "jetson_edge": ("NVIDIA Jetson AGX Orin 64GB", "AIR-GAPPED DEPLOYMENT"),
        "cloud_cpu_demo": ("Hetzner Cloud CPU", "CLOUD CPU DEMO"),
        "gpu_cluster": ("GPU Cluster", "MULTI-GPU DEPLOYMENT"),
    }
    return mode_labels.get(mode, ("Unknown", "UNKNOWN"))


def _preflight_cloud_check(config: Any) -> list[str]:
    """Validate critical settings for cloud CPU demo deployment."""
    warnings: list[str] = []
    cors_origins = getattr(config, "cors_origins", ["*"])
    auth_enabled = bool(getattr(config, "auth_enabled", False))
    api_key = getattr(config, "api_key", None)
    device = str(getattr(config, "device", "cpu")).strip().lower()

    # Tactical context: strict ingress/auth defaults reduce exposure of command paths.
    if not cors_origins or cors_origins == ["*"]:
        warnings.append("CORS_ORIGINS is wildcard or empty - set explicitly for production")
    if auth_enabled and not api_key:
        warnings.append("S3M_AUTH_ENABLED=true but no S3M_API_KEY set")
    if device != "cpu":
        warnings.append(f"Cloud demo should use CPU but device={device}")
    return warnings


def main() -> None:
    try:
        from src.api.config import api_config
    except Exception as e:
        import logging
        logging.warning(f"Non-fatal startup error: {e}")
        return

    mode_from_env = os.getenv("DEPLOYMENT_MODE")
    mode_from_config = getattr(api_config, "deployment_mode", None)
    deployment_mode = _normalize_deployment_mode(mode_from_env or mode_from_config)
    platform, mode_desc = _resolve_mode_details(deployment_mode)

    device = str(getattr(api_config, "device", os.getenv("S3M_DEVICE", "cuda"))).upper()
    auth_enabled = bool(getattr(api_config, "auth_enabled", False))
    cors_origins = getattr(api_config, "cors_origins", ["*"])
    cors_display = ", ".join(cors_origins) if cors_origins else "(none)"

    print("=" * 60)
    print("  S3M QUAD-ENGINE API SERVER")
    print(f"  Platform: {platform}")
    print(f"  Mode: {mode_desc}")
    print(f"  Deployment Mode: {deployment_mode}")
    print(f"  Device: {device}")
    print(f"  Auth: {'ENABLED' if auth_enabled else 'DISABLED'}")
    print(f"  CORS: {cors_display}")
    print("=" * 60)

    if deployment_mode == "cloud_cpu_demo":
        warnings = _preflight_cloud_check(api_config)
        for warning in warnings:
            print(f"  [WARN] {warning}")

    try:
        import uvicorn

        print(f"\n  Starting server on {api_config.host}:{api_config.port}")
        print(f"  API Docs: http://localhost:{api_config.port}/docs")
        print(f"  Health:   http://localhost:{api_config.port}/health")
        print()

        uvicorn.run(
            "src.api.server:app",
            host=api_config.host,
            port=api_config.port,
            workers=api_config.workers,
            log_level=getattr(api_config, "log_level", "info"),
            reload=False,
        )
    except Exception as e:
        import logging
        logging.warning(f"Non-fatal startup error: {e}")


if __name__ == "__main__":
    main()

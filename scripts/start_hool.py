#!/usr/bin/env python3
"""Start HOOL operations stack from YAML configuration."""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI

from src.autonomy.mission_executive import MissionExecutive
from src.platforms.common.config_loader import HOOLRuntimeContext, bootstrap_hool_runtime


def build_hool_app() -> FastAPI:
    """Return the API app with HOOL extension routes mounted."""
    from services.autonomy.hool_extension.api_routes import router as hool_router
    from src.api.server import app

    existing_paths = {route.path for route in app.routes}
    if "/hool/status" not in existing_paths:
        app.include_router(hool_router, tags=["HOOL Autonomy"])
    return app


def initialize_mission_executive(runtime: HOOLRuntimeContext) -> MissionExecutive:
    """Initialize mission executive using loaded HOOL mission templates."""
    _ = runtime
    return MissionExecutive()


def print_fleet_status_summary(runtime: HOOLRuntimeContext) -> None:
    """Print concise fleet status for operator startup checks."""
    print("\nHOOL Fleet Status Summary")
    print("-" * 72)
    for row in runtime.platform_registry.fleet_status_summary():
        position = row.get("position", (0.0, 0.0, 0.0))
        print(
            f"{row['platform_id']:16} type={row['type']:6} "
            f"adapter={row['adapter_class']:16} "
            f"pos=({position[0]:8.1f}, {position[1]:8.1f}, {position[2]:6.1f}) "
            f"health={row.get('health_state', 'unknown')}"
        )


def start_health_monitor_polling_loop(
    runtime: HOOLRuntimeContext,
    *,
    poll_interval_seconds: float,
    stop_event: threading.Event,
) -> threading.Thread:
    """Start background platform state polling for tactical heartbeat visibility."""

    def _poll_loop() -> None:
        while not stop_event.is_set():
            for platform_id, adapter in runtime.platform_registry.adapters().items():
                try:
                    state = adapter.read_state()
                    print(
                        "[health] "
                        f"platform={platform_id} "
                        f"position={getattr(state, 'position', 'unknown')} "
                        f"mode={getattr(getattr(state, 'autonomy_mode', None), 'value', 'unknown')}"
                    )
                except Exception as exc:
                    print(f"[health] platform={platform_id} error={exc}")
            stop_event.wait(poll_interval_seconds)

    thread = threading.Thread(target=_poll_loop, name="hool-health-monitor", daemon=True)
    thread.start()
    return thread


def _resolve_poll_interval(runtime: HOOLRuntimeContext) -> float:
    safety = runtime.configs.safety.get("safety", {})
    poll_value = safety.get("health_poll_interval_seconds", 2.0)
    try:
        poll_interval = float(poll_value)
    except Exception as exc:
        raise ValueError("safety.health_poll_interval_seconds must be numeric") from exc
    if poll_interval <= 0:
        raise ValueError("safety.health_poll_interval_seconds must be > 0")
    return poll_interval


def main() -> None:
    print("=" * 72)
    print("S3M HOOL OPERATIONS STARTUP")
    print("Config-driven fleet bootstrap for tactical autonomy operations")
    print("=" * 72)

    config_dir = os.environ.get("HOOL_CONFIG_DIR", "configs/hool")
    runtime = bootstrap_hool_runtime(config_dir=config_dir)
    mission_executive = initialize_mission_executive(runtime)
    _ = mission_executive
    app = build_hool_app()

    poll_interval = _resolve_poll_interval(runtime)
    stop_event = threading.Event()
    polling_thread = start_health_monitor_polling_loop(
        runtime,
        poll_interval_seconds=poll_interval,
        stop_event=stop_event,
    )
    _ = polling_thread

    print_fleet_status_summary(runtime)

    mission_templates = runtime.configs.missions.get("missions", [])
    print(f"\nLoaded mission templates: {len(mission_templates)}")
    print(f"Registered operators: {len(runtime.registered_operators)}")

    from src.api.config import api_config

    try:
        import uvicorn

        print(f"\nStarting HOOL API server on {api_config.host}:{api_config.port}")
        print(f"HOOL status endpoint: http://localhost:{api_config.port}/hool/status")
        uvicorn.run(
            app,
            host=api_config.host,
            port=api_config.port,
            workers=1,
            log_level="info",
        )
    finally:
        stop_event.set()
        time.sleep(0.1)


if __name__ == "__main__":
    main()

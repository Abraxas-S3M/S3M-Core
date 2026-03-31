#!/usr/bin/env python3
"""Start the S3M Dashboard — API + Frontend."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    print("=" * 60)
    print("  S3M DASHBOARD — SOVEREIGN MILITARY AI")
    print("  Layer 06: Operator Interface")
    print("=" * 60)
    try:
        import uvicorn

        from src.api.config import api_config

        print(f"\n  Dashboard:  http://localhost:{api_config.port}/dashboard/")
        print(f"  API Docs:   http://localhost:{api_config.port}/docs")
        print(f"  WebSocket:  ws://localhost:{api_config.port}/dashboard/ws")
        print()
        uvicorn.run(
            "src.api.server:app",
            host=api_config.host,
            port=api_config.port,
            workers=1,
            log_level="info",
        )
    except ImportError as exc:
        print(f"\n  [ERROR] Missing dependency: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Start the S3M API Server."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 60)
    print("  S3M QUAD-ENGINE API SERVER")
    print("  Platform: NVIDIA Jetson AGX Orin 64GB")
    print("  Mode: AIR-GAPPED DEPLOYMENT")
    print("=" * 60)

    try:
        import uvicorn
        from src.api.config import api_config

        print(f"\n  Starting server on {api_config.host}:{api_config.port}")
        print(f"  API Docs: http://localhost:{api_config.port}/docs")
        print(f"  Health:   http://localhost:{api_config.port}/health")
        print()

        uvicorn.run(
            "src.api.server:app",
            host=api_config.host,
            port=api_config.port,
            workers=api_config.workers,
            log_level="info",
            reload=False
        )
    except ImportError as e:
        print(f"\n  [ERROR] Missing dependency: {e}")
        print("  Install with: pip install fastapi uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()

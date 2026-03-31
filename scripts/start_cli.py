#!/usr/bin/env python3
"""Start the S3M Tactical CLI."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="S3M Tactical CLI")
    parser.add_argument("--api-url", default="http://localhost:8080", help="API server URL")
    args = parser.parse_args()

    from src.cli.tactical_cli import TacticalCLI

    cli = TacticalCLI(api_url=args.api_url)

    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\n\n  CLI interrupted. Goodbye.\n")


if __name__ == "__main__":
    main()

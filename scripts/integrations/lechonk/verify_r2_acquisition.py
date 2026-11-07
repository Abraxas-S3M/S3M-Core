#!/usr/bin/env python3
"""Emit Le Chonk R2 acquisition inventory reports without downloading weights."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.integrations.lechonk.r2_acquisition import (  # noqa: E402
    build_production_inventory_report,
    r2_client_lister_factory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Le Chonk R2 quarantine object metadata.")
    parser.add_argument(
        "--manifest",
        default="configs/model_manifests/mistral_large_4.yaml",
        help="Le Chonk manifest path",
    )
    parser.add_argument(
        "--output",
        default="reports/lechonk_r2_inventory.json",
        help="Write JSON inventory report to this path",
    )
    args = parser.parse_args()

    try:
        lister = r2_client_lister_factory()()
    except ValueError as exc:
        print(f"R2 credentials unavailable: {exc}", file=sys.stderr)
        return 2

    report = build_production_inventory_report(args.manifest, lister=lister)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(out), "admitted": report.get("admitted")}, indent=2))
    return 0 if report.get("admitted") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Standalone air-gap verification utility for deployment gates."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.security.airgap_verifier import AirGapVerifier


def main() -> int:
    verifier = AirGapVerifier()
    result = verifier.verify()
    print("=" * 70)
    print("S3M PHASE 10 AIR-GAP VERIFICATION")
    print("=" * 70)
    print(f"Timestamp: {result.get('timestamp')}")
    checks = result.get("checks_performed", [])
    violations = result.get("violations", [])
    print(f"Checks performed: {', '.join(checks) if checks else 'none'}")
    air_gapped = result.get("air_gapped")
    if air_gapped is None:
        print("[WARN] Air-gap status inconclusive on this platform.")
        note = result.get("note")
        if note:
            print(f"  - {note}")
        return 0

    if air_gapped:
        print("[PASS] Environment appears air-gapped.")
        return 0

    print("[FAIL] Air-gap violations detected.")
    for idx, violation in enumerate(violations, start=1):
        print(
            f"  {idx}. [{violation.get('severity', 'WARN')}] "
            f"{violation.get('check', 'unknown')}: {violation.get('detail', '')}"
        )
    print("\nRemediation:")
    print("- Disable non-approved network interfaces and remove outbound routes.")
    print("- Block DNS resolution and outbound internet access.")
    print("- Close or document non-mission listening ports.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

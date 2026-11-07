"""CycloneDX SBOM helpers for Cortex container images."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _requirements_components(req_paths: List[Path], tier: str) -> List[Dict[str, Any]]:
    components: List[Dict[str, Any]] = []
    for req_path in req_paths:
        if not req_path.exists():
            continue
        for line in req_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            name = stripped.split(">=")[0].split("==")[0].strip()
            components.append(
                {
                    "type": "library",
                    "name": name,
                    "purl": f"pkg:pypi/{name}",
                    "properties": [{"name": "s3m:source_requirements", "value": str(req_path)}],
                }
            )
    return components


def build_sbom_from_requirements(tier: str, req_paths: List[Path], image_ref: str) -> Dict[str, Any]:
    """Fallback SBOM when syft is unavailable (CI offline / lightweight checks)."""
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "container",
                "name": image_ref,
                "properties": [
                    {"name": "s3m:cortex.tier", "value": tier},
                    {"name": "s3m:build_profile", "value": "customer"},
                ],
            },
            "tools": [{"vendor": "S3M", "name": "cortex-sbom-fallback", "version": "1.0"}],
        },
        "components": _requirements_components(req_paths, tier),
    }


def syft_sbom(image_ref: str, output: Path) -> bool:
    syft = shutil.which("syft")
    if not syft:
        return False
    proc = subprocess.run(
        [syft, image_ref, "-o", f"cyclonedx-json={output}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and output.exists() and output.stat().st_size > 0


def tier_requirements(tier: str) -> List[Path]:
    base = [
        Path("requirements-api.txt"),
        Path("requirements-security.txt"),
    ]
    if tier == "core":
        return base + [Path("requirements-intel.txt"), Path("requirements-cognitive.txt")]
    if tier == "regional":
        return base + [Path("requirements-intel.txt")]
    if tier == "edge":
        return [Path("requirements-edge.txt"), Path("requirements-security.txt")]
    raise ValueError(f"unknown tier: {tier}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CycloneDX SBOM for a Cortex image.")
    parser.add_argument("--tier", choices=["core", "regional", "edge"], required=True)
    parser.add_argument("--image", required=True, help="Local image reference (e.g. cortex-core:ci).")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if syft_sbom(args.image, args.output):
        return 0

    sbom = build_sbom_from_requirements(args.tier, tier_requirements(args.tier), args.image)
    args.output.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate a CycloneDX CBOM from the Cortex cryptographic inventory."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

CBOM_SPEC_VERSION = "1.6"
DEFAULT_INVENTORY = Path("configs/cortex/cbom_inventory.yaml")


def _load_inventory(path: Path) -> List[Dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    components = raw.get("components") or []
    if not isinstance(components, list):
        raise ValueError("cbom_inventory.components must be a list")
    return components


def build_cbom(inventory_path: Path, cortex_version: str) -> Dict[str, Any]:
    """Build CycloneDX CBOM describing algorithms in use."""
    components = _load_inventory(inventory_path)
    crypto_components: List[Dict[str, Any]] = []
    for block in components:
        name = str(block.get("name", "unknown"))
        for algo in block.get("algorithms") or []:
            crypto_components.append(
                {
                    "type": "cryptographic-asset",
                    "name": str(algo.get("id", "unspecified")),
                    "description": str(algo.get("purpose", "")),
                    "cryptoProperties": {
                        "assetType": "algorithm",
                        "algorithmProperties": {
                            "primitive": "unknown",
                            "parameterSetIdentifier": str(algo.get("id", "")),
                        },
                    },
                    "group": name,
                }
            )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": CBOM_SPEC_VERSION,
        "serialNumber": f"urn:uuid:cortex-cbom-{cortex_version}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "s3m-cortex",
                "version": cortex_version,
            },
            "properties": [{"name": "s3m:build_profile", "value": "customer"}],
        },
        "components": crypto_components,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Cortex CycloneDX CBOM JSON.")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--version", required=True, help="Cortex release version string.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cbom = build_cbom(args.inventory, args.version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cbom, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

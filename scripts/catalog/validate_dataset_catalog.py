#!/usr/bin/env python3
"""Validate dataset catalog schema and routing prerequisites.

Military/tactical context:
Validation prevents malformed dataset metadata from entering packet-selection
pipelines that feed command-support model adaptation tracks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.catalog.dataset_catalog import validate_catalog

DEFAULT_CONFIG_PATH = Path("configs/catalog/datasets.saudi_mod.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate dataset catalog JSON.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Catalog config JSON path.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="Optional direct catalog JSON path override.",
    )
    parser.add_argument(
        "--ontology",
        type=Path,
        default=None,
        help="Saudi MOD ontology domains JSON path.",
    )
    parser.add_argument(
        "--artifact-rooms",
        type=Path,
        default=None,
        help="Artifact rooms registry JSON path.",
    )
    return parser.parse_args()


def _load_config(config_path: Path) -> dict[str, str]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config {config_path} must be a JSON object.")
    return {str(key): str(value) for key, value in payload.items()}


def main() -> int:
    args = parse_args()
    config = _load_config(args.config)
    catalog_path = args.catalog or Path(config.get("catalog_path", "catalog/datasets/saudi_mod.v1.json"))
    ontology_path = args.ontology or Path(
        config.get("ontology_path", "training/scenario_ontology/saudi_mod/v1/scenario_domains.json")
    )
    artifact_rooms_path = args.artifact_rooms or Path(config.get("artifact_rooms_path", "artifacts/rooms/room_registry.json"))
    result = validate_catalog(
        catalog_path=catalog_path,
        ontology_path=ontology_path,
        artifact_rooms_path=artifact_rooms_path,
    )

    print(f"Catalog: {result.catalog_path}")
    print(f"Records loaded: {result.total_records}")

    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    print("Catalog validation PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Print dataset routing results for Saudi MOD scenario domain requests.

Military/tactical context:
Route previews let planners confirm that packet assembly draws from relevant
mission datasets before adaptation runs are authorized.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.catalog import DatasetRouter, validate_catalog

DEFAULT_CONFIG_PATH = Path("configs/catalog/datasets.saudi_mod.json")
DEFAULT_TOP_K = 8
DEFAULT_ROUTE_CASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("saudi_mod", ("risk_readiness",)),
    ("saudi_mod", ("cop_intel",)),
    ("saudi_mod", ("cyber_electronic_warfare",)),
    ("saudi_mod", ("logistics_sustainment",)),
    ("saudi_mod", ("bilingual",)),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print ranked dataset route candidates.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Catalog config JSON path.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Maximum number of routes to print per case.",
    )
    return parser.parse_args()


def _load_catalog_path(config_path: Path) -> Path:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    catalog_path = payload.get("catalog_path")
    if not isinstance(catalog_path, str) or not catalog_path.strip():
        raise ValueError(f"Config {config_path} must define non-empty string 'catalog_path'")
    candidate = Path(catalog_path)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def _print_case(track: str, scenario_domains: Sequence[str], *, router: DatasetRouter, top_k: int) -> None:
    print(f"=== route: track={track} domains={list(scenario_domains)} ===")
    routes = router.route(
        training_track=track,
        scenario_domains=scenario_domains,
        top_k=top_k,
    )
    if not routes:
        print("  (no matching datasets)")
        return

    for idx, route in enumerate(routes, start=1):
        print(
            f"  {idx:02d}. {route.dataset_id} score={route.score} "
            f"matched={list(route.matched_scenario_domains)} reasons={list(route.reasons)}"
        )


def main() -> int:
    args = parse_args()
    config_path = args.config if args.config.is_absolute() else REPO_ROOT / args.config
    catalog_path = _load_catalog_path(config_path)
    result = validate_catalog(catalog_path)
    if not result.is_valid:
        print("Catalog validation failed. Resolve errors before routing:")
        for item in result.errors:
            print(f"  - {item}")
        return 1

    router = DatasetRouter(result.records)
    for track, domains in DEFAULT_ROUTE_CASES:
        _print_case(track, domains, router=router, top_k=args.top_k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

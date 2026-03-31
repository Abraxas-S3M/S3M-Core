#!/usr/bin/env python3
"""Phase 11 dataset registry demonstration script."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.apps.data_management.dataset_registry import DatasetRegistry


def main() -> None:
    registry = DatasetRegistry()
    datasets = registry.list_datasets()
    print("=== DATASET REGISTRY SUMMARY ===")
    print(f"{'ID':<10} {'Name':<45} {'Domain':<14} {'Format':<8} {'Available':<10}")
    for item in datasets:
        print(
            f"{str(item.get('id')):<10} "
            f"{str(item.get('name'))[:44]:<45} "
            f"{str(item.get('domain')):<14} "
            f"{str(item.get('format')):<8} "
            f"{str(item.get('available')):<10}"
        )

    availability = registry.check_availability()
    print("\n=== AVAILABILITY ===")
    print(f"Total: {availability['total']}  Available: {availability['available']}  Missing: {availability['missing']}")

    missing = [item for item in availability["datasets"] if not item.get("available")]
    print("\n=== DOWNLOAD INSTRUCTIONS (FIRST 3 MISSING) ===")
    for item in missing[:3]:
        item_id = item.get("id")
        print(f"- {item_id}: {registry.get_download_instructions(item_id)}")

    stats = registry.get_stats()
    total_size_estimate = ", ".join(sorted({str(item.get('size_estimate')) for item in datasets}))
    print("\n=== STATS ===")
    print("By domain:", stats["by_domain"])
    print("By format:", stats["by_format"])
    print("Total datasets:", stats["total"])
    print("Size estimates present:", total_size_estimate)


if __name__ == "__main__":
    main()


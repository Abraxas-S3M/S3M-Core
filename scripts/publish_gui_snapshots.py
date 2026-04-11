#!/usr/bin/env python3
"""CLI for publishing S3M GUI snapshots to object storage.

Military/tactical context:
This command supports disconnected rehearsal operations by producing static
workspace payloads that the CloudFlare Pages GUI can consume offline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.gui_bridge.snapshot_publisher import SnapshotPublisher
from src.storage.object_storage import ObjectStorageConnector


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish CloudFlare GUI snapshots")
    parser.add_argument("--all", action="store_true", help="Generate and publish all workspace snapshots")
    parser.add_argument("--training-only", action="store_true", help="Publish only training-status snapshot")
    parser.add_argument(
        "--workspace",
        action="append",
        default=[],
        help="Publish one or more specific workspaces (repeatable)",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Generate snapshots and write to local output instead of object storage upload",
    )
    parser.add_argument(
        "--output",
        default="./snapshots",
        help="Output directory used with --local-only (default: ./snapshots)",
    )
    return parser.parse_args()


def _resolve_connector(local_only: bool) -> ObjectStorageConnector:
    if local_only:
        return ObjectStorageConnector()
    if hasattr(ObjectStorageConnector, "from_env"):
        return ObjectStorageConnector.from_env()
    return ObjectStorageConnector()


def _select_workspaces(args: argparse.Namespace) -> list[str]:
    if args.training_only:
        return ["training_status"]
    if args.workspace:
        return [str(item).strip().lower() for item in args.workspace if str(item).strip()]
    if args.all:
        return list(SnapshotPublisher.SUPPORTED_WORKSPACES)
    raise ValueError("No publish mode selected. Use --all, --training-only, or --workspace.")


def _print_summary(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def main() -> int:
    args = _parse_args()
    try:
        selected_workspaces = _select_workspaces(args)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    connector = _resolve_connector(local_only=args.local_only)
    publisher = SnapshotPublisher(connector)

    snapshots = {
        workspace: publisher.generate_workspace_snapshot(workspace)
        for workspace in selected_workspaces
    }

    if args.local_only:
        manifest = publisher.write_local_snapshots(snapshots=snapshots, output_dir=Path(args.output))
        print(f"[OK] Wrote {len(snapshots)} snapshots to {Path(args.output).resolve()}")
        _print_summary(manifest)
        return 0

    if args.training_only and len(selected_workspaces) == 1 and selected_workspaces[0] == "training_status":
        publisher.publish_training_status()
        print("[OK] Published training-status snapshot")
        return 0

    manifest = publisher.publish_to_object_storage(snapshots)
    print(f"[OK] Published {len(snapshots)} snapshots")
    _print_summary(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

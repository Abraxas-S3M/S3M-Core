#!/usr/bin/env python3
"""Build, validate, and optionally upload scenario training packets.

Military/tactical context:
This CLI standardizes packet assembly so distributed operators can ship trusted
scenario updates into sovereign training tracks without format drift.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the repository root is importable when invoked as a file path.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.training.packet_builder import PacketBuilder


def parse_args() -> argparse.Namespace:
    """Parse command-line options for packet build and validation flows."""
    parser = argparse.ArgumentParser(description="Build and validate S3M scenario training packets.")
    parser.add_argument("--input", type=Path, help="Raw JSONL input file to convert into scenario packets.")
    parser.add_argument(
        "--track",
        choices=["saudi_mod", "ukraine_mod", "nato", "indopac_mod", "southam_mod", "africa_mod", "shared"],
        help="Target training track for generated packets.",
    )
    parser.add_argument(
        "--data-class",
        dest="data_class",
        choices=["command", "cop_intel", "risk_readiness", "bilingual"],
        help="Scenario data class to stamp in packet manifests.",
    )
    parser.add_argument("--output", type=Path, help="Output directory that holds scenario-XXXXX packets.")
    parser.add_argument(
        "--examples-per-pack",
        type=int,
        default=50,
        help="Maximum normalized examples per generated packet.",
    )
    parser.add_argument(
        "--validate",
        type=Path,
        help="Validate an existing scenario packet directory and exit.",
    )
    parser.add_argument(
        "--source",
        choices=["manual", "claude_generated", "synthetic"],
        default="manual",
        help="Provenance value embedded in generated manifests.",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload validated generated packets to Cloudflare R2 after creation.",
    )
    return parser.parse_args()


def main() -> int:
    """Run CLI command and return process exit code."""
    args = parse_args()
    builder = PacketBuilder(source=args.source)

    if args.validate is not None:
        is_valid = builder.validate_pack(args.validate)
        if is_valid:
            print(f"VALID: {args.validate}")
            return 0
        print(f"INVALID: {args.validate}")
        return 1

    if args.input is None:
        raise SystemExit("--input is required unless --validate is used")
    if args.track is None:
        raise SystemExit("--track is required unless --validate is used")
    if args.data_class is None:
        raise SystemExit("--data-class is required unless --validate is used")
    if args.output is None:
        raise SystemExit("--output is required unless --validate is used")

    packs = builder.build_from_jsonl(
        input_file=args.input,
        track=args.track,
        data_class=args.data_class,
        output_dir=args.output,
        examples_per_pack=args.examples_per_pack,
    )
    print(f"Built {len(packs)} packet(s).")
    for pack_dir in packs:
        print(str(pack_dir))

    if args.upload and packs:
        remote_prefixes = builder.upload_packs(pack_dirs=packs, track=args.track)
        print("Uploaded packet prefixes:")
        for prefix in remote_prefixes:
            print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


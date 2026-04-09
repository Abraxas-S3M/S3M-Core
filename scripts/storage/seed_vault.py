#!/usr/bin/env python3
"""Seed the BackBlaze vault with model weights from HuggingFace.

Run on an internet-connected machine (your laptop).
Downloads FP16 from HuggingFace, uploads to BackBlaze.
Optionally also downloads pre-quantized Q4 GGUF files.

Usage:
  # Seed Phi-3 Medium (FP16 + Q4):
  python scripts/storage/seed_vault.py --engine phi3-medium --both

  # Seed Mistral (FP16 only, will quantize on Hetzner later):
  python scripts/storage/seed_vault.py --engine mistral-7b --fp16-only

  # Seed all trainable engines:
  python scripts/storage/seed_vault.py --all-trainable --both

  # Check what's in the vault:
  python scripts/storage/seed_vault.py --inventory
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from src.storage.b2_connector import B2Connector
from src.storage.precision_manager import PrecisionManager
from src.storage.vault_paths import VaultPaths

try:
    from huggingface_hub import snapshot_download
except Exception as exc:  # pragma: no cover - import guard
    snapshot_download = None
    _HF_IMPORT_ERROR = exc
else:
    _HF_IMPORT_ERROR = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed S3M dual-precision vault in BackBlaze B2")
    parser.add_argument("--engine", action="append", default=[], help="Engine id to seed (repeatable)")
    parser.add_argument("--all-trainable", action="store_true", help="Seed all engines marked trainable=true")
    parser.add_argument("--both", action="store_true", help="Seed FP16 and Q4 tiers")
    parser.add_argument("--fp16-only", action="store_true", help="Seed only FP16 tier")
    parser.add_argument("--q4-only", action="store_true", help="Seed only Q4 tier")
    parser.add_argument("--resume", action="store_true", help="Skip files already present in BackBlaze")
    parser.add_argument("--inventory", action="store_true", help="Print vault inventory and exit")
    parser.add_argument("--force-grok", action="store_true", help="Allow grok seeding with explicit warning prompt")
    parser.add_argument(
        "--config",
        default="configs/deployment/backblaze.yaml",
        help="BackBlaze deployment config with engine repository metadata",
    )
    parser.add_argument(
        "--assumed-upload-mbps",
        type=float,
        default=200.0,
        help="Estimated uplink throughput used only for ETA printouts",
    )
    return parser.parse_args()


def _load_engine_catalog(config_path: Path) -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("BackBlaze config must be a mapping")
    backblaze = payload.get("backblaze", {})
    if not isinstance(backblaze, dict):
        raise ValueError("backblaze config section must be a mapping")
    engines = backblaze.get("engines", {})
    if not isinstance(engines, dict):
        raise ValueError("backblaze.engines must be a mapping")
    return {str(name): data for name, data in engines.items() if isinstance(data, dict)}


def _selected_engines(args: argparse.Namespace, engines: dict[str, dict[str, Any]]) -> list[str]:
    if args.all_trainable:
        selected = [name for name, cfg in engines.items() if bool(cfg.get("trainable", False))]
        return sorted(selected)

    picked = [str(engine).strip() for engine in args.engine if str(engine).strip()]
    if picked:
        unknown = [engine for engine in picked if engine not in engines]
        if unknown:
            raise ValueError(f"Unknown engine(s): {unknown}. Available: {sorted(engines)}")
        return picked
    raise ValueError("Select at least one engine via --engine or use --all-trainable")


def _resolve_precision_mode(args: argparse.Namespace) -> tuple[bool, bool]:
    mode_flags = sum(bool(value) for value in (args.both, args.fp16_only, args.q4_only))
    if mode_flags > 1:
        raise ValueError("Use only one of --both, --fp16-only, or --q4-only")
    if args.fp16_only:
        return True, False
    if args.q4_only:
        return False, True
    return True, True


def _human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    units = ["KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        size /= 1024.0
        if size < 1024.0:
            return f"{size:.2f} {unit}"
    return f"{size:.2f} PB"


def _eta_text(size_bytes: int, assumed_upload_mbps: float) -> str:
    if assumed_upload_mbps <= 0:
        return "unknown"
    bytes_per_second = assumed_upload_mbps * 1_000_000 / 8.0
    seconds = size_bytes / bytes_per_second
    minutes = seconds / 60.0
    if minutes < 1:
        return f"{math.ceil(seconds)} sec"
    if minutes < 60:
        return f"{minutes:.1f} min"
    return f"{(minutes / 60.0):.2f} hr"


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _download_hf_snapshot(repo_id: str, destination: Path, allow_patterns: list[str] | None = None) -> Path:
    if snapshot_download is None:
        raise ImportError(f"huggingface_hub is required for seeding: {_HF_IMPORT_ERROR}")
    destination.mkdir(parents=True, exist_ok=True)
    local_path = snapshot_download(
        repo_id=repo_id,
        local_dir=destination,
        local_dir_use_symlinks=False,
        allow_patterns=allow_patterns,
        resume_download=True,
    )
    return Path(local_path).resolve()


def _confirm_force_grok(engine_id: str, force_grok: bool) -> None:
    if not VaultPaths.is_blocked_engine(engine_id):
        return
    if not force_grok:
        raise ValueError(f"Engine '{engine_id}' is blocked. Pass --force-grok to continue.")
    warning = (
        "Grok-1 is 300 GB. This will take several hours.\n"
        "Grok is used as a validation oracle only and is not required\n"
        "for initial training. Continue? [y/N]"
    )
    print(warning)
    answer = input().strip().lower()
    if answer not in {"y", "yes"}:
        raise ValueError("Grok seed cancelled by operator.")


def _upload_tree(
    connector: B2Connector,
    *,
    local_root: Path,
    remote_prefix: str,
    resume: bool,
    assumed_upload_mbps: float,
) -> dict[str, int]:
    uploaded = 0
    skipped = 0
    bytes_transferred = 0
    files = _iter_files(local_root)
    for path in files:
        relative = path.relative_to(local_root).as_posix()
        remote_key = f"{remote_prefix}{relative}"
        file_size = path.stat().st_size
        eta = _eta_text(file_size, assumed_upload_mbps)
        if resume and connector.file_exists(remote_key):
            print(f"[SKIP] {relative} ({_human_size(file_size)}) already exists in vault")
            skipped += 1
            continue

        print(
            f"[UPLOAD] {relative} ({_human_size(file_size)}, est {eta}) -> {remote_key}",
            flush=True,
        )
        started = time.monotonic()
        local_sha = _sha256_file(path)
        connector.upload_file(path, remote_key)
        remote_sha = connector.get_file_sha256(remote_key)
        if remote_sha != local_sha:
            raise RuntimeError(
                f"Checksum mismatch for '{remote_key}': local={local_sha}, remote={remote_sha or 'missing'}"
            )
        elapsed = time.monotonic() - started
        print(f"[OK] {relative} uploaded in {elapsed:.1f}s (sha256 verified)")
        uploaded += 1
        bytes_transferred += file_size

    return {
        "downloaded": 0,
        "uploaded": uploaded,
        "skipped": skipped,
        "bytes_transferred": bytes_transferred,
    }


def _seed_fp16(
    connector: B2Connector,
    engine_id: str,
    engine_cfg: dict[str, Any],
    staging_root: Path,
    *,
    resume: bool,
    assumed_upload_mbps: float,
) -> None:
    repo_id = str(engine_cfg.get("fp16_hf_repo") or "").strip()
    if not repo_id:
        raise ValueError(f"fp16_hf_repo missing for engine '{engine_id}'")
    print(f"[DOWNLOAD] FP16 {engine_id} from HuggingFace repo '{repo_id}'")
    local_path = _download_hf_snapshot(repo_id=repo_id, destination=staging_root / "fp16" / engine_id)
    stats = _upload_tree(
        connector,
        local_root=local_path,
        remote_prefix=VaultPaths.fp16_base(engine_id),
        resume=resume,
        assumed_upload_mbps=assumed_upload_mbps,
    )
    print(f"[SUMMARY] FP16 {engine_id}: {stats}")


def _seed_q4(
    connector: B2Connector,
    engine_id: str,
    engine_cfg: dict[str, Any],
    staging_root: Path,
    *,
    resume: bool,
    assumed_upload_mbps: float,
) -> None:
    repo_id = str(engine_cfg.get("q4_hf_repo") or "").strip()
    if not repo_id:
        print("Q4 will be created after first training cycle on Hetzner")
        return
    print(f"[DOWNLOAD] Q4 {engine_id} from HuggingFace repo '{repo_id}'")
    local_path = _download_hf_snapshot(
        repo_id=repo_id,
        destination=staging_root / "q4" / engine_id,
        allow_patterns=["*.gguf", "*.GGUF"],
    )
    stats = _upload_tree(
        connector,
        local_root=local_path,
        remote_prefix=VaultPaths.q4_serving(engine_id),
        resume=resume,
        assumed_upload_mbps=assumed_upload_mbps,
    )
    print(f"[SUMMARY] Q4 {engine_id}: {stats}")


def main() -> int:
    args = _parse_args()
    connector = B2Connector.from_env()
    manager = PrecisionManager(connector)

    if args.inventory:
        inventory = manager.get_model_inventory()
        print(json.dumps(inventory, indent=2, sort_keys=True))
        return 0

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    engines = _load_engine_catalog(config_path)
    selected_engines = _selected_engines(args, engines)
    seed_fp16, seed_q4 = _resolve_precision_mode(args)

    staging_parent = Path(tempfile.mkdtemp(prefix="s3m-seed-vault-"))
    try:
        print(f"[INFO] Staging directory: {staging_parent}")
        for engine_id in selected_engines:
            print(f"\n=== Seeding engine: {engine_id} ===")
            _confirm_force_grok(engine_id, args.force_grok)
            engine_cfg = engines[engine_id]
            if seed_fp16:
                _seed_fp16(
                    connector,
                    engine_id,
                    engine_cfg,
                    staging_parent,
                    resume=args.resume,
                    assumed_upload_mbps=float(args.assumed_upload_mbps),
                )
            if seed_q4:
                _seed_q4(
                    connector,
                    engine_id,
                    engine_cfg,
                    staging_parent,
                    resume=args.resume,
                    assumed_upload_mbps=float(args.assumed_upload_mbps),
                )
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise

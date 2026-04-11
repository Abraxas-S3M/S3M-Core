#!/usr/bin/env python3
"""Seed S3M Hetzner Object Storage vault tiers: models, datasets, and vendor repositories.

Military/tactical context:
    This orchestration script supports sovereign artifact pre-positioning so
    operators can rehydrate tactical AI capabilities from Hetzner Object Storage
    storage during contested or disconnected operations.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.object_storage import ObjectStorageConnector
from src.storage.precision_manager import PrecisionManager
from src.storage.vault_paths import VaultPaths

try:
    from huggingface_hub import snapshot_download
except Exception as exc:  # pragma: no cover - optional import guard
    snapshot_download = None
    HF_IMPORT_ERROR = exc
else:
    HF_IMPORT_ERROR = None

LOGGER = logging.getLogger("s3m.seed")
RETRY_ATTEMPTS = 3
PRIORITY_DATASET_IDS: tuple[str, ...] = (
    "DAT-001",
    "DAT-002",
    "DAT-003",
    "DAT-014",
    "DAT-015",
    "DAT-025",
    "DAT-032",
)
MODEL_ID_ALIASES: dict[str, str] = {
    "phi3": "phi3-medium",
    "mistral": "mistral-7b",
    "allam": "allam-7b",
    "grok1": "grok-300b",
}
MODEL_CANONICAL_ORDER: tuple[str, ...] = ("phi3-medium", "mistral-7b", "allam-7b", "grok-300b")


@dataclass(frozen=True)
class ModelSource:
    """Model source metadata needed for deterministic vault seeding."""

    engine_id: str
    fp16_repo: str
    q4_repo: str


@dataclass(frozen=True)
class DatasetDefinition:
    """Dataset acquisition metadata from the sovereign registry."""

    dataset_id: str
    name: str
    source_url: str
    size_estimate: str
    download_instructions: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _human_size(size_bytes: int) -> str:
    size = float(max(size_bytes, 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def _run_with_retries(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Execute command with retry policy for transient network faults."""

    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        last_result = result
        if result.returncode == 0:
            return result
        if attempt < RETRY_ATTEMPTS:
            sleep_seconds = 2**attempt
            LOGGER.warning(
                "Command failed on attempt %d/%d; retrying in %ss: %s",
                attempt,
                RETRY_ATTEMPTS,
                sleep_seconds,
                " ".join(command),
            )
            time.sleep(sleep_seconds)

    assert last_result is not None
    return last_result


def _dir_stats(path: Path) -> tuple[int, int]:
    files = [entry for entry in path.rglob("*") if entry.is_file()]
    return sum(entry.stat().st_size for entry in files), len(files)


def _download_hf_snapshot(repo_id: str, destination: Path, *, allow_patterns: list[str] | None = None) -> Path:
    if snapshot_download is None:
        raise RuntimeError(f"huggingface_hub is required but unavailable: {HF_IMPORT_ERROR}")

    destination.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            snapshot_path = snapshot_download(
                repo_id=repo_id,
                local_dir=destination,
                local_dir_use_symlinks=False,
                allow_patterns=allow_patterns,
                resume_download=True,
            )
            return Path(snapshot_path).resolve()
        except Exception as exc:  # noqa: BLE001 - controlled retry around network IO
            if attempt >= RETRY_ATTEMPTS:
                raise
            delay = 2**attempt
            LOGGER.warning(
                "HuggingFace download failed for %s attempt %d/%d (%s), retrying in %ss",
                repo_id,
                attempt,
                RETRY_ATTEMPTS,
                exc,
                delay,
            )
            time.sleep(delay)
    return destination


def _write_marker(tmp_dir: Path, filename: str, fields: dict[str, str]) -> Path:
    marker_path = tmp_dir / filename
    lines = [f"{key}={value}" for key, value in fields.items()]
    marker_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return marker_path


def _parse_marker_text(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _load_model_catalog(config_path: Path) -> dict[str, ModelSource]:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    engines = payload.get("engines", {}) if isinstance(payload, dict) else {}
    if not isinstance(engines, dict):
        return {}

    catalog: dict[str, ModelSource] = {}
    for raw_id, details in engines.items():
        if not isinstance(details, dict):
            continue
        alias = str(raw_id).strip()
        canonical_id = MODEL_ID_ALIASES.get(alias, alias)
        fp16_repo = str(details.get("hf_repo", "")).strip()
        q4_repo = str(details.get("hf_repo_gguf", "")).strip()
        if fp16_repo:
            catalog[canonical_id] = ModelSource(engine_id=canonical_id, fp16_repo=fp16_repo, q4_repo=q4_repo)
    return catalog


def _select_models(catalog: dict[str, ModelSource], requested: list[str]) -> list[ModelSource]:
    if requested:
        normalized = [MODEL_ID_ALIASES.get(item.strip(), item.strip()) for item in requested if item.strip()]
        missing = [item for item in normalized if item not in catalog]
        if missing:
            raise ValueError(f"Unknown engine id(s): {missing}. Available: {sorted(catalog)}")
        return [catalog[item] for item in normalized]

    ordered: list[ModelSource] = []
    for engine_id in MODEL_CANONICAL_ORDER:
        if engine_id in catalog:
            ordered.append(catalog[engine_id])
    for engine_id in sorted(catalog):
        if engine_id not in {entry.engine_id for entry in ordered}:
            ordered.append(catalog[engine_id])
    return ordered


def _seed_models(connector: ObjectStorageConnector, model_sources: list[ModelSource], *, force_grok: bool) -> int:
    if not model_sources:
        LOGGER.warning("No model sources found; skipping model seeding")
        return 0

    failures = 0
    with tempfile.TemporaryDirectory(prefix="s3m-seed-models-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        for source in model_sources:
            if VaultPaths.is_blocked_engine(source.engine_id) and not force_grok:
                LOGGER.warning(
                    "Skipping blocked engine '%s' (use --force-grok to override)",
                    source.engine_id,
                )
                continue

            LOGGER.info("Seeding model FP16 %s from %s", source.engine_id, source.fp16_repo)
            try:
                fp16_dir = _download_hf_snapshot(
                    source.fp16_repo,
                    tmp_dir / "models" / source.engine_id / "fp16",
                )
                connector.sync_up(fp16_dir, VaultPaths.fp16_base(source.engine_id))
                shutil.rmtree(fp16_dir, ignore_errors=True)

                if source.q4_repo:
                    LOGGER.info("Seeding model Q4 %s from %s", source.engine_id, source.q4_repo)
                    q4_dir = _download_hf_snapshot(
                        source.q4_repo,
                        tmp_dir / "models" / source.engine_id / "q4",
                        allow_patterns=["*.gguf", "*.GGUF"],
                    )
                    connector.sync_up(q4_dir, VaultPaths.q4_serving(source.engine_id))
                    shutil.rmtree(q4_dir, ignore_errors=True)
                else:
                    LOGGER.info("No Q4 source configured for %s; skipped", source.engine_id)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                LOGGER.exception("Model seeding failed for %s: %s", source.engine_id, exc)

    return 1 if failures else 0


def _load_dataset_registry(registry_path: Path) -> list[DatasetDefinition]:
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    datasets_raw = payload.get("datasets", []) if isinstance(payload, dict) else []
    datasets: list[DatasetDefinition] = []
    for item in datasets_raw:
        if not isinstance(item, dict):
            continue
        dataset_id = str(item.get("id", "")).strip()
        if not dataset_id:
            continue
        datasets.append(
            DatasetDefinition(
                dataset_id=dataset_id,
                name=str(item.get("name", dataset_id)).strip(),
                source_url=str(item.get("source_url", "")).strip(),
                size_estimate=str(item.get("size_estimate", "unknown")).strip(),
                download_instructions=str(item.get("download_instructions", "")).strip(),
            )
        )
    return datasets


def _select_datasets(datasets: list[DatasetDefinition], dataset_ids: list[str], priority_only: bool) -> list[DatasetDefinition]:
    selected = datasets
    if dataset_ids:
        requested = {item.strip() for item in dataset_ids if item.strip()}
        selected = [entry for entry in selected if entry.dataset_id in requested]
        missing = sorted(requested - {entry.dataset_id for entry in selected})
        if missing:
            raise ValueError(f"Unknown dataset ids: {missing}")
    if priority_only:
        selected = [entry for entry in selected if entry.dataset_id in PRIORITY_DATASET_IDS]
    return selected


def _dataset_strategy(source_url: str) -> str:
    lowered = source_url.lower()
    if "kaggle.com" in lowered:
        return "kaggle"
    if "huggingface.co" in lowered:
        return "huggingface"
    if "github.com" in lowered:
        return "github"
    if source_url.startswith("http://") or source_url.startswith("https://"):
        return "direct"
    return "manual"


def _kaggle_slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if "datasets" in segments:
        index = segments.index("datasets")
        if len(segments) >= index + 3:
            return f"{segments[index + 1]}/{segments[index + 2]}"
    return ""


def _hf_dataset_repo_from_url(url: str) -> str:
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return ""
    if segments[0] == "datasets":
        segments = segments[1:]
    if "tree" in segments:
        segments = segments[: segments.index("tree")]
    if len(segments) >= 2:
        return f"{segments[0]}/{segments[1]}"
    return ""


def _is_gated_error(stderr_text: str) -> bool:
    lowered = stderr_text.lower()
    markers = ("403", "401", "forbidden", "unauthorized", "accept", "gated", "terms")
    return any(marker in lowered for marker in markers)


def _download_dataset_once(entry: DatasetDefinition, staging_dir: Path) -> tuple[bool, str]:
    strategy = _dataset_strategy(entry.source_url)
    if strategy == "manual":
        return False, (
            f"Dataset {entry.dataset_id} has non-automatable source '{entry.source_url}'. "
            f"Manual staging required. {entry.download_instructions}"
        )

    if strategy == "kaggle":
        if not os.getenv("KAGGLE_USERNAME") or not os.getenv("KAGGLE_KEY"):
            return False, "Kaggle credentials missing (KAGGLE_USERNAME/KAGGLE_KEY)."
        slug = _kaggle_slug_from_url(entry.source_url)
        if not slug:
            return False, "Unable to parse Kaggle dataset slug from URL."
        command = ["kaggle", "datasets", "download", "-d", slug, "-p", str(staging_dir), "--unzip"]
    elif strategy == "huggingface":
        repo_id = _hf_dataset_repo_from_url(entry.source_url)
        if not repo_id:
            return False, "Unable to parse HuggingFace dataset repo id from URL."
        command = [
            "huggingface-cli",
            "download",
            repo_id,
            "--repo-type",
            "dataset",
            "--local-dir",
            str(staging_dir),
            "--resume-download",
        ]
    elif strategy == "github":
        command = ["git", "clone", "--depth", "1", entry.source_url, str(staging_dir / "repo")]
    else:
        filename = Path(urlparse(entry.source_url).path).name or f"{entry.dataset_id}.download"
        target_file = staging_dir / filename
        wget_result = _run_with_retries(["wget", "-O", str(target_file), entry.source_url])
        if wget_result.returncode == 0:
            return True, "ok"
        curl_result = _run_with_retries(["curl", "-L", "-o", str(target_file), entry.source_url])
        if curl_result.returncode == 0:
            return True, "ok"
        stderr_text = "\n".join([wget_result.stderr, curl_result.stderr]).strip()
        if _is_gated_error(stderr_text):
            return False, f"Gated source detected. Manual acceptance/download required. {entry.download_instructions}"
        return False, stderr_text or "direct download command failed"

    result = _run_with_retries(command)
    if result.returncode != 0:
        if _is_gated_error("\n".join([result.stdout, result.stderr])):
            return False, f"Gated source detected. Manual acceptance/download required. {entry.download_instructions}"
        return False, (result.stderr or result.stdout or "command failed").strip()

    if strategy == "github":
        git_dir = staging_dir / "repo" / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir, ignore_errors=True)
    return True, "ok"


def _seed_datasets(connector: ObjectStorageConnector, datasets: list[DatasetDefinition]) -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="s3m-seed-datasets-") as tmp_dir_name:
        tmp_root = Path(tmp_dir_name)
        for entry in datasets:
            remote_prefix = f"datasets/training-data/{entry.dataset_id}/"
            marker_key = f"{remote_prefix}.seeded"
            if connector.file_exists(marker_key):
                LOGGER.info("Skipping dataset %s (marker exists)", entry.dataset_id)
                continue

            staging_dir = tmp_root / entry.dataset_id
            staging_dir.mkdir(parents=True, exist_ok=True)
            LOGGER.info(
                "Seeding dataset %s (%s, est %s) from %s",
                entry.dataset_id,
                entry.name,
                entry.size_estimate,
                entry.source_url,
            )

            ok, status_message = _download_dataset_once(entry, staging_dir)
            if not ok:
                LOGGER.warning("Dataset %s skipped: %s", entry.dataset_id, status_message)
                shutil.rmtree(staging_dir, ignore_errors=True)
                continue

            size_bytes, file_count = _dir_stats(staging_dir)
            LOGGER.info(
                "Uploading dataset %s (%s across %d files)",
                entry.dataset_id,
                _human_size(size_bytes),
                file_count,
            )

            try:
                connector.sync_up(staging_dir, remote_prefix)
                marker_file = _write_marker(
                    tmp_root,
                    f"{entry.dataset_id}.seeded",
                    {
                        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                        "dataset_id": entry.dataset_id,
                        "size_bytes": str(size_bytes),
                        "file_count": str(file_count),
                        "source_url": entry.source_url,
                    },
                )
                connector.upload_file(marker_file, marker_key)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                LOGGER.exception("Dataset seeding failed for %s: %s", entry.dataset_id, exc)
            finally:
                shutil.rmtree(staging_dir, ignore_errors=True)

    return 1 if failures else 0


def _ensure_vendor_manifest(repo_root: Path) -> Path:
    repos_path = repo_root / "scripts" / "vendor" / "repos.txt"
    if repos_path.exists() and repos_path.stat().st_size > 0:
        return repos_path

    builder = repo_root / "scripts" / "vendor" / "build_repos_manifest.py"
    if not builder.exists():
        raise FileNotFoundError(f"Missing vendor manifest builder: {builder}")
    LOGGER.info("repos.txt missing; generating via build_repos_manifest.py")
    subprocess.run([sys.executable, str(builder)], cwd=str(repo_root), check=True)
    if not repos_path.exists() or repos_path.stat().st_size == 0:
        raise RuntimeError("Failed to generate scripts/vendor/repos.txt")
    return repos_path


def _seed_vendor(repo_root: Path, *, domain: str, parallel: int, dry_run: bool) -> int:
    _ensure_vendor_manifest(repo_root)
    clone_script = repo_root / "scripts" / "vendor" / "clone_all.sh"
    if not clone_script.exists():
        raise FileNotFoundError(f"Missing vendor clone script: {clone_script}")
    clone_script.chmod(clone_script.stat().st_mode | 0o111)

    command = ["bash", str(clone_script), "--parallel", str(parallel)]
    if domain:
        command.extend(["--domain", domain])
    if dry_run:
        command.append("--dry-run")

    LOGGER.info("Launching vendor seeding: %s", " ".join(command))
    process = subprocess.Popen(command, cwd=str(repo_root))
    process.wait()
    return int(process.returncode)


def _read_marker(connector: ObjectStorageConnector, key: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="s3m-marker-read-") as tmp_dir_name:
        tmp_path = Path(tmp_dir_name) / "marker.txt"
        connector.download_file(key, tmp_path)
        return _parse_marker_text(tmp_path.read_text(encoding="utf-8"))


def _non_comment_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def _format_engine_line(engine_id: str, payload: dict[str, Any]) -> str:
    has_fp16 = bool(payload.get("has_fp16"))
    has_q4 = bool(payload.get("has_q4"))
    fp16_size = float(payload.get("fp16_size_gb", 0.0))
    q4_size = float(payload.get("q4_size_gb", 0.0))
    fp16_text = f"FP16 {'✓' if has_fp16 else '✗'} ({fp16_size:.1f} GB)" if has_fp16 else "FP16 ✗ (not uploaded)"
    q4_text = f"Q4 {'✓' if has_q4 else '✗'} ({q4_size:.1f} GB)" if has_q4 else "Q4 ✗ (not uploaded)"
    return f"  {engine_id:<14} {fp16_text:<24} {q4_text}"


def _format_missing(ids: list[str], *, max_items: int = 10) -> str:
    if not ids:
        return "-"
    if len(ids) <= max_items:
        return ", ".join(ids)
    shown = ", ".join(ids[:max_items])
    return f"{shown}, ... ({len(ids) - max_items} more)"


def _inventory_report(connector: ObjectStorageConnector, repo_root: Path, datasets_registry: list[DatasetDefinition]) -> str:
    manager = PrecisionManager(connector)
    model_inventory = manager.get_model_inventory()
    model_lines = [_format_engine_line(engine_id, model_inventory.get(engine_id, {})) for engine_id in MODEL_CANONICAL_ORDER]
    model_subtotal_gb = sum(
        float(payload.get("fp16_size_gb", 0.0)) + float(payload.get("q4_size_gb", 0.0))
        for payload in model_inventory.values()
    )

    expected_dataset_ids = sorted(entry.dataset_id for entry in datasets_registry)
    dataset_marker_keys = sorted(
        key for key in connector.list_keys("datasets/training-data/") if key.endswith("/.seeded")
    )
    uploaded_dataset_ids = sorted({Path(key).parts[-2] for key in dataset_marker_keys})
    missing_dataset_ids = sorted(set(expected_dataset_ids) - set(uploaded_dataset_ids))
    dataset_bytes = 0
    for key in dataset_marker_keys:
        try:
            dataset_bytes += int(_read_marker(connector, key).get("size_bytes", "0") or 0)
        except Exception:  # noqa: BLE001
            LOGGER.debug("Unable to parse dataset marker %s", key, exc_info=True)
    dataset_size_gb = dataset_bytes / (1024**3)

    repos_manifest = repo_root / "scripts" / "vendor" / "repos.txt"
    expected_vendor_lines = _non_comment_lines(repos_manifest)
    expected_vendor_total = len(expected_vendor_lines)
    expected_domain_counts: dict[str, int] = {}
    for line in expected_vendor_lines:
        parts = line.split("|")
        if len(parts) < 2:
            continue
        expected_domain_counts[parts[0]] = expected_domain_counts.get(parts[0], 0) + 1

    vendor_marker_keys = sorted(key for key in connector.list_keys("vendor/") if key.endswith("/.cloned"))
    cloned_total = len(vendor_marker_keys)
    cloned_domain_counts: dict[str, int] = {}
    vendor_bytes = 0
    for key in vendor_marker_keys:
        marker_parts = Path(key).parts
        if len(marker_parts) >= 3:
            domain = marker_parts[1]
            cloned_domain_counts[domain] = cloned_domain_counts.get(domain, 0) + 1
        try:
            vendor_bytes += int(_read_marker(connector, key).get("size_bytes", "0") or 0)
        except Exception:  # noqa: BLE001
            LOGGER.debug("Unable to parse vendor marker %s", key, exc_info=True)
    vendor_size_gb = vendor_bytes / (1024**3)

    complete_domains: list[str] = []
    partial_domains: list[str] = []
    empty_domains: list[str] = []
    for domain in sorted(expected_domain_counts):
        expected = expected_domain_counts[domain]
        cloned = cloned_domain_counts.get(domain, 0)
        if cloned == 0:
            empty_domains.append(domain)
        elif cloned >= expected:
            complete_domains.append(domain)
        else:
            partial_domains.append(f"{domain} ({cloned}/{expected})")

    total_usage_gb = model_subtotal_gb + dataset_size_gb + vendor_size_gb
    capacity_gb = 2048.0
    usage_pct = (total_usage_gb / capacity_gb) * 100.0 if capacity_gb > 0 else 0.0

    lines = [
        "S3M HETZNER OBJECT STORAGE VAULT INVENTORY",
        "═══════════════════════════════════════════",
        "MODELS (FP16 + Q4):",
        *model_lines,
        "  ─────────────────────────────────────────",
        f"  Subtotal: {model_subtotal_gb:.1f} GB",
        "",
        "DATASETS:",
        f"  {len(expected_dataset_ids)} registered, {len(uploaded_dataset_ids)} uploaded ({dataset_size_gb:.1f} GB)",
        f"  Uploaded: {_format_missing(uploaded_dataset_ids, max_items=20)}",
        f"  Missing:  {_format_missing(missing_dataset_ids, max_items=20)}",
        "",
        "VENDOR REPOS:",
        f"  {expected_vendor_total} expected, {cloned_total} cloned ({vendor_size_gb:.1f} GB)",
        f"  Domains complete: {_format_missing(complete_domains)}",
        f"  Domains partial:  {_format_missing(partial_domains)}",
        f"  Domains empty:    {_format_missing(empty_domains)}",
        "",
        f"TOTAL VAULT USAGE: {total_usage_gb:.1f} GB / {capacity_gb:.0f} GB ({usage_pct:.1f}%)",
        "═══════════════════════════════════════════",
    ]
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed S3M Hetzner Object Storage vault tiers")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--models", action="store_true", help="Seed AI model weights")
    mode.add_argument("--datasets", action="store_true", help="Seed training datasets")
    mode.add_argument("--vendor", action="store_true", help="Seed external vendor repositories")
    mode.add_argument("--all", action="store_true", help="Seed models, datasets, and vendor repos")
    mode.add_argument("--inventory", action="store_true", help="Print current vault inventory")

    parser.add_argument("--engine", action="append", default=[], help="Engine id for --models (repeatable)")
    parser.add_argument("--force-grok", action="store_true", help="Allow blocked Grok model seeding")

    parser.add_argument("--dataset-id", action="append", default=[], help="Dataset id for --datasets (repeatable)")
    parser.add_argument("--priority", action="store_true", help="For --datasets, only seed the 7 priority datasets")

    parser.add_argument("--domain", default="", help="Domain filter for --vendor")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers for --vendor")
    parser.add_argument("--dry-run", action="store_true", help="Dry run for --vendor")

    parser.add_argument("--models-config", default="configs/engines.yaml", help="Model source registry file")
    parser.add_argument("--datasets-config", default="configs/datasets/registry.yaml", help="Dataset registry file")
    args = parser.parse_args()
    if args.parallel < 1:
        parser.error("--parallel must be >= 1")
    return args


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    repo_root = _project_root()
    connector = ObjectStorageConnector()

    datasets_registry_path = (repo_root / args.datasets_config).resolve()
    datasets_registry = _load_dataset_registry(datasets_registry_path)

    if args.inventory:
        print(_inventory_report(connector, repo_root, datasets_registry))
        return 0

    if args.models or args.all:
        models_config_path = (repo_root / args.models_config).resolve()
        model_catalog = _load_model_catalog(models_config_path)
        selected_models = _select_models(model_catalog, args.engine)
        rc = _seed_models(connector, selected_models, force_grok=bool(args.force_grok))
        if args.models:
            return rc
    else:
        rc = 0

    if args.datasets or args.all:
        selected_datasets = _select_datasets(datasets_registry, args.dataset_id, bool(args.priority))
        datasets_rc = _seed_datasets(connector, selected_datasets)
        if args.datasets:
            return datasets_rc
        rc = max(rc, datasets_rc)

    if args.vendor or args.all:
        vendor_rc = _seed_vendor(
            repo_root,
            domain=str(args.domain).strip(),
            parallel=max(1, int(args.parallel)),
            dry_run=bool(args.dry_run),
        )
        if args.vendor:
            return vendor_rc
        rc = max(rc, vendor_rc)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())

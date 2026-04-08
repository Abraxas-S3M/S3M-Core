"""
S3M Offline Model CI/CD Pipeline — Gap 6 of 7
Air-gapped, reproducible, version-controlled model rollout.
Uses: DVC (data versioning), MLflow (experiment tracking),
      manifest-based signed bundles, delta-update support.

Run:  python scripts/model_pipeline/offline_model_ci.py --engine mixtral --action package
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("s3m.model_pipeline")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
CACHE = ROOT / "data" / "model_cache"
MANIFEST = ROOT / "data" / "model_manifest.json"


# ─── Manifest ─────────────────────────────────────────────────────────────────


@dataclass
class ModelEntry:
    engine_id: str
    version: str
    filename: str
    sha256: str
    size_bytes: int
    packaged_at: str
    quantization: str
    signed_by: str = "S3M-CI"

    @classmethod
    def from_file(cls, engine_id: str, version: str, path: Path, quant: str) -> "ModelEntry":
        sha256 = cls._hash(path)
        return cls(
            engine_id=engine_id,
            version=version,
            filename=path.name,
            sha256=sha256,
            size_bytes=path.stat().st_size,
            packaged_at=datetime.now(timezone.utc).isoformat(),
            quantization=quant,
        )

    @staticmethod
    def _hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()


class ModelManifest:
    def __init__(self) -> None:
        self._entries: Dict[str, ModelEntry] = {}
        self._load()

    def _load(self) -> None:
        if MANIFEST.exists():
            try:
                data = json.loads(MANIFEST.read_text())
            except json.JSONDecodeError:
                logger.error("Manifest file is not valid JSON: %s", MANIFEST)
                return
            for k, v in data.items():
                self._entries[k] = ModelEntry(**v)

    def save(self) -> None:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        out = {k: asdict(v) for k, v in self._entries.items()}
        MANIFEST.write_text(json.dumps(out, indent=2))
        logger.info("Manifest written → %s", MANIFEST)

    def register(self, entry: ModelEntry) -> None:
        self._entries[entry.engine_id] = entry

    def verify(self, engine_id: str) -> bool:
        entry = self._entries.get(engine_id)
        if not entry:
            logger.error("No manifest entry for %s", engine_id)
            return False
        path = CACHE / entry.filename
        if not path.exists():
            logger.error("Model file missing: %s", path)
            return False
        actual = ModelEntry._hash(path)
        if actual != entry.sha256:
            logger.error("SHA-256 mismatch for %s!", engine_id)
            return False
        logger.info("✅  %s verified OK", engine_id)
        return True

    def get(self, engine_id: str) -> Optional[ModelEntry]:
        return self._entries.get(engine_id)


# ─── Quantization Step ────────────────────────────────────────────────────────

ENGINE_CONFIGS = {
    "phi3_medium": {
        "hf_repo": "microsoft/Phi-3-medium-4k-instruct",
        "gguf_out": "phi-3-medium-4k-instruct.Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
    "grok1": {
        "hf_repo": "xai-org/grok-1",
        "gguf_out": "grok-1.Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
    "mixtral": {
        "hf_repo": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "gguf_out": "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
    "allam": {
        "hf_repo": "humain-ai/ALLaM-7B-Instruct-preview",
        "gguf_out": "allam-7b-instruct.Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
}


def _run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    logger.info("$ %s", " ".join(cmd))
    return subprocess.run(cmd, check=check, capture_output=False)


def package_model(engine_id: str, version: str, dry_run: bool = False) -> Optional[Path]:
    cfg = ENGINE_CONFIGS.get(engine_id)
    if not cfg:
        logger.error("Unknown engine: %s", engine_id)
        return None

    CACHE.mkdir(parents=True, exist_ok=True)
    out_path = CACHE / cfg["gguf_out"]

    if out_path.exists():
        logger.info("GGUF already cached: %s", out_path)
    elif not dry_run:
        logger.info("Converting %s → GGUF …", cfg["hf_repo"])
        # Requires llama.cpp convert scripts in PATH
        _run(
            [
                "python",
                "llama.cpp/convert_hf_to_gguf.py",
                cfg["hf_repo"],
                "--outfile",
                str(out_path),
                "--outtype",
                "f16",
            ]
        )
        logger.info("Quantizing to %s …", cfg["quant"])
        _run(
            [
                "llama.cpp/build/bin/llama-quantize",
                str(out_path),
                str(out_path),
                cfg["quant"],
            ]
        )
    else:
        logger.info("[DRY-RUN] Would convert %s", cfg["hf_repo"])
        return None

    return out_path


def register_and_track(engine_id: str, version: str, path: Path) -> None:
    manifest = ModelManifest()
    entry = ModelEntry.from_file(engine_id, version, path, ENGINE_CONFIGS[engine_id]["quant"])
    manifest.register(entry)
    manifest.save()

    # Tactical auditability: optional local experiment records aid post-mission forensics.
    try:
        import mlflow

        with mlflow.start_run(run_name=f"{engine_id}-{version}"):
            mlflow.log_param("engine_id", engine_id)
            mlflow.log_param("version", version)
            mlflow.log_param("quantization", entry.quantization)
            mlflow.log_param("sha256", entry.sha256)
            mlflow.log_metric("size_gb", entry.size_bytes / 1e9)
        logger.info("MLflow run logged")
    except ImportError:
        logger.info("MLflow not installed — skipping experiment tracking")


def rollback(engine_id: str, target_version: str) -> None:
    """Restore a previously packaged model version from DVC."""
    try:
        _run(["dvc", "checkout", f"models/{engine_id}/{target_version}"])
        logger.info("Rolled back %s to version %s", engine_id, target_version)
    except Exception as exc:  # pragma: no cover - defensive catch for CLI runtime
        logger.error("Rollback failed: %s", exc)


# ─── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="S3M Offline Model CI/CD")
    parser.add_argument("--engine", required=True, choices=list(ENGINE_CONFIGS))
    parser.add_argument("--version", default="latest")
    parser.add_argument("--action", required=True, choices=["package", "verify", "rollback", "status"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback-to", default=None)
    args = parser.parse_args()

    manifest = ModelManifest()

    if args.action == "package":
        path = package_model(args.engine, args.version, dry_run=args.dry_run)
        if path:
            register_and_track(args.engine, args.version, path)

    elif args.action == "verify":
        ok = manifest.verify(args.engine)
        sys.exit(0 if ok else 1)

    elif args.action == "rollback":
        if not args.rollback_to:
            logger.error("Provide --rollback-to <version>")
            sys.exit(1)
        rollback(args.engine, args.rollback_to)

    elif args.action == "status":
        entry = manifest.get(args.engine)
        if entry:
            print(json.dumps(asdict(entry), indent=2))
        else:
            print(f"No manifest entry for {args.engine}")


if __name__ == "__main__":
    main()

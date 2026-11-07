#!/usr/bin/env python3
"""
Verify an offline Cortex update bundle before loading any artifact.

Tactical context: disconnected sites must reject tampered payloads before they
touch operational networks. Every hash and signature is checked against pinned keys.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Iterable, List, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.cortex.bundle_common import (  # noqa: E402
    BUNDLE_FORMAT,
    INDEX_NAME,
    INDEX_SIG_NAME,
    expected_signature_path,
    sha256_file,
)
from scripts.cortex.signing import verify_blob  # noqa: E402


class BundleVerificationError(Exception):
    """Raised when any integrity or signature check fails."""


def _load_pinned_keys(trust_dir: Path) -> List[Path]:
    if not trust_dir.is_dir():
        raise BundleVerificationError(f"trust directory not found: {trust_dir}")
    keys = sorted(trust_dir.glob("*.pub"))
    if not keys:
        raise BundleVerificationError(f"no pinned *.pub keys in {trust_dir}")
    return keys


def _verify_with_any_key(
    artifact: Path, signature: Path, public_keys: Sequence[Path]
) -> None:
    errors: List[str] = []
    for key in public_keys:
        try:
            verify_blob(artifact, signature, key)
            return
        except Exception as exc:  # noqa: BLE001 — aggregate cosign failures
            errors.append(f"{key.name}: {exc}")
    raise BundleVerificationError(
        f"signature verification failed for {artifact}: " + "; ".join(errors)
    )


def _extract_bundle(bundle_path: Path, dest: Path) -> None:
    if not bundle_path.is_file():
        raise BundleVerificationError(f"bundle not found: {bundle_path}")
    with tarfile.open(bundle_path, "r") as archive:
        archive.extractall(dest, filter="data")


def verify_bundle_root(root: Path, public_keys: Sequence[Path]) -> dict:
    index_path = root / INDEX_NAME
    index_sig = root / INDEX_SIG_NAME
    if not index_path.is_file() or not index_sig.is_file():
        raise BundleVerificationError("bundle missing signed manifest/index.json")

    _verify_with_any_key(index_path, index_sig, public_keys)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("bundle_format") != BUNDLE_FORMAT:
        raise BundleVerificationError(
            f"unexpected bundle_format: {index.get('bundle_format')!r}"
        )

    artifacts = index.get("artifacts") or []
    if not isinstance(artifacts, list) or not artifacts:
        raise BundleVerificationError("index contains no artifacts")

    for entry in artifacts:
        rel = str(entry.get("path", ""))
        expected_hash = str(entry.get("sha256", ""))
        if not rel or not expected_hash:
            raise BundleVerificationError(f"invalid index entry: {entry!r}")

        target = root / rel
        if not target.is_file():
            raise BundleVerificationError(f"missing artifact: {rel}")

        actual_hash = sha256_file(target)
        if actual_hash != expected_hash:
            raise BundleVerificationError(
                f"hash mismatch for {rel}: expected {expected_hash}, got {actual_hash}"
            )

        sig_rel = expected_signature_path(rel)
        signature = root / sig_rel
        if not signature.is_file():
            raise BundleVerificationError(f"missing signature: {sig_rel}")
        _verify_with_any_key(target, signature, public_keys)

    return index


def verify_bundle(bundle_path: Path, trust_dir: Path) -> dict:
    keys = _load_pinned_keys(trust_dir)
    with tempfile.TemporaryDirectory(prefix="cortex-verify-") as tmp:
        root = Path(tmp)
        _extract_bundle(bundle_path, root)
        return verify_bundle_root(root, keys)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Cortex offline update bundle.")
    parser.add_argument("bundle", type=Path, help="Path to cortex-update-<version>.tar")
    parser.add_argument(
        "--trust-dir",
        type=Path,
        required=True,
        help="Directory of pinned cosign *.pub keys (customer HSM-backed keys in production).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not shutil.which("cosign"):
        print("cosign is required for bundle verification", file=sys.stderr)
        return 2

    try:
        index = verify_bundle(args.bundle, args.trust_dir)
    except BundleVerificationError as exc:
        print(f"VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "cortex_version": index.get("cortex_version"),
                "artifact_count": len(index.get("artifacts") or []),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

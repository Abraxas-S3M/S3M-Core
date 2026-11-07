"""Cosign key-based signing for Cortex offline bundles (supports PKCS#11 HSM keys)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _cosign_bin() -> str:
    path = shutil.which("cosign")
    if not path:
        raise RuntimeError("cosign not found on PATH; install Sigstore cosign for signing.")
    return path


def _key_ref(private_key: Optional[Path]) -> str:
    """Resolve signing key: explicit file, PKCS#11 URI, or env COSIGN_PRIVATE_KEY."""
    pkcs11_module = os.environ.get("COSIGN_PKCS11_MODULE", "").strip()
    pkcs11_token = os.environ.get("COSIGN_PKCS11_TOKEN_LABEL", "").strip()
    if pkcs11_module:
        # Air-gapped customer HSM — key never leaves the module.
        slot = os.environ.get("COSIGN_PKCS11_SLOT", "0")
        key_id = os.environ.get("COSIGN_PKCS11_KEY_ID", "01")
        return f"pkcs11:module-path={pkcs11_module};slot={slot};id={key_id}?token={pkcs11_token}"

    if private_key is not None:
        return str(private_key)

    env_key = os.environ.get("COSIGN_PRIVATE_KEY", "").strip()
    if env_key:
        return env_key

    raise RuntimeError("No signing key: pass --key, set COSIGN_PRIVATE_KEY, or PKCS#11 env vars.")


def sign_blob(
    artifact: Path,
    signature_path: Path,
    *,
    private_key: Optional[Path] = None,
    password_env: str = "COSIGN_PASSWORD",
) -> None:
    """Sign a single artifact with cosign sign-blob (detached signature)."""
    cosign = _cosign_bin()
    key = _key_ref(private_key)
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        cosign,
        "sign-blob",
        "--yes",
        "--tlog-upload=false",
        "--key",
        key,
        "--output-signature",
        str(signature_path),
        str(artifact),
    ]
    env = os.environ.copy()
    subprocess.run(cmd, check=True, env=env)


def verify_blob(
    artifact: Path,
    signature_path: Path,
    public_key: Path,
) -> None:
    cosign = _cosign_bin()
    subprocess.run(
        [
            cosign,
            "verify-blob",
            "--key",
            str(public_key),
            "--signature",
            str(signature_path),
            "--insecure-ignore-tlog=true",
            str(artifact),
        ],
        check=True,
    )


def slsa_provenance_stub(image_ref: str, output: Path, builder_id: str = "https://github.com/Abraxas-S3M/S3M-Core/.github/workflows/cortex-customer-release.yml") -> None:
    """Write minimal in-toto SLSA provenance JSON for offline bundle inclusion."""
    import json
    from datetime import datetime, timezone

    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": image_ref, "digest": {"sha256": "pending"}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://mobyproject.org/buildkit@v1",
                "externalParameters": {"image": image_ref},
            },
            "runDetails": {
                "builder": {"id": builder_id},
                "metadata": {"invocationId": datetime.now(timezone.utc).isoformat()},
            },
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(statement, indent=2) + "\n", encoding="utf-8")

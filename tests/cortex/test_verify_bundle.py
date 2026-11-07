"""Unit tests for offline Cortex bundle verification."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _require_cosign() -> str:
    cosign = shutil.which("cosign")
    if not cosign:
        pytest.skip("cosign not installed")
    return cosign


def _generate_keypair(work: Path) -> tuple[Path, Path]:
    _require_cosign()
    priv = work / "cosign.key"
    pub = work / "cosign.pub"
    env = os.environ.copy()
    env["COSIGN_PASSWORD"] = "test-pass"
    subprocess.run(
        ["cosign", "generate-key-pair"],
        cwd=work,
        check=True,
        env=env,
    )
    assert priv.is_file() and pub.is_file()
    return priv, pub


def _build_bundle(work: Path, priv: Path, version: str = "0.0.0-ci") -> Path:
    out = work / f"cortex-update-{version}.tar"
    subprocess.run(
        [
            "python3",
            str(REPO_ROOT / "scripts/cortex/build_bundle.py"),
            "--version",
            version,
            "--output",
            str(out),
            "--repo-root",
            str(REPO_ROOT),
            "--private-key",
            str(priv),
            "--stub-images",
        ],
        check=True,
        cwd=REPO_ROOT,
        env={**os.environ, "COSIGN_PASSWORD": "test-pass"},
    )
    return out


def test_verify_bundle_passes_for_signed_bundle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        priv, pub = _generate_keypair(work)
        trust = work / "trust"
        trust.mkdir()
        shutil.copy(pub, trust / "customer.pub")

        bundle = _build_bundle(work, priv)
        proc = subprocess.run(
            [
                "python3",
                str(REPO_ROOT / "scripts/cortex/verify_bundle.py"),
                str(bundle),
                "--trust-dir",
                str(trust),
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "COSIGN_PASSWORD": "test-pass"},
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["status"] == "ok"
        assert payload["artifact_count"] > 0


def test_verify_bundle_rejects_tampered_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        priv, pub = _generate_keypair(work)
        trust = work / "trust"
        trust.mkdir()
        shutil.copy(pub, trust / "customer.pub")

        bundle = _build_bundle(work, priv)
        tampered = work / "tampered.tar"
        shutil.copy(bundle, tampered)

        with tempfile.TemporaryDirectory() as extract_tmp:
            extract = Path(extract_tmp)
            with tarfile.open(tampered, "r") as archive:
                archive.extractall(extract, filter="data")

            victim = next(extract.glob("images/*/image.tar"))
            victim.write_bytes(victim.read_bytes() + b"TAMPER")

            with tarfile.open(tampered, "w") as archive:
                for path in sorted(extract.rglob("*")):
                    if path.is_file():
                        archive.add(path, arcname=str(path.relative_to(extract)))

        proc = subprocess.run(
            [
                "python3",
                str(REPO_ROOT / "scripts/cortex/verify_bundle.py"),
                str(tampered),
                "--trust-dir",
                str(trust),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1
        assert "VERIFICATION FAILED" in proc.stderr


def test_verify_bundle_rejects_unpinned_key() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        priv, _pub = _generate_keypair(work)
        other = work / "other"
        other.mkdir()
        subprocess.run(
            ["cosign", "generate-key-pair"],
            cwd=other,
            check=True,
            env={**os.environ, "COSIGN_PASSWORD": "test-pass"},
        )
        trust = work / "trust"
        trust.mkdir()
        shutil.copy(other / "cosign.pub", trust / "customer.pub")

        bundle = _build_bundle(work, priv)
        proc = subprocess.run(
            [
                "python3",
                str(REPO_ROOT / "scripts/cortex/verify_bundle.py"),
                str(bundle),
                "--trust-dir",
                str(trust),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1

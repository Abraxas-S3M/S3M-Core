"""Cortex model admission gate and engines.yaml registry alignment tests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
import yaml

from src.cortex.envelope import HmacAdmissionSigner
from src.cortex.model_admission import (
    ModelAdmissionGate,
    is_engine_routable,
    quad_engine_bindings,
    registry_matches_engines_yaml,
    registry_model_files_match,
)
from src.quad_engine.model_registry import ModelRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINES_PATH = str(REPO_ROOT / "configs" / "engines.yaml")
MANIFEST_DIR = str(REPO_ROOT / "configs" / "model_manifests")
ADMISSION_KEY = b"s3m-admission-unit-test-key"


@pytest.fixture()
def signer() -> HmacAdmissionSigner:
    return HmacAdmissionSigner(signing_key=ADMISSION_KEY, key_id="test-authority")


def _sign_admission(signer: HmacAdmissionSigner, fields: dict) -> dict:
    signed = dict(fields)
    signed["signature"] = signer.sign_fields(signed)
    return signed


def _write_lab_engine(
    tmp_path: Path,
    engine_id: str,
    admission: dict,
    *,
    status: str | None = None,
) -> tuple[str, str]:
    engines_doc = yaml.safe_load(Path(ENGINES_PATH).read_text(encoding="utf-8"))
    engines = dict(engines_doc.get("engines") or {})
    base = dict(engines.get("extractor") or {})
    base["admission"] = admission
    base["manifest_id"] = "test_manifest"
    if status:
        base["status"] = status
    engines[engine_id] = base
    engines_doc["engines"] = engines
    engines_doc.setdefault("quad_engine_map", {})["tactical_engine"] = engine_id
    engines_file = tmp_path / "engines.yaml"
    engines_file.write_text(yaml.safe_dump(engines_doc, sort_keys=False), encoding="utf-8")

    manifest_file = tmp_path / "test_manifest.yaml"
    manifest_file.write_text(
        yaml.safe_dump({"model_id": "test_manifest", "admission": admission}, sort_keys=False),
        encoding="utf-8",
    )
    return str(engines_file), str(tmp_path)


def test_registry_and_engines_yaml_agree() -> None:
    registry = ModelRegistry(models_dir="/nonexistent/models")
    assert registry_matches_engines_yaml(registry.engine_ids(), path=ENGINES_PATH)
    bindings = quad_engine_bindings(ENGINES_PATH)
    files = {eid: (registry.get(eid).model_file if registry.get(eid) else "") for eid in bindings}
    assert registry_model_files_match(files, path=ENGINES_PATH)


def test_retired_engine_is_not_routable() -> None:
    from src.cortex.model_admission import is_engine_retired

    assert not is_engine_routable("grok1", ENGINES_PATH)
    assert is_engine_retired("grok1", ENGINES_PATH) is True


def test_pickle_format_model_is_refused(tmp_path: Path, signer: HmacAdmissionSigner) -> None:
    admission = _sign_admission(
        signer,
        {
            "format": "pickle",
            "sha256_verified": True,
            "pinned_sha256": "a" * 64,
            "scanner_passed": True,
            "evals_passed": True,
        },
    )
    engines_path, manifest_dir = _write_lab_engine(tmp_path, "pickle_engine", admission)
    gate = ModelAdmissionGate(engines_path=engines_path, manifest_dir=manifest_dir, signer=signer)
    decision = gate.evaluate("pickle_engine", production=True)
    assert decision.allowed is False
    assert any("pickle" in reason or "forbidden" in reason for reason in decision.reasons)


def test_hash_mismatch_is_refused(tmp_path: Path, signer: HmacAdmissionSigner) -> None:
    model_bytes = b"gguf-stub-weights"
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(model_bytes)
    pinned = hashlib.sha256(b"expected-bytes").hexdigest()
    admission = _sign_admission(
        signer,
        {
            "format": "gguf",
            "sha256_verified": True,
            "pinned_sha256": pinned,
            "scanner_passed": True,
            "evals_passed": True,
        },
    )
    engines_path, manifest_dir = _write_lab_engine(tmp_path, "hash_engine", admission)
    gate = ModelAdmissionGate(engines_path=engines_path, manifest_dir=manifest_dir, signer=signer)
    decision = gate.evaluate("hash_engine", model_path=str(model_path), production=True)
    assert decision.allowed is False
    assert "sha256_mismatch" in decision.reasons


def test_unsigned_manifest_refused_in_production_allowed_in_lab_with_warning(
    tmp_path: Path,
    signer: HmacAdmissionSigner,
) -> None:
    admission = {
        "format": "gguf",
        "sha256_verified": True,
        "pinned_sha256": "",
        "scanner_passed": True,
        "evals_passed": True,
    }
    engines_path, manifest_dir = _write_lab_engine(tmp_path, "unsigned_engine", admission)
    gate = ModelAdmissionGate(engines_path=engines_path, manifest_dir=manifest_dir, signer=signer)

    prod = gate.evaluate("unsigned_engine", production=True)
    assert prod.allowed is False
    assert "unsigned_manifest" in prod.reasons

    lab = gate.evaluate("unsigned_engine", production=False)
    assert lab.allowed is True
    assert any("unsigned_manifest" in w for w in lab.warnings)


if __name__ == "__main__":
    os.environ.setdefault("S3M_DEPLOY_MODE", "production")
    raise SystemExit(pytest.main([__file__, "-v"]))

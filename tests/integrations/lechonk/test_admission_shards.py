"""Admission gate integration with multi-shard inventories."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.cortex.model_admission import ModelAdmissionGate

REPO = Path(__file__).resolve().parents[3]
ENGINES = str(REPO / "configs" / "engines.yaml")
MANIFESTS = str(REPO / "configs" / "model_manifests")


def test_lechonk_engine_not_routable_while_quarantined() -> None:
    gate = ModelAdmissionGate(engines_path=ENGINES, manifest_dir=MANIFESTS)
    decision = gate.evaluate("mistral_large_4", production=True)
    assert decision.allowed is False
    assert "quarantine" in ";".join(decision.reasons)


def test_shard_inventory_passes_with_lab_fixture(tmp_path: Path) -> None:
    gate = ModelAdmissionGate(engines_path=ENGINES, manifest_dir=MANIFESTS)
    (tmp_path / "config.json").write_bytes(b"")
    (tmp_path / "tokenizer.model").write_bytes(b"")
    shard = gate.evaluate_shard_inventory("mistral_large_4", str(tmp_path), variant_tag="fp8_gpu")
    assert shard.admitted is True


def test_admitted_with_shards_still_denied_while_quarantined(tmp_path: Path) -> None:
    gate = ModelAdmissionGate(engines_path=ENGINES, manifest_dir=MANIFESTS)
    (tmp_path / "config.json").write_bytes(b"")
    (tmp_path / "tokenizer.model").write_bytes(b"")
    decision, shard = gate.admitted_with_shards(
        "mistral_large_4",
        str(tmp_path),
        variant_tag="fp8_gpu",
        production=True,
    )
    assert shard.admitted is True
    assert decision.allowed is False

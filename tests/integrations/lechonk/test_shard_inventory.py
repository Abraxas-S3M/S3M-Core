"""Multi-shard inventory verification tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.integrations.lechonk.shard_inventory import (
    ShardInventoryManifest,
    ShardRecord,
    load_inventory_json,
    verify_shard_inventory,
)

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "configs" / "model_manifests" / "inventories" / "mistral_large_4_fp8_lab_fixture.json"


def test_lab_fixture_manifest_digest_matches() -> None:
    inv = load_inventory_json(FIXTURE)
    assert inv.computed_manifest_sha256() == inv.manifest_sha256


def test_verify_accepts_matching_shards(tmp_path: Path) -> None:
    inv = load_inventory_json(FIXTURE)
    (tmp_path / "config.json").write_bytes(b"")
    (tmp_path / "tokenizer.model").write_bytes(b"")
    result = verify_shard_inventory(inv, tmp_path)
    assert result.admitted is True
    assert result.verified_count == 2


def test_verify_rejects_missing_shard(tmp_path: Path) -> None:
    inv = load_inventory_json(FIXTURE)
    (tmp_path / "config.json").write_bytes(b"")
    result = verify_shard_inventory(inv, tmp_path)
    assert result.admitted is False
    assert any("missing" in r for r in result.reasons)


def test_verify_rejects_unexpected_file(tmp_path: Path) -> None:
    inv = load_inventory_json(FIXTURE)
    (tmp_path / "config.json").write_bytes(b"")
    (tmp_path / "tokenizer.model").write_bytes(b"")
    (tmp_path / "evil.bin").write_bytes(b"x")
    result = verify_shard_inventory(inv, tmp_path)
    assert result.admitted is False


def test_verify_rejects_hash_mismatch(tmp_path: Path) -> None:
    inv = ShardInventoryManifest(
        variant_tag="fp8_gpu",
        model_id="mistral_large_4",
        source_revision="rev",
        shards=(
            ShardRecord(
                relative_path="weights.safetensors",
                size_bytes=3,
                sha256="a" * 64,
            ),
        ),
    )
    (tmp_path / "weights.safetensors").write_bytes(b"abc")
    result = verify_shard_inventory(inv, tmp_path)
    assert result.admitted is False
    assert any("sha256" in r for r in result.reasons)

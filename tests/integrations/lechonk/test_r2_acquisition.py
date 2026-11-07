"""R2 acquisition verification workflow (metadata-only, no downloads)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.integrations.lechonk.r2_acquisition import (
    InMemoryObjectLister,
    R2ObjectHead,
    etag_is_multipart,
    inventory_manifest_integrity,
    verify_variant_acquisition,
)
from src.integrations.lechonk.shard_inventory import load_inventory_json

REPO = Path(__file__).resolve().parents[3]
INV = REPO / "configs" / "model_manifests" / "inventories"


def test_multipart_etag_not_treated_as_sha256() -> None:
    assert etag_is_multipart('"abcdef0123456789abcdef0123456789-9"')


def test_fp8_object_count_and_metadata_sha256() -> None:
    inv = load_inventory_json(INV / "mistral_large_4_fp8_lab_fixture.json")
    records = [
        R2ObjectHead(
            key="mistral-le-chonk/01-quarantine-original/fp8/config.json",
            size_bytes=0,
            etag='"deadbeef"',
            metadata_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            revision="af2627869af601441d6cdf75a1272469ddc3d059",
        ),
        R2ObjectHead(
            key="mistral-le-chonk/01-quarantine-original/fp8/tokenizer.model",
            size_bytes=0,
            etag='"cafebabe"',
            metadata_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            revision="af2627869af601441d6cdf75a1272469ddc3d059",
        ),
    ]
    variant = {
        "tag": "fp8_gpu",
        "r2_prefix": "mistral-le-chonk/01-quarantine-original/fp8/",
        "source_revision": "af2627869af601441d6cdf75a1272469ddc3d059",
        "expected_inventory_objects": 2,
    }
    report = verify_variant_acquisition(variant, InMemoryObjectLister(records), inv)
    assert report.admitted is True
    assert report.listed_object_count == 2


def test_count_mismatch_rejects() -> None:
    variant = {
        "tag": "fp8_gpu",
        "r2_prefix": "mistral-le-chonk/01-quarantine-original/fp8/",
        "source_revision": "af2627869af601441d6cdf75a1272469ddc3d059",
        "expected_inventory_objects": 69,
    }
    report = verify_variant_acquisition(variant, InMemoryObjectLister([]), None)
    assert report.admitted is False
    assert any("object_count_mismatch" in r for r in report.reasons)


def test_production_manifest_expectations_documented() -> None:
    """Lab fixture has 2 shards; production gate A expects 69 FP8 / 44 NVFP4 objects."""
    fp8 = load_inventory_json(INV / "mistral_large_4_fp8_lab_fixture.json")
    nvfp4 = load_inventory_json(INV / "mistral_large_4_nvfp4_lab_fixture.json")
    assert inventory_manifest_integrity(fp8) == []
    assert inventory_manifest_integrity(nvfp4) == []

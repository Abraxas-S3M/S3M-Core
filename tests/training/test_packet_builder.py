"""Tests for scenario packet construction and validation flows."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.training.packet_builder import PacketBuilder


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def test_build_from_jsonl_splits_normalizes_and_autonumbers(tmp_path: Path) -> None:
    input_path = tmp_path / "raw.jsonl"
    _write_jsonl(
        input_path,
        [
            {"prompt": "Summarize convoy status", "completion": "Convoy is stable."},
            {"instruction": "لخص موقف القوة", "output": "الوضع مستقر"},
            {"input": "Report fuel status", "response": "Fuel at 70%."},
            {"prompt": "لخص SITREP now", "completion": "Mixed language response."},
            {"instruction": "Provide weather update", "output": "Winds are moderate."},
        ],
    )

    output_dir = tmp_path / "scenarios"
    # Tactical auto-numbering must continue from pre-existing packet IDs.
    (output_dir / "scenario-00003").mkdir(parents=True)

    builder = PacketBuilder(source="manual")
    packs = builder.build_from_jsonl(
        input_file=input_path,
        track="saudi_mod",
        data_class="command",
        output_dir=output_dir,
        examples_per_pack=2,
    )

    assert [pack.name for pack in packs] == ["scenario-00004", "scenario-00005", "scenario-00006"]
    assert all(builder.validate_pack(pack) for pack in packs)

    first_manifest = _read_json(packs[0] / "manifest.json")
    second_manifest = _read_json(packs[1] / "manifest.json")
    third_manifest = _read_json(packs[2] / "manifest.json")

    assert first_manifest["example_count"] == 2
    assert first_manifest["language"] == "bilingual"
    assert second_manifest["language"] == "bilingual"
    assert third_manifest["language"] == "en"

    assert len((packs[0] / "prompts.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert len((packs[0] / "labels.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_build_from_pairs_marks_arabic_language_and_structure(tmp_path: Path) -> None:
    builder = PacketBuilder(source="synthetic")
    packs = builder.build_from_pairs(
        pairs=[
            {"prompt": "تلخيص موجز عملياتي", "completion": "الاستعداد مرتفع."},
            {"prompt": "اعرض موقف القطاع", "completion": "القطاع آمن."},
        ],
        track="shared",
        data_class="risk_readiness",
        output_dir=tmp_path,
        scenario_id_start=7,
    )

    assert [pack.name for pack in packs] == ["scenario-00007"]
    pack = packs[0]
    manifest = _read_json(pack / "manifest.json")
    assert manifest["scenario_id"] == "scenario-00007"
    assert manifest["track"] == "shared"
    assert manifest["data_class"] == "risk_readiness"
    assert manifest["language"] == "ar"
    assert manifest["source"] == "synthetic"
    assert set(manifest["checksums"]) == {"prompts.jsonl", "labels.jsonl"}
    assert builder.validate_pack(pack)


def test_validate_pack_rejects_checksum_tamper(tmp_path: Path) -> None:
    builder = PacketBuilder()
    pack = builder.build_from_pairs(
        pairs=[{"prompt": "Mission prompt", "completion": "Mission completion"}],
        track="nato",
        data_class="cop_intel",
        output_dir=tmp_path,
        scenario_id_start=1,
    )[0]

    with (pack / "prompts.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"prompt": "Injected", "weight": 1.0}))
        handle.write("\n")

    assert builder.validate_pack(pack) is False


def test_upload_packs_emits_object_storage_key_prefixes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    builder = PacketBuilder()
    pack = builder.build_from_pairs(
        pairs=[{"prompt": "Intel summary", "completion": "Intel output"}],
        track="ukraine_mod",
        data_class="cop_intel",
        output_dir=tmp_path,
        scenario_id_start=15,
    )[0]

    uploaded_keys: list[str] = []

    def _fake_upload(local_path: Path, remote_key: str) -> None:
        uploaded_keys.append(remote_key)

    monkeypatch.setattr(builder, "_upload_file", _fake_upload)
    prefixes = builder.upload_packs(pack_dirs=[pack], track="ukraine_mod")

    assert prefixes == ["datasets/ukraine_mod/scenarios/scenario-00015"]
    assert uploaded_keys == [
        "datasets/ukraine_mod/scenarios/scenario-00015/manifest.json",
        "datasets/ukraine_mod/scenarios/scenario-00015/prompts.jsonl",
        "datasets/ukraine_mod/scenarios/scenario-00015/labels.jsonl",
    ]


def test_cli_build_and_validate_flow(tmp_path: Path) -> None:
    input_path = tmp_path / "cli_raw.jsonl"
    _write_jsonl(
        input_path,
        [
            {"prompt": "Prepare SITREP", "completion": "SITREP prepared."},
            {"instruction": "Provide logistics status", "output": "Logistics stable."},
        ],
    )
    output_dir = tmp_path / "cli_scenarios"
    (output_dir / "scenario-00001").mkdir(parents=True)

    build_cmd = [
        sys.executable,
        "scripts/training/build_packet.py",
        "--input",
        str(input_path),
        "--track",
        "nato",
        "--data-class",
        "command",
        "--output",
        str(output_dir),
        "--examples-per-pack",
        "1",
    ]
    build_result = subprocess.run(build_cmd, text=True, capture_output=True, check=False, cwd=Path.cwd())
    assert build_result.returncode == 0, build_result.stderr
    assert (output_dir / "scenario-00002").exists()
    assert (output_dir / "scenario-00003").exists()

    validate_cmd = [
        sys.executable,
        "scripts/training/build_packet.py",
        "--validate",
        str(output_dir / "scenario-00002"),
    ]
    validate_result = subprocess.run(validate_cmd, text=True, capture_output=True, check=False, cwd=Path.cwd())
    assert validate_result.returncode == 0
    assert "VALID" in validate_result.stdout


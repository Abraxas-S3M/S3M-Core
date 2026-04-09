from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.storage.precision_manager import PrecisionManager


class _FakeB2:
    def __init__(self) -> None:
        self.synced_down: list[tuple[str, str]] = []
        self.synced_up: list[tuple[str, str]] = []
        self.uploaded: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.downloaded: list[tuple[str, str]] = []
        self.keys_by_prefix: dict[str, list[str]] = {}
        self.sizes: dict[str, int] = {}

    def sync_down(self, remote_prefix: str, local_dir: Path, exclude_patterns: list[str] | None = None) -> dict[str, int]:
        _ = exclude_patterns
        self.synced_down.append((remote_prefix, str(local_dir)))
        return {"downloaded": 1, "uploaded": 0, "skipped": 0, "bytes_transferred": 10}

    def sync_up(self, local_dir: Path, remote_prefix: str) -> dict[str, int]:
        self.synced_up.append((str(local_dir), remote_prefix))
        return {"downloaded": 0, "uploaded": 1, "skipped": 0, "bytes_transferred": 10}

    def upload_file(self, local_path: Path, remote_key: str) -> dict[str, Any]:
        self.uploaded.append((str(local_path), remote_key))
        return {"remote_key": remote_key, "size_bytes": 11}

    def list_keys(self, prefix: str) -> list[str]:
        return list(self.keys_by_prefix.get(prefix, []))

    def delete_file(self, remote_key: str) -> bool:
        self.deleted.append(remote_key)
        return True

    def download_file(self, remote_key: str, local_path: Path) -> dict[str, Any]:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_text(f"payload-{remote_key}", encoding="utf-8")
        self.downloaded.append((remote_key, str(local_path)))
        return {"remote_key": remote_key, "size_bytes": Path(local_path).stat().st_size}

    def get_file_size(self, remote_key: str) -> int:
        return int(self.sizes.get(remote_key, 0))


def test_pull_fp16_for_training_blocks_grok(tmp_path: Path) -> None:
    manager = PrecisionManager(_FakeB2())
    with pytest.raises(ValueError, match="blocked"):
        manager.pull_fp16_for_training("grok-300b", tmp_path / "models")


def test_pull_q4_for_serving_uses_q4_prefix(tmp_path: Path) -> None:
    fake = _FakeB2()
    manager = PrecisionManager(fake)
    destination = tmp_path / "q4"
    returned = manager.pull_q4_for_serving("phi3-medium", destination)

    assert returned == destination
    assert fake.synced_down[0][0] == "models/q4-gguf/phi3-medium/"


def test_push_q4_serving_replaces_existing_files(tmp_path: Path) -> None:
    fake = _FakeB2()
    fake.keys_by_prefix["models/q4-gguf/phi3-medium/"] = [
        "models/q4-gguf/phi3-medium/old-a.gguf",
        "models/q4-gguf/phi3-medium/old-b.gguf",
    ]
    manager = PrecisionManager(fake)
    gguf = tmp_path / "new.gguf"
    gguf.write_bytes(b"new")

    manager.push_q4_serving("phi3-medium", gguf)

    assert fake.deleted == [
        "models/q4-gguf/phi3-medium/old-a.gguf",
        "models/q4-gguf/phi3-medium/old-b.gguf",
    ]
    assert fake.uploaded[-1][1] == "models/q4-gguf/phi3-medium/new.gguf"


def test_promote_merged_to_base_downloads_and_uploads_key_map() -> None:
    fake = _FakeB2()
    merged_prefix = "models/fp16-merged/phi3-medium/nato/"
    fake.keys_by_prefix[merged_prefix] = [
        "models/fp16-merged/phi3-medium/nato/config.json",
        "models/fp16-merged/phi3-medium/nato/model-00001.safetensors",
    ]
    manager = PrecisionManager(fake)

    stats = manager.promote_merged_to_base("phi3-medium", "nato")

    assert stats["downloaded"] == 2
    assert stats["uploaded"] == 2
    uploaded_targets = [remote_key for _, remote_key in fake.uploaded]
    assert "models/fp16/phi3-medium/config.json" in uploaded_targets
    assert "models/fp16/phi3-medium/model-00001.safetensors" in uploaded_targets


def test_get_model_inventory_summarizes_tiers() -> None:
    fake = _FakeB2()
    fake.keys_by_prefix["models/fp16/phi3-medium/"] = [
        "models/fp16/phi3-medium/config.json",
        "models/fp16/phi3-medium/model.safetensors",
    ]
    fake.keys_by_prefix["models/q4-gguf/phi3-medium/"] = ["models/q4-gguf/phi3-medium/model.gguf"]
    fake.sizes["models/fp16/phi3-medium/config.json"] = 100
    fake.sizes["models/fp16/phi3-medium/model.safetensors"] = 900
    fake.sizes["models/q4-gguf/phi3-medium/model.gguf"] = 500
    manager = PrecisionManager(fake)

    inventory = manager.get_model_inventory()

    assert inventory["phi3-medium"]["fp16_files"] == 2
    assert inventory["phi3-medium"]["q4_files"] == 1
    assert inventory["phi3-medium"]["has_fp16"] is True
    assert inventory["phi3-medium"]["has_q4"] is True

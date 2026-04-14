"""Dual-precision model lifecycle manager for S3M storage operations.

Military/tactical context:
This manager enforces strict separation between training-grade FP16 artifacts
and deployable Q4 serving artifacts so promotion operations do not degrade the
model source-of-truth during mission preparation cycles.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from src.storage.object_storage import ObjectStorageConnector
from src.storage.vault_paths import VaultPaths


class PrecisionManager:
    """Manages the dual-precision model lifecycle.

    Military/tactical context:
    This manager ensures that the FP16 source of truth is never
    accidentally degraded, and that Q4 serving copies are always
    derived from the latest promoted FP16 model.
    """

    def __init__(self, object_storage: ObjectStorageConnector) -> None:
        self.object_storage = object_storage

    def pull_fp16_for_training(self, engine_id: str, local_dir: Path) -> Path:
        """Pull FP16 base model for GPU training while blocking Grok oracle pulls."""
        if VaultPaths.is_blocked_engine(engine_id):
            raise ValueError(
                f"Engine '{engine_id}' is blocked from pull. "
                "Grok-1 (300 GB) stays in Cloudflare R2 as validation oracle."
            )
        remote = VaultPaths.fp16_base(engine_id)
        self.object_storage.sync_down(remote, local_dir)
        return Path(local_dir)

    def pull_q4_for_serving(self, engine_id: str, local_dir: Path) -> Path:
        """Pull Q4 GGUF model for CPU inference serving while blocking Grok pulls."""
        if VaultPaths.is_blocked_engine(engine_id):
            raise ValueError(f"Engine '{engine_id}' is blocked from pull.")
        remote = VaultPaths.q4_serving(engine_id)
        self.object_storage.sync_down(remote, local_dir)
        return Path(local_dir)

    def push_fp16_adapter(self, engine_id: str, track: str, adapter_dir: Path) -> dict[str, int]:
        """Push FP16 LoRA adapter from RunPod back to Cloudflare R2."""
        remote = VaultPaths.fp16_adapter(engine_id, track)
        return self.object_storage.sync_up(adapter_dir, remote)

    def push_fp16_merged(self, engine_id: str, track: str, merged_dir: Path) -> dict[str, int]:
        """Push merged FP16 model from Hetzner to Cloudflare R2."""
        remote = VaultPaths.fp16_merged(engine_id, track)
        return self.object_storage.sync_up(merged_dir, remote)

    def push_q4_serving(self, engine_id: str, gguf_path: Path) -> dict[str, Any]:
        """Push the latest Q4 GGUF to serving path, replacing prior serving files."""
        remote_prefix = VaultPaths.q4_serving(engine_id)
        for key in self.object_storage.list_keys(remote_prefix):
            self.object_storage.delete_file(key)
        remote = f"{remote_prefix}{Path(gguf_path).name}"
        return self.object_storage.upload_file(gguf_path, remote)

    def promote_merged_to_base(self, engine_id: str, track: str) -> dict[str, int]:
        """Promote merged FP16 into canonical FP16 base after evaluation approval.

        Tactical context:
        Promotion is the model "level-up" moment and must preserve every model
        file while replacing prior base artifacts with approved merged state.
        """

        merged_prefix = VaultPaths.fp16_merged(engine_id, track)
        base_prefix = VaultPaths.fp16_base(engine_id)
        keys = self.object_storage.list_keys(merged_prefix)
        if not keys:
            raise ValueError(f"No merged FP16 artifacts found for {engine_id}/{track}")

        promoted = 0
        bytes_transferred = 0
        with tempfile.TemporaryDirectory(prefix="s3m-promote-") as tmp_dir:
            staging_root = Path(tmp_dir)
            for key in keys:
                relative = key[len(merged_prefix) :] if key.startswith(merged_prefix) else key
                if not relative:
                    continue
                local_copy = staging_root / relative
                self.object_storage.download_file(key, local_copy)
                target_key = f"{base_prefix}{relative}"
                upload_result = self.object_storage.upload_file(local_copy, target_key)
                promoted += 1
                bytes_transferred += int(upload_result.get("size_bytes", 0))
                local_copy.unlink(missing_ok=True)

        return {
            "downloaded": promoted,
            "uploaded": promoted,
            "skipped": 0,
            "bytes_transferred": bytes_transferred * 2,
        }

    def get_model_inventory(self) -> dict[str, dict[str, Any]]:
        """Return model inventory snapshot across FP16 and Q4 precision tiers."""
        inventory: dict[str, dict[str, Any]] = {}
        for engine in ["phi3-medium", "mistral-7b", "allam-7b", "grok-300b"]:
            fp16_keys = self.object_storage.list_keys(VaultPaths.fp16_base(engine))
            q4_keys = self.object_storage.list_keys(VaultPaths.q4_serving(engine))
            inventory[engine] = {
                "fp16_files": len(fp16_keys),
                "fp16_size_gb": sum(self.object_storage.get_file_size(key) for key in fp16_keys) / (1024**3),
                "q4_files": len(q4_keys),
                "q4_size_gb": sum(self.object_storage.get_file_size(key) for key in q4_keys) / (1024**3),
                "has_fp16": len(fp16_keys) > 0,
                "has_q4": len(q4_keys) > 0,
            }
        return inventory

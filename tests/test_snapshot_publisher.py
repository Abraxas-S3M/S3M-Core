from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.api.gui_bridge.snapshot_publisher import SnapshotPublisher


class _FakeB2Connector:
    def __init__(self) -> None:
        self.uploaded: list[dict] = []

    def upload_json(self, object_key: str, payload: dict) -> dict:
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        etag = hashlib.md5(content).hexdigest()
        row = {
            "object_key": object_key,
            "payload": payload,
            "etag": etag,
            "uploaded_at": "2026-04-09T00:00:00+00:00",
            "size_bytes": len(content),
        }
        self.uploaded.append(row)
        return row


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_training_status_snapshot_schema(tmp_path) -> None:
    metrics_dir = tmp_path / "state" / "training" / "cloud_cpu" / "metrics"
    _write_jsonl(
        metrics_dir / "saudi_mod.jsonl",
        [
            {
                "cycle": 1200,
                "loss": 0.58,
                "samples_processed": 60000,
                "timestamp": "2026-04-09T00:00:00+00:00",
                "last_eval": {"arabic_fidelity": 0.79, "overall": 0.74},
                "active_adapters": {"phi3-medium": "adapter-v2-step1200"},
            },
            {
                "cycle": 1500,
                "loss": 0.42,
                "samples_processed": 75000,
                "timestamp": "2026-04-09T02:00:00+00:00",
                "last_eval": {"arabic_fidelity": 0.82, "overall": 0.78},
                "active_adapters": {
                    "phi3-medium": "adapter-v3-step1500",
                    "mistral-7b": "adapter-v2-step800",
                },
                "gpu_session": {"engine": "phi3-medium", "duration": "2h 15m", "loss": 0.38},
                "grok_verdict": {"status": "approved", "timestamp": "2026-04-09T03:00:00+00:00"},
            },
        ],
    )

    promoted_manifest = (
        tmp_path
        / "state"
        / "training"
        / "cloud_cpu"
        / "tracks"
        / "saudi_mod"
        / "checkpoints"
        / "promoted"
        / "ckpt-1500"
        / "manifest.json"
    )
    promoted_manifest.parent.mkdir(parents=True, exist_ok=True)
    promoted_manifest.write_text(
        json.dumps({"step": 1200, "timestamp": "2026-04-08T20:00:00+00:00"}),
        encoding="utf-8",
    )

    publisher = SnapshotPublisher(
        b2_connector=_FakeB2Connector(),
        metrics_dir=metrics_dir,
        training_state_root=tmp_path / "state" / "training" / "cloud_cpu",
    )
    snapshot = publisher.generate_workspace_snapshot("training_status")

    assert snapshot["type"] == "backend.snapshot"
    assert "timestamp" in snapshot
    payload = snapshot["payload"]
    assert "generated_at" in payload
    assert "tracks" in payload
    assert "gpu_sessions" in payload
    assert "grok_verdicts" in payload

    saudi = payload["tracks"]["saudi_mod"]
    assert saudi["current_step"] == 1500
    assert saudi["last_loss"] == 0.42
    assert saudi["samples_processed"] == 75000
    assert saudi["last_eval"]["arabic_fidelity"] == 0.82
    assert saudi["last_promotion"]["step"] == 1200
    assert saudi["active_adapters"]["phi3-medium"] == "adapter-v3-step1500"
    assert saudi["active_adapters"]["mistral-7b"] == "adapter-v2-step800"

    assert payload["gpu_sessions"]["last_session"]["engine"] == "phi3-medium"
    assert payload["gpu_sessions"]["last_session"]["duration"] == "2h 15m"
    assert payload["gpu_sessions"]["last_session"]["loss"] == 0.38


def test_publish_to_b2_writes_workspace_files_and_manifest(tmp_path) -> None:
    connector = _FakeB2Connector()
    publisher = SnapshotPublisher(
        b2_connector=connector,
        metrics_dir=tmp_path / "state" / "training" / "cloud_cpu" / "metrics",
        training_state_root=tmp_path / "state" / "training" / "cloud_cpu",
    )

    snapshots = {
        "command": {"type": "backend.snapshot", "payload": {"ok": True}, "timestamp": "2026-04-09T00:00:00+00:00"},
        "system_status": {"type": "backend.snapshot", "payload": {"status": "operational"}, "timestamp": "2026-04-09T00:00:00+00:00"},
        "training_status": {"type": "backend.snapshot", "payload": {"tracks": {}}, "timestamp": "2026-04-09T00:00:00+00:00"},
    }
    manifest = publisher.publish_to_b2(snapshots)

    uploaded_keys = {row["object_key"] for row in connector.uploaded}
    assert "gui-snapshots/command.json" in uploaded_keys
    assert "gui-snapshots/system-status.json" in uploaded_keys
    assert "gui-snapshots/training-status.json" in uploaded_keys
    assert "gui-snapshots/manifest.json" in uploaded_keys

    assert manifest["type"] == "backend.snapshot.manifest"
    assert "generated_at" in manifest
    assert "command" in manifest["snapshots"]
    assert "system_status" in manifest["snapshots"]
    assert "training_status" in manifest["snapshots"]
    assert "etag" in manifest["snapshots"]["command"]


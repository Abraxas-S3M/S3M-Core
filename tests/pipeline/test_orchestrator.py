"""Unit tests for S3M pipeline orchestrator integration layer."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from src.pipeline.orchestrator import Orchestrator
from src.training.packet_builder import PacketBuilder


def _seed_valid_packet(base_dir: Path, track: str = "saudi_mod", scenario_id: str = "scenario-00001") -> Path:
    packet_dir = base_dir / scenario_id
    packet_dir.mkdir(parents=True, exist_ok=True)

    prompts_path = packet_dir / "prompts.jsonl"
    labels_path = packet_dir / "labels.jsonl"
    manifest_path = packet_dir / "manifest.json"

    prompts_payload = {"prompt": "Generate tactical SITREP", "weight": 1.0}
    labels_payload = {"completion": "Sector secure, ISR active."}

    prompts_path.write_text(json.dumps(prompts_payload) + "\n", encoding="utf-8")
    labels_path.write_text(json.dumps(labels_payload) + "\n", encoding="utf-8")

    # Tactical note: use canonical packet checksums to simulate trusted ingest.
    builder = PacketBuilder()
    manifest = {
        "scenario_id": scenario_id,
        "track": track,
        "data_class": "command",
        "example_count": 1,
        "language": "en",
        "source": "manual",
        "checksums": {
            "prompts.jsonl": builder._sha256_file(prompts_path),  # noqa: SLF001 - test-only checksum generation
            "labels.jsonl": builder._sha256_file(labels_path),  # noqa: SLF001 - test-only checksum generation
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return packet_dir


def test_orchestrator_watcher_queues_and_monitor_executes(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "opt" / "s3m"
    inbox_dir = root / "state" / "training" / "cloud_cpu" / "inbox"
    packets_dir = root / "packets"
    staging_dir = root / "state" / "training" / "staging"
    log_dir = root / "logs"

    monkeypatch.setenv("S3M_ROOT", str(root))
    monkeypatch.setenv("INBOX_DIR", str(inbox_dir))
    monkeypatch.setenv("PACKETS_DIR", str(packets_dir))
    monkeypatch.setenv("STAGING_DIR", str(staging_dir))
    monkeypatch.setenv("LOG_DIR", str(log_dir))
    monkeypatch.setenv("S3M_TRAINING_TRACKS", "saudi_mod")
    monkeypatch.setenv("POLL_INTERVAL", "1")
    monkeypatch.setenv("R2_ENDPOINT", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY", "access")
    monkeypatch.setenv("R2_SECRET_KEY", "secret")
    monkeypatch.setenv("R2_BUCKET", "s3m-vault")

    orchestrator = Orchestrator(poll_interval=1)

    # Replace trainer-service creation with deterministic fake for isolated unit test.
    class _FakeTrainerService:
        def __init__(self) -> None:
            self.cycles = 0
            self.stopped = False

        def run_cycle_once(self) -> None:
            self.cycles += 1

        def stop(self) -> None:
            self.stopped = True

    fake_service = _FakeTrainerService()
    orchestrator.trainer_registry._services["saudi_mod"] = fake_service  # noqa: SLF001 - controlled test seam

    _seed_valid_packet(inbox_dir, track="saudi_mod")
    orchestrator._watcher_once()  # noqa: SLF001 - exercising one watcher cycle
    completed = orchestrator.train_runner.monitor_once()

    assert completed is not None
    assert completed.status == "success"
    assert fake_service.cycles == 1

    routed_dir = orchestrator.state_paths.scenario_dir("saudi_mod") / "scenario-00001"
    assert routed_dir.exists()

    snapshot_path = staging_dir / "runpod_jobs.json"
    assert snapshot_path.exists()
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert int(snapshot_payload["active_jobs"]) == 0

    status = orchestrator.status()
    assert status["components"]["packet_builder"]["ok"] is True
    assert status["components"]["train_runner"]["ok"] is True
    assert status["components"]["trainer_registry"]["ok"] is True


def test_orchestrator_run_and_shutdown_threads(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "opt" / "s3m"
    monkeypatch.setenv("S3M_ROOT", str(root))
    monkeypatch.setenv("INBOX_DIR", str(root / "state" / "training" / "cloud_cpu" / "inbox"))
    monkeypatch.setenv("PACKETS_DIR", str(root / "packets"))
    monkeypatch.setenv("STAGING_DIR", str(root / "state" / "training" / "staging"))
    monkeypatch.setenv("LOG_DIR", str(root / "logs"))
    monkeypatch.setenv("S3M_TRAINING_TRACKS", "saudi_mod")
    monkeypatch.setenv("R2_ENDPOINT", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY", "access")
    monkeypatch.setenv("R2_SECRET_KEY", "secret")

    orchestrator = Orchestrator(poll_interval=1)

    monitor_calls = {"count": 0}
    lock = threading.Lock()

    def _fake_monitor_once():
        with lock:
            monitor_calls["count"] += 1
        return None

    orchestrator.train_runner.monitor_once = _fake_monitor_once  # type: ignore[assignment]

    orchestrator.run()
    assert orchestrator.status()["running"] is True

    # Allow a short loop cycle.
    import time

    time.sleep(1.2)
    orchestrator.shutdown()

    final_status = orchestrator.status()
    assert final_status["running"] is False
    assert final_status["threads"]["watcher_alive"] is False
    assert final_status["threads"]["monitor_alive"] is False
    with lock:
        assert monitor_calls["count"] >= 1

"""End-to-end packet watcher pipeline tests with mocked integrations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.pipeline import packet_watcher as packet_watcher_module


class FakeLabelValidator:
    """Captures scenario validation calls from the watcher gate."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def validate_scenario(self, track: str, scenario: str) -> bool:
        self.calls.append((track, scenario))
        return True


class FakeOrchestrator:
    """Startup stub proving watcher initializes orchestrator on boot."""

    instances: list["FakeOrchestrator"] = []

    def __init__(self, poll_interval: int) -> None:
        self.poll_interval = int(poll_interval)
        self.db_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.db_conn.row_factory = sqlite3.Row
        self.label_validator = FakeLabelValidator()
        self.packet_builder = packet_watcher_module.PacketBuilder()
        self.trainer_registry = None
        FakeOrchestrator.instances.append(self)


class FakeTrainerRegistry:
    """Offline registry with deterministic trainer config routing."""

    _RUNPOD_BY_TRACK = {
        "saudi_mod": "runpod-saudi-mod-causal-lm",
        "ukraine_mod": "runpod-ukraine-mod-causal-lm",
        "nato": "runpod-nato-causal-lm",
        "indopac_mod": "runpod-indopac-mod-causal-lm",
    }

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path is not None else None

    def get_trainer_config(self, track: str, scenario: str) -> dict[str, Any]:
        return {
            "trainer_type": "causal_lm",
            "base_model": f"models/quantized/{track}-causal-lm",
            "learning_rate": 2e-5,
            "batch_size": 8,
            "max_epochs": 4,
            "warmup_steps": 100,
            "gradient_accumulation": 1,
            "mixed_precision": True,
            "runpod_template": self._RUNPOD_BY_TRACK[track],
            "scenario": scenario,
        }


class FakePacketRouter:
    """Captures route_batch calls and emits deterministic manifests."""

    instances: list["FakePacketRouter"] = []

    def __init__(self, registry: FakeTrainerRegistry, db_conn: Any = None) -> None:
        self._registry = registry
        self._db_conn = db_conn
        self.route_batch_calls: list[dict[str, Any]] = []
        FakePacketRouter.instances.append(self)

    def route_batch(self, packets: list[Path], track: str, scenario: str) -> list[dict[str, Any]]:
        self.route_batch_calls.append(
            {
                "packets": [Path(packet) for packet in packets],
                "track": track,
                "scenario": scenario,
            }
        )
        manifests: list[dict[str, Any]] = []
        for packet in packets:
            manifests.append(
                {
                    "packet": str(packet),
                    "track": track,
                    "scenario": scenario,
                    "trainer_config": self._registry.get_trainer_config(track, scenario),
                    "status": "routed",
                }
            )
        return manifests


class FakeR2Client:
    """Collects processed uploads instead of reaching external storage."""

    instances: list["FakeR2Client"] = []

    def __init__(self) -> None:
        self.uploads: list[tuple[str, str]] = []
        FakeR2Client.instances.append(self)

    def upload(self, local_path: Path, r2_key: str) -> str:
        self.uploads.append((str(local_path), str(r2_key)))
        return f"r2://mock-bucket/{r2_key}"


class FakeVaultCatalog:
    """Captures vault completion marks for processed sources."""

    instances: list["FakeVaultCatalog"] = []

    def __init__(self, r2_client: FakeR2Client, db_conn: Any = None) -> None:
        self.r2_client = r2_client
        self.db_conn = db_conn
        self.completed_keys: list[str] = []
        FakeVaultCatalog.instances.append(self)

    def mark_complete(self, r2_key: str) -> None:
        self.completed_keys.append(str(r2_key))


class FakeTrainRunner:
    """RunPod substitute that records job submissions."""

    instances: list["FakeTrainRunner"] = []

    def __init__(self, db_conn: Any = None, r2_client: Any = None) -> None:
        self.db_conn = db_conn
        self.r2_client = r2_client
        self.submissions: list[dict[str, Any]] = []
        FakeTrainRunner.instances.append(self)

    def submit_job(self, routing_manifest: dict[str, Any]) -> str:
        self.submissions.append(dict(routing_manifest))
        return f"job-{len(self.submissions):04d}"


def _write_tracks_config(path: Path) -> None:
    payload = {
        "tracks": {
            "saudi_mod": {"default_data_class": "command", "scenarios": {"strategic_command": {"data_class": "command"}}},
            "ukraine_mod": {"default_data_class": "command", "scenarios": {"frontline_recon": {"data_class": "command"}}},
            "nato": {"default_data_class": "command", "scenarios": {"joint_planning": {"data_class": "command"}}},
            "indopac_mod": {"default_data_class": "command", "scenarios": {"maritime_patrol": {"data_class": "command"}}},
        }
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: int) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for idx in range(rows):
            payload = {
                "prompt": f"mission prompt {idx}",
                "completion": f"mission completion {idx}",
            }
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")


@pytest.fixture
def full_pipeline_watcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> packet_watcher_module.PacketWatcher:
    FakeOrchestrator.instances.clear()
    FakePacketRouter.instances.clear()
    FakeR2Client.instances.clear()
    FakeVaultCatalog.instances.clear()
    FakeTrainRunner.instances.clear()

    monkeypatch.setattr(packet_watcher_module, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(packet_watcher_module, "TrainerRegistry", FakeTrainerRegistry)
    monkeypatch.setattr(packet_watcher_module, "PacketRouter", FakePacketRouter)
    monkeypatch.setattr(packet_watcher_module, "R2Client", FakeR2Client)
    monkeypatch.setattr(packet_watcher_module, "VaultCatalog", FakeVaultCatalog)
    monkeypatch.setattr(packet_watcher_module, "TrainRunner", FakeTrainRunner)
    monkeypatch.setattr(packet_watcher_module, "LOG_FILE", tmp_path / "packet_watcher.log")

    inbox_dir = tmp_path / "inbox"
    staging_dir = tmp_path / "staging"
    packet_root = tmp_path / "packets"
    tracks_config = tmp_path / "tracks.yaml"
    _write_tracks_config(tracks_config)

    return packet_watcher_module.PacketWatcher(
        inbox_dir=inbox_dir,
        staging_dir=staging_dir,
        packet_output_root=packet_root,
        tracks_config_path=tracks_config,
        poll_interval_seconds=1,
    )


def test_full_pipeline_processes_all_tracks_and_writes_audit(full_pipeline_watcher: packet_watcher_module.PacketWatcher) -> None:
    watcher = full_pipeline_watcher
    inbox = watcher._inbox_dir
    staging = watcher._staging_dir
    packet_root = watcher._packet_output_root

    tracks = {
        "saudi_mod_strategic_command_v1.jsonl": ("saudi_mod", "strategic_command"),
        "ukraine_mod_frontline_recon_v1.jsonl": ("ukraine_mod", "frontline_recon"),
        "nato_joint_planning_v1.jsonl": ("nato", "joint_planning"),
        "indopac_mod_maritime_patrol_v1.jsonl": ("indopac_mod", "maritime_patrol"),
    }
    for filename in tracks:
        _write_jsonl(inbox / filename, rows=120)

    watcher._run_single_cycle()

    assert len(FakeOrchestrator.instances) == 1
    orchestrator = FakeOrchestrator.instances[0]
    assert isinstance(orchestrator.label_validator, FakeLabelValidator)
    assert sorted(orchestrator.label_validator.calls) == sorted(tracks.values())

    assert len(FakePacketRouter.instances) == 1
    router = FakePacketRouter.instances[0]
    assert len(router.route_batch_calls) == 4
    assert all(len(call["packets"]) == 3 for call in router.route_batch_calls)

    assert len(FakeTrainRunner.instances) == 1
    runpod = FakeTrainRunner.instances[0]
    assert len(runpod.submissions) == 12
    for submission in runpod.submissions:
        assert isinstance(submission.get("trainer_config"), dict)
        assert submission["packet_files"] == [submission["packet"]]
        assert submission["trainer_config"]["runpod_template"].startswith("runpod-")

    assert len(FakeR2Client.instances) == 1
    r2 = FakeR2Client.instances[0]
    assert len(r2.uploads) == 4
    for local_path, r2_key in r2.uploads:
        assert Path(local_path).exists()
        assert r2_key.startswith("datasets/")
        assert "/processed/" in r2_key

    assert len(FakeVaultCatalog.instances) == 1
    vault = FakeVaultCatalog.instances[0]
    assert len(vault.completed_keys) == 4
    assert all("/processed/" in key for key in vault.completed_keys)

    for filename in tracks:
        assert not (inbox / filename).exists()
        assert (staging / filename).exists()

    assert list(inbox.glob("*.jsonl")) == []

    for track, _scenario in tracks.values():
        scenario_dirs = sorted((packet_root / track / "scenarios").glob("scenario-*"))
        assert len(scenario_dirs) == 3
        for scenario_dir in scenario_dirs:
            assert (scenario_dir / "manifest.json").exists()
            assert (scenario_dir / "prompts.jsonl").exists()
            assert (scenario_dir / "labels.jsonl").exists()

    assert watcher._audit_db_connection is not None
    run_rows = watcher._audit_db_connection.execute(
        f"SELECT source_file, track, scenario, packet_count, routed_count, submitted_jobs, vault_marked FROM {packet_watcher_module.TRAINING_RUNS_TABLE} ORDER BY source_file ASC;"
    ).fetchall()
    assert len(run_rows) == 4
    for row in run_rows:
        assert int(row["packet_count"]) == 3
        assert int(row["routed_count"]) == 3
        assert int(row["submitted_jobs"]) == 3
        assert int(row["vault_marked"]) == 1

    packet_rows = watcher._audit_db_connection.execute(
        f"SELECT run_id, packet_path, train_job_id, status, routing_manifest FROM {packet_watcher_module.PACKETS_TABLE} ORDER BY id ASC;"
    ).fetchall()
    assert len(packet_rows) == 12
    assert all(str(row["train_job_id"]).startswith("job-") for row in packet_rows)
    assert all(str(row["status"]) == "submitted" for row in packet_rows)
    for row in packet_rows:
        manifest = json.loads(str(row["routing_manifest"]))
        assert manifest["trainer_config"]["runpod_template"].startswith("runpod-")
        assert manifest["track"] in {"saudi_mod", "ukraine_mod", "nato", "indopac_mod"}

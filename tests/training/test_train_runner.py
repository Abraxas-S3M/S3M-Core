"""Unit tests for RunPod training execution runner."""

from __future__ import annotations

import builtins
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.training.train_runner import TrainRunner


class FakeR2Client:
    """In-memory R2 simulator for deterministic train runner tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload_file(self, local_path: str, remote_key: str) -> dict[str, Any]:
        path = Path(local_path)
        self.objects[remote_key] = path.read_bytes()
        return {"remote_key": remote_key, "size_bytes": len(self.objects[remote_key])}

    def generate_presigned_url(self, remote_key: str, expires_in: int = 86400) -> str:
        return f"https://r2.example/{remote_key}?exp={expires_in}"

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))

    def file_exists(self, remote_key: str) -> bool:
        return remote_key in self.objects

    def download_file(self, remote_key: str, local_path: str) -> dict[str, Any]:
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.objects[remote_key])
        return {"remote_key": remote_key, "size_bytes": len(self.objects[remote_key])}


class _TrainRunnerHarness(TrainRunner):
    """Test harness that overrides RunPod HTTP interactions."""

    def __init__(self, db_conn: Any, r2_client: Any) -> None:
        self._submit_payloads: list[dict[str, Any]] = []
        self._runpod_submit_response: dict[str, Any] = {"id": "rp-job-1", "status": "IN_QUEUE"}
        self._status_by_job_id: dict[str, dict[str, Any]] = {}
        super().__init__(db_conn=db_conn, r2_client=r2_client)

    def _submit_runpod_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._submit_payloads.append(payload)
        return dict(self._runpod_submit_response)

    def _fetch_runpod_status(self, job_id: str) -> dict[str, Any]:
        return dict(self._status_by_job_id[job_id])


@pytest.fixture
def train_runner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("R2_BUCKET", "s3m-vault")
    monkeypatch.setenv("R2_ENDPOINT", "https://account.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY", "test-access")
    monkeypatch.setenv("R2_SECRET_KEY", "test-secret")
    monkeypatch.setenv("RUNPOD_API_KEY", "test-runpod-key")
    monkeypatch.setenv("RUNPOD_ENDPOINT_ID", "test-endpoint")


def _runner_with_fakes() -> tuple[_TrainRunnerHarness, FakeR2Client]:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    fake_r2 = FakeR2Client()
    return _TrainRunnerHarness(db_conn=db, r2_client=fake_r2), fake_r2


def test_submit_job_uploads_packets_and_persists_job(
    tmp_path: Path,
    train_runner_env: None,
) -> None:
    runner, fake_r2 = _runner_with_fakes()
    packet = tmp_path / "packet-a.jsonl"
    packet.write_text('{"prompt":"Alpha","completion":"Bravo"}\n', encoding="utf-8")

    job_id = runner.submit_job(
        {
            "packet_files": [str(packet)],
            "trainer_config": {"max_steps": 20},
            "callback_url": "https://callback.example/train-done",
            "model_output_path": "training/results/alpha/",
        }
    )

    assert job_id == "rp-job-1"
    assert len(fake_r2.objects) == 1
    assert any("training/staging/" in key for key in fake_r2.objects)
    stored = runner._get_job(job_id)
    assert stored is not None
    assert stored.status == "pending"
    assert stored.output_path == "r2://s3m-vault/training/results/alpha/"
    assert runner._submit_payloads[0]["input"]["packet_urls"][0].startswith("https://r2.example/")


def test_check_job_status_normalizes_runpod_status(
    tmp_path: Path,
    train_runner_env: None,
) -> None:
    runner, _ = _runner_with_fakes()
    packet = tmp_path / "packet-b.jsonl"
    packet.write_text('{"prompt":"One","completion":"Two"}\n', encoding="utf-8")
    job_id = runner.submit_job({"packet_files": [str(packet)], "trainer_config": {"max_steps": 5}})

    runner._status_by_job_id[job_id] = {
        "id": job_id,
        "status": "RUNNING",
        "progress": 45,
        "eta_seconds": 120,
        "output": {"output_path": "r2://s3m-vault/training/output/rp-job-1/"},
    }
    status = runner.check_job_status(job_id)

    assert status["status"] == "running"
    assert status["progress"] == pytest.approx(0.45)
    assert status["eta_seconds"] == 120
    assert status["output_path"] == "r2://s3m-vault/training/output/rp-job-1/"


def test_monitor_jobs_downloads_completed_artifacts(
    tmp_path: Path,
    train_runner_env: None,
) -> None:
    runner, fake_r2 = _runner_with_fakes()
    packet = tmp_path / "packet-c.jsonl"
    packet.write_text('{"prompt":"Ready","completion":"Set"}\n', encoding="utf-8")
    job_id = runner.submit_job({"packet_files": [str(packet)], "trainer_config": {"max_steps": 5}})
    runner.artifact_root = tmp_path / "artifacts"
    runner.artifact_root.mkdir(parents=True, exist_ok=True)

    fake_r2.objects["training/output/rp-job-1/model.bin"] = b"trained-model"
    runner._status_by_job_id[job_id] = {
        "id": job_id,
        "status": "COMPLETED",
        "progress": 1.0,
        "output": {"output_path": "r2://s3m-vault/training/output/rp-job-1/"},
    }

    runner.monitor_jobs()

    downloaded = runner.artifact_root / job_id / "model.bin"
    assert downloaded.exists()
    assert downloaded.read_bytes() == b"trained-model"
    stored = runner._get_job(job_id)
    assert stored is not None
    assert stored.artifacts_downloaded is True
    assert stored.status == "completed"


def test_run_local_returns_failure_when_transformers_unavailable(
    tmp_path: Path,
    train_runner_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, _ = _runner_with_fakes()
    packet = tmp_path / "packet-d.jsonl"
    packet.write_text('{"prompt":"CPU test","completion":"local fallback"}\n', encoding="utf-8")

    real_import = builtins.__import__

    def guarded_import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0) -> Any:
        if name in {"torch", "transformers"}:
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    result = runner.run_local({"packet_files": [str(packet)], "trainer_config": {"max_steps": 2}})

    assert result["status"] == "failed"
    assert "transformers runtime unavailable" in result["error"]
    assert result["examples_trained"] == 1

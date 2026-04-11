"""Unit tests for RunPod GPU session lifecycle management."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

import src.training.gpu.session_manager as session_manager_mod
from src.training.gpu.eval_harness import EvalResult
from src.training.gpu.session_manager import GPUSessionManager, GrokTrainingBlockedError


class FakeObjectStorageConnector:
    def __init__(self, remote_root: Path) -> None:
        self.remote_root = remote_root
        self.pulls: list[str] = []
        self.pushes: list[str] = []
        self.json_writes: list[str] = []

    def sync_prefix_to_local(self, prefix: str, local_dir: str) -> bool:
        self.pulls.append(prefix)
        src = self.remote_root / prefix.strip("/")
        dest = Path(local_dir)
        dest.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            return False
        if src.is_file():
            shutil.copy2(src, dest / src.name)
            return True
        for path in src.rglob("*"):
            rel = path.relative_to(src)
            target = dest / rel
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        return True

    def sync_local_to_prefix(self, local_dir: str, prefix: str) -> bool:
        self.pushes.append(prefix)
        src = Path(local_dir)
        dest = self.remote_root / prefix.strip("/")
        if not src.exists():
            return False
        dest.mkdir(parents=True, exist_ok=True)
        for path in src.rglob("*"):
            rel = path.relative_to(src)
            target = dest / rel
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        return True

    def write_json(self, key: str, payload: Dict[str, Any]) -> bool:
        self.json_writes.append(key)
        target = self.remote_root / key.strip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True


class FakeTrainer:
    last_call: Dict[str, Any] = {}

    def __init__(self, engine_id: str, config: Any, output_dir: str, run_name: str) -> None:
        self.engine_id = engine_id
        self.output_dir = Path(output_dir) / run_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def train(
        self,
        dataset_path: str,
        resume_from: Optional[str] = None,
        max_runtime_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        FakeTrainer.last_call = {
            "dataset_path": dataset_path,
            "resume_from": resume_from,
            "max_runtime_seconds": max_runtime_seconds,
            "engine_id": self.engine_id,
        }
        adapter_dir = self.output_dir / "final_adapter"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        (adapter_dir / "adapter.bin").write_text("adapter", encoding="utf-8")

        checkpoint_dir = self.output_dir / "time_limit_checkpoint"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        (checkpoint_dir / "trainer_state.json").write_text("{}", encoding="utf-8")
        return {
            "adapter_path": str(adapter_dir),
            "elapsed_seconds": 123.4,
            "final_loss": 0.42,
            "examples_processed": 4096,
            "time_limit_reached": True,
            "checkpoint_path": str(checkpoint_dir),
        }


class FakeEvalHarness:
    def __init__(self, eval_data_dir: str) -> None:
        self.eval_data_dir = Path(eval_data_dir)
        self.eval_data_dir.mkdir(parents=True, exist_ok=True)

    def evaluate(self, engine_id: str, model_path: str, **_: Any) -> EvalResult:
        return EvalResult(
            engine_id=engine_id,
            eval_suite="fake-suite",
            scores={"structured_output": 0.91, "safety_refusal": 0.95},
            overall=0.93,
            passed=True,
            samples_evaluated=12,
            elapsed_seconds=1.2,
        )


def _set_workspace_paths(manager: GPUSessionManager, workspace_root: Path) -> None:
    manager.workspace_root = workspace_root
    manager.base_weights_root = workspace_root / "base_weights"
    manager.dataset_root = workspace_root / "datasets"
    manager.checkpoint_root = workspace_root / "checkpoints" / "runpod"
    manager.eval_root = workspace_root / "eval-results"
    manager.eval_harness = FakeEvalHarness(eval_data_dir=str(manager.eval_root))


def test_launch_session_runs_full_lifecycle_and_uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    remote_root = tmp_path / "remote"
    workspace_root = tmp_path / "workspace"
    (remote_root / "base-weights" / "phi3-medium").mkdir(parents=True, exist_ok=True)
    (remote_root / "base-weights" / "phi3-medium" / "model.safetensors").write_text("w", encoding="utf-8")
    scenarios = remote_root / "datasets" / "saudi_mod" / "scenarios"
    scenarios.mkdir(parents=True, exist_ok=True)
    (scenarios / "train.jsonl").write_text('{"prompt":"p","completion":"c"}\n', encoding="utf-8")
    existing_ckpt = remote_root / "checkpoints" / "runpod" / "phi3-medium" / "checkpoint-000000100"
    existing_ckpt.mkdir(parents=True, exist_ok=True)
    (existing_ckpt / "trainer_state.json").write_text("{}", encoding="utf-8")

    fake_connector = FakeObjectStorageConnector(remote_root=remote_root)
    monkeypatch.setattr(
        session_manager_mod.GPUSessionManager,
        "_load_object_storage_connector",
        lambda self: fake_connector,
    )
    monkeypatch.setattr(session_manager_mod, "S3MLoRATrainer", FakeTrainer)
    monkeypatch.setattr(session_manager_mod, "S3MEvalHarness", FakeEvalHarness)
    monkeypatch.setattr(session_manager_mod.sys.stdin, "isatty", lambda: False)

    manager = GPUSessionManager()
    _set_workspace_paths(manager, workspace_root)
    result = manager.launch_session(engine_id="phi3-medium", track="saudi_mod", max_runtime_hours=1.5)

    assert result.engine_id == "phi3-medium"
    assert result.track == "saudi_mod"
    assert result.uploaded_to_object_storage is True
    assert result.eval_scores["structured_output"] == pytest.approx(0.91)
    assert "checkpoint-000000100" in str(FakeTrainer.last_call["resume_from"])
    assert FakeTrainer.last_call["max_runtime_seconds"] == pytest.approx(5400.0)

    adapter_mirror = remote_root / "adapters" / "phi3-medium" / "saudi_mod"
    assert any(adapter_mirror.rglob("adapter.bin"))

    eval_mirror = remote_root / "eval-results" / "phi3-medium" / "saudi_mod"
    assert any(eval_mirror.rglob("session-*.json"))

    verdict_dir = remote_root / "grok-verdicts" / "pending"
    assert any(verdict_dir.glob("session-*.json"))

    metadata_files = list((workspace_root / "eval-results" / "phi3-medium" / "saudi_mod").glob("session-*.json"))
    assert metadata_files
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["resumed_from"] is not None
    assert metadata["final_loss"] == pytest.approx(0.42)


def test_grok_engine_is_hard_blocked_at_multiple_entry_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote_root = tmp_path / "remote"
    fake_connector = FakeObjectStorageConnector(remote_root=remote_root)
    monkeypatch.setattr(
        session_manager_mod.GPUSessionManager,
        "_load_object_storage_connector",
        lambda self: fake_connector,
    )
    monkeypatch.setattr(session_manager_mod, "S3MEvalHarness", FakeEvalHarness)

    manager = GPUSessionManager()
    _set_workspace_paths(manager, tmp_path / "workspace")

    with pytest.raises(GrokTrainingBlockedError):
        manager.launch_session(engine_id="grok-300b", track="saudi_mod")
    with pytest.raises(GrokTrainingBlockedError):
        manager.sync_from_object_storage(engine_id="grok-300b", track="saudi_mod")
    with pytest.raises(GrokTrainingBlockedError):
        manager.sync_to_object_storage(engine_id="grok-300b", track="saudi_mod", adapter_dir=tmp_path)


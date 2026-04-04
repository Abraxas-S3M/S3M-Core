"""Unit tests for hierarchical checkpointing in CPU adaptation workflows."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.training.cpu_adaptation.checkpointing import CheckpointPolicy, HierarchicalCheckpointer

try:
    import torch

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime
    torch = None  # type: ignore
    TORCH_AVAILABLE = False


def _skip_if_no_torch() -> None:
    if not TORCH_AVAILABLE:
        pytest.skip("torch not installed in test environment")


def test_save_and_resume_round_trip(tmp_path: Path) -> None:
    _skip_if_no_torch()
    policy = CheckpointPolicy(l2_every_n_l1=999, checkpoint_dir="checkpoints")
    checkpointer = HierarchicalCheckpointer(model_id="edge-model", policy=policy, base_dir=str(tmp_path))

    model = torch.nn.Linear(4, 2)  # type: ignore[union-attr]
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)  # type: ignore[union-attr]
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.5)  # type: ignore[union-attr]

    model_state = model.state_dict()
    optimizer_state = optimizer.state_dict()
    scheduler_state = scheduler.state_dict()

    manifest = checkpointer.save_checkpoint(
        step=10,
        epoch=2,
        loss=0.25,
        model_state=model_state,
        optimizer_state=optimizer_state,
        scheduler_state=scheduler_state,
        extra_metadata={"precision_used": "fp32", "peak_memory_mb": 128.0},
    )
    assert manifest.is_complete is True
    assert Path(manifest.path).exists()

    latest = checkpointer.find_latest_checkpoint()
    assert latest is not None
    assert latest.step == 10

    new_model = torch.nn.Linear(4, 2)  # type: ignore[union-attr]
    new_optimizer = torch.optim.SGD(new_model.parameters(), lr=0.1)  # type: ignore[union-attr]
    new_scheduler = torch.optim.lr_scheduler.StepLR(new_optimizer, step_size=1, gamma=0.5)  # type: ignore[union-attr]

    resumed_step = checkpointer.resume_training_state(new_model, new_optimizer, new_scheduler)
    assert resumed_step == 10


def test_fallback_to_previous_checkpoint_when_latest_corrupt(tmp_path: Path) -> None:
    _skip_if_no_torch()
    policy = CheckpointPolicy(l2_every_n_l1=999, checkpoint_dir="checkpoints")
    checkpointer = HierarchicalCheckpointer(model_id="edge-model", policy=policy, base_dir=str(tmp_path))

    tensor = torch.tensor([1.0, 2.0])  # type: ignore[union-attr]
    checkpointer.save_checkpoint(
        step=10,
        epoch=1,
        loss=0.4,
        model_state={"w": tensor},
        optimizer_state={"lr": 0.1},
    )
    latest_manifest = checkpointer.save_checkpoint(
        step=20,
        epoch=2,
        loss=0.2,
        model_state={"w": tensor * 2},
        optimizer_state={"lr": 0.05},
    )

    state_path = Path(latest_manifest.path) / "state.pt"
    state_path.write_bytes(b"corrupted")

    recovered = checkpointer.find_latest_checkpoint()
    assert recovered is not None
    assert recovered.step == 10


def test_interrupted_tmp_write_cleanup(tmp_path: Path) -> None:
    _skip_if_no_torch()
    checkpoints_dir = tmp_path / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    interrupted_dir = checkpoints_dir / "checkpoint-000000001.tmp"
    interrupted_dir.mkdir(parents=True, exist_ok=True)
    (interrupted_dir / "manifest.json").write_text("{}", encoding="utf-8")

    policy = CheckpointPolicy(l2_every_n_l1=999, checkpoint_dir="checkpoints")
    checkpointer = HierarchicalCheckpointer(model_id="edge-model", policy=policy, base_dir=str(tmp_path))

    assert not interrupted_dir.exists()
    manifest = checkpointer.save_checkpoint(
        step=1,
        epoch=1,
        loss=1.0,
        model_state={"v": torch.tensor([1.0])},  # type: ignore[union-attr]
        optimizer_state={"lr": 0.1},
    )
    assert Path(manifest.path).exists()


class _AlwaysUpBroker:
    def any_bearer_up(self) -> bool:
        return True


def test_async_peer_replication_and_inventory(tmp_path: Path) -> None:
    _skip_if_no_torch()
    policy = CheckpointPolicy(
        l2_every_n_l1=1,
        l3_every_n_l2=1,
        max_l1_checkpoints=2,
        max_l2_checkpoints=1,
        checkpoint_dir="checkpoints",
    )
    checkpointer = HierarchicalCheckpointer(model_id="edge-model", policy=policy, base_dir=str(tmp_path))
    checkpointer._bearer_broker = _AlwaysUpBroker()

    for step in (1, 2, 3):
        checkpointer.save_checkpoint(
            step=step,
            epoch=1,
            loss=1.0 / step,
            model_state={"v": torch.tensor([float(step)])},  # type: ignore[union-attr]
            optimizer_state={"lr": 0.1},
        )

    checkpointer._replication_queue.join()
    time.sleep(0.05)

    inventory = checkpointer.get_checkpoint_inventory()
    assert inventory["levels"]["l1"]["count"] == 2
    assert inventory["levels"]["l2"]["count"] == 1
    assert inventory["levels"]["l3"]["count"] >= 1


def test_manifest_is_json_readable(tmp_path: Path) -> None:
    _skip_if_no_torch()
    checkpointer = HierarchicalCheckpointer(
        model_id="edge-model",
        policy=CheckpointPolicy(checkpoint_dir="checkpoints", l2_every_n_l1=999),
        base_dir=str(tmp_path),
    )
    manifest = checkpointer.save_checkpoint(
        step=7,
        epoch=1,
        loss=0.7,
        model_state={"v": torch.tensor([7.0])},  # type: ignore[union-attr]
        optimizer_state={"lr": 0.1},
    )
    manifest_path = Path(manifest.path) / "manifest.json"
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert parsed["is_complete"] is True
    assert parsed["step"] == 7

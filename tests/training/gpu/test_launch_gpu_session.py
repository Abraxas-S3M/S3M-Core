"""Unit tests for scripts/training/launch_gpu_session.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from src.training.gpu.session_manager import GrokTrainingBlockedError, SessionResult


def _load_launcher_module():
    module_path = Path("scripts/training/launch_gpu_session.py").resolve()
    spec = importlib.util.spec_from_file_location("launch_gpu_session_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_blocks_grok_engine(capsys) -> None:
    mod = _load_launcher_module()

    class FakeManager:
        def __init__(self, config_path: str) -> None:
            self.config_path = config_path

        def launch_session(self, **kwargs):
            raise GrokTrainingBlockedError(
                "Grok-300B is too large for GPU training. "
                "It remains in Cloudflare R2 as a validation oracle only."
            )

    rc = mod.main(
        argv=["--engine", "grok-300b", "--track", "saudi_mod"],
        manager_cls=FakeManager,
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert 'ERROR: "Grok-300B is too large for GPU training.' in captured.err


def test_main_prints_session_result_json(capsys) -> None:
    mod = _load_launcher_module()

    class FakeManager:
        def __init__(self, config_path: str) -> None:
            self.config_path = config_path

        def launch_session(self, **kwargs):
            return SessionResult(
                engine_id="mistral-7b",
                track="nato",
                adapter_path="/workspace/checkpoints/runpod/mistral-7b/final_adapter",
                final_loss=0.31,
                eval_scores={"opord_structure": 0.9},
                training_duration_seconds=99.0,
                examples_processed=2048,
                uploaded_to_object_storage=True,
            )

    rc = mod.main(
        argv=["--engine", "mistral-7b", "--track", "nato", "--max-hours", "2"],
        manager_cls=FakeManager,
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["engine_id"] == "mistral-7b"
    assert payload["track"] == "nato"
    assert payload["uploaded_to_object_storage"] is True


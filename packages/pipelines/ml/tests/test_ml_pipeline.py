from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.pipelines.ml.ml_pipeline import MLServicesPipeline


def test_model_readiness_structure() -> None:
    readiness = MLServicesPipeline().get_model_readiness()
    assert set(readiness.keys()) == {"ml-huggingface", "ml-labelstudio", "ml-wandb", "ml-clearml", "ml-langfuse"}


def test_deployment_readiness_checks() -> None:
    report = MLServicesPipeline().check_deployment_readiness()
    assert "ready" in report
    assert "missing_models" in report
    assert isinstance(report["missing_models"], list)


def test_training_pipeline_status() -> None:
    status = MLServicesPipeline().get_training_pipeline_status()
    assert set(status.keys()) == {"labeling", "orchestration", "tracking", "models", "monitoring"}


def test_health_check_all_providers() -> None:
    health = MLServicesPipeline().health_check()
    assert set(health["providers"].keys()) == {"ml-huggingface", "ml-labelstudio", "ml-wandb", "ml-clearml", "ml-langfuse"}

"""ClearML adapter for experiment, model, dataset, and pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier

from .config import ClearMLConfig


class ClearMLAdapter(ProviderAdapter):
    def __init__(self, config: ClearMLConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or ClearMLConfig()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def _env(self, key: str, default: str = "") -> str:
        import os

        return os.getenv(f"S3M_{key}", os.getenv(key, default))

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="ml-clearml",
            category=ProviderCategory.AI_ML_SERVICES,
            tier=ProviderTier.FREE,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["CLEARML_API_ACCESS_KEY", "CLEARML_API_SECRET_KEY"],
            optional_env_vars=["CLEARML_API_HOST"],
            supported_schemas=["ExperimentTask", "ModelVersion", "DatasetVersion", "PipelineStatus"],
        )

    def validate_credentials(self) -> dict[str, Any]:
        if self.mode == "airgapped" or self.config.offline_mode:
            return {"valid": True, "mode": "airgapped", "offline_mode": True}
        access = self._env("CLEARML_API_ACCESS_KEY")
        secret = self._env("CLEARML_API_SECRET_KEY")
        return {"valid": bool(access and secret), "mode": "online"}

    def list_experiments(self, project: str | None = None, limit: int = 50) -> dict[str, Any]:
        experiments = self._load_fixture_json("experiments_list.json").get("experiments", [])
        if project:
            experiments = [item for item in experiments if item.get("project") == project]
        return {"experiments": experiments[:limit], "count": min(len(experiments), limit), "project": project}

    def get_experiment(self, task_id: str) -> dict[str, Any]:
        for item in self._load_fixture_json("experiments_list.json").get("experiments", []):
            if item.get("task_id") == task_id:
                return item
        return {"error": "task_not_found", "task_id": task_id}

    def list_models(self, project: str | None = None) -> list[dict[str, Any]]:
        models = self._load_fixture_json("models_list.json").get("models", [])
        if project:
            return [item for item in models if item.get("project") == project]
        return models

    def list_datasets(self, project: str | None = None) -> list[dict[str, Any]]:
        datasets = self._load_fixture_json("experiments_list.json").get("datasets", [])
        if project:
            return [item for item in datasets if item.get("project") == project]
        return datasets

    def list_pipelines(self) -> list[dict[str, Any]]:
        status = self._load_fixture_json("pipeline_status.json")
        if "pipelines" in status and isinstance(status.get("pipelines"), list):
            return status.get("pipelines", [])
        if "pipeline_id" in status:
            return [status]
        return []

    def get_pipeline_status(self, pipeline_id: str) -> dict[str, Any]:
        for pipe in self.list_pipelines():
            if pipe.get("pipeline_id") == pipeline_id:
                return pipe
        return {"error": "pipeline_not_found", "pipeline_id": pipeline_id}

    def get_training_overview(self) -> dict[str, Any]:
        experiments = self.list_experiments(limit=200).get("experiments", [])
        models = self.list_models()
        datasets = self.list_datasets()
        pipelines = self.list_pipelines()
        return {
            "experiments": experiments,
            "models": models,
            "datasets": datasets,
            "pipelines": pipelines,
            "latest_experiment": experiments[0] if experiments else None,
            "active_pipelines": [pipe for pipe in pipelines if pipe.get("status") in {"queued", "running"}],
        }

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        action = str(params.get("action", "overview")).lower()
        if action == "experiments":
            return self.list_experiments(params.get("project"), int(params.get("limit", 50)))
        if action == "models":
            return {"models": self.list_models(params.get("project"))}
        if action == "datasets":
            return {"datasets": self.list_datasets(params.get("project"))}
        if action == "pipelines":
            return {"pipelines": self.list_pipelines()}
        return self.get_training_overview()

    def normalize(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        return raw_data

    def health_check(self) -> dict[str, Any]:
        overview = self.get_training_overview()
        return {
            "status": "ok",
            "detail": {
                "experiments": len(overview.get("experiments", [])),
                "models": len(overview.get("models", [])),
                "pipelines": len(overview.get("pipelines", [])),
                "offline_mode": self.config.offline_mode or self.mode == "airgapped",
            },
        }

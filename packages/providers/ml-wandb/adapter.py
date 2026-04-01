"""Weights & Biases adapter for experiment tracking and model artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier

from .config import WandBConfig


class WandBAdapter(ProviderAdapter):
    def __init__(self, config: WandBConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or WandBConfig()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def _is_offline_mode(self) -> bool:
        return self.mode == "airgapped" or self.config.offline_mode

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="ml-wandb",
            category=ProviderCategory.AI_ML_SERVICES,
            tier=ProviderTier.FREEMIUM,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["WANDB_API_KEY"],
            optional_env_vars=["WANDB_BASE_URL"],
            supported_schemas=["ExperimentRun", "ModelArtifact", "TrainingStatus"],
        )

    def validate_credentials(self) -> dict[str, Any]:
        if self._is_offline_mode():
            return {"valid": True, "mode": "airgapped", "offline_mode": True}
        return {"valid": False, "detail": "online credential validation not enabled in offline-first mode"}

    def _load_runs(self) -> list[dict[str, Any]]:
        return list(self._load_fixture_json("runs_list.json").get("runs", []))

    def list_runs(self, project: str, limit: int = 50) -> dict[str, Any]:
        runs = [run for run in self._load_runs() if run.get("project") == project]
        return {"project": project, "runs": runs[:limit], "count": min(len(runs), limit)}

    def get_run(self, project: str, run_id: str) -> dict[str, Any]:
        detail = self._load_fixture_json("run_detail.json")
        if detail.get("project") == project and detail.get("run_id") == run_id:
            return detail
        for run in self._load_runs():
            if run.get("project") == project and run.get("run_id") == run_id:
                return {"project": project, "run_id": run_id, "summary": run, "metrics_history": [], "artifacts": []}
        return {"error": "run_not_found", "project": project, "run_id": run_id}

    def get_best_run(self, project: str, metric: str = "mAP", direction: str = "max") -> dict[str, Any]:
        runs = self.list_runs(project).get("runs", [])
        if not runs:
            return {"project": project, "best_run": None}
        reverse = direction.lower() != "min"
        best = sorted(runs, key=lambda item: float(item.get("metrics", {}).get(metric, float("-inf"))), reverse=reverse)[0]
        return {"project": project, "metric": metric, "direction": direction, "best_run": best}

    def list_artifacts(self, project: str) -> list[dict[str, Any]]:
        detail = self._load_fixture_json("run_detail.json")
        artifacts = detail.get("artifacts", [])
        return [item for item in artifacts if item.get("project") == project]

    def download_artifact(self, project: str, artifact_name: str, version: str = "latest") -> dict[str, Any]:
        for artifact in self.list_artifacts(project):
            if artifact.get("name") == artifact_name and (version == "latest" or artifact.get("version") == version):
                # Tactical context: preserve model lineage for mission model rollback.
                return {
                    "project": project,
                    "artifact": artifact_name,
                    "version": artifact.get("version"),
                    "path": artifact.get("local_path"),
                }
        return {"error": "artifact_not_found", "project": project, "artifact": artifact_name, "version": version}

    def get_training_status(self) -> dict[str, Any]:
        projects: dict[str, dict[str, Any]] = {}
        total_runs = 0
        for project_name in self.config.s3m_projects:
            project_runs = self.list_runs(project_name, limit=500)["runs"]
            total_runs += len(project_runs)
            if project_runs:
                latest = max(project_runs, key=lambda item: str(item.get("created_at", "")))
                best = self.get_best_run(project_name, metric="mAP", direction="max").get("best_run") or latest
                projects[project_name] = {
                    "latest_run": latest.get("created_at"),
                    "best_metric": "mAP",
                    "best_value": float((best.get("metrics") or {}).get("mAP", 0.0)),
                    "active_runs": sum(1 for run in project_runs if str(run.get("state", "")).lower() == "running"),
                }
            else:
                projects[project_name] = {
                    "latest_run": None,
                    "best_metric": "mAP",
                    "best_value": 0.0,
                    "active_runs": 0,
                }
        return {"projects": projects, "total_runs": total_runs}

    def compare_runs(self, project: str, run_ids: list[str]) -> dict[str, Any]:
        runs = {run.get("run_id"): run for run in self.list_runs(project).get("runs", [])}
        comparison: dict[str, dict[str, Any]] = {}
        for run_id in run_ids:
            payload = runs.get(run_id)
            if payload:
                comparison[run_id] = {
                    "metrics": payload.get("metrics", {}),
                    "config": payload.get("config", {}),
                }
        return {"project": project, "runs": comparison}

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        action = str(params.get("action", "status")).lower()
        if action == "runs":
            return self.list_runs(str(params.get("project", "")), int(params.get("limit", 50)))
        if action == "best":
            return self.get_best_run(
                str(params.get("project", "")),
                metric=str(params.get("metric", "mAP")),
                direction=str(params.get("direction", "max")),
            )
        return self.get_training_status()

    def normalize(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        return raw_data

    def health_check(self) -> dict[str, Any]:
        status = self.get_training_status()
        return {"status": "ok", "detail": {"projects": len(status.get("projects", {})), "offline_mode": self._is_offline_mode()}}

"""AI/ML services readiness pipeline spanning model, data, and observability layers."""

from __future__ import annotations

from typing import Any

from packages.providers.registry import ProviderRegistry


class MLServicesPipeline:
    def __init__(self, mode: str = "airgapped") -> None:
        self.mode = mode
        self.registry = ProviderRegistry()
        self.registry.register_default_ml_providers(mode=mode)
        self.providers = self.registry.as_dict()

    def get_model_readiness(self) -> dict[str, Any]:
        hf = self.providers["ml-huggingface"].get_s3m_model_status()
        ls_projects = self.providers["ml-labelstudio"].list_projects()
        ls_ready = []
        for project in ls_projects:
            total = int(project.get("task_number", project.get("total_tasks", 0)))
            done = int(project.get("num_tasks_with_annotations", 0))
            if total > 0 and done > 0:
                ls_ready.append(
                    {
                        "id": project.get("id"),
                        "title": project.get("title"),
                        "completed": done,
                        "total": total,
                    }
                )
        wb = self.providers["ml-wandb"].get_training_status()
        clearml = self.providers["ml-clearml"].get_training_overview()
        langfuse = self.providers["ml-langfuse"].get_llm_health()
        return {
            "ml-huggingface": hf,
            "ml-labelstudio": {"projects_ready_for_training": ls_ready, "count_ready": len(ls_ready)},
            "ml-wandb": wb,
            "ml-clearml": clearml,
            "ml-langfuse": langfuse,
        }

    def get_training_pipeline_status(self) -> dict[str, Any]:
        projects = self.providers["ml-labelstudio"].list_projects()
        ready_data = [
            {
                "project_id": p.get("id"),
                "project_name": p.get("title"),
                "completed_annotations": int(p.get("num_tasks_with_annotations", 0)),
            }
            for p in projects
            if int(p.get("num_tasks_with_annotations", 0)) > 0
        ]
        clearml_overview = self.providers["ml-clearml"].get_training_overview()
        wandb_status = self.providers["ml-wandb"].get_training_status()
        hf_status = self.providers["ml-huggingface"].get_s3m_model_status()
        langfuse_metrics = self.providers["ml-langfuse"].get_daily_metrics(days=7)
        latest_experiment = clearml_overview.get("latest_experiment")
        latest_experiments = {}
        if isinstance(latest_experiment, dict) and latest_experiment:
            latest_experiments = {
                str(latest_experiment.get("project", "unknown")): {
                    "id": latest_experiment.get("id"),
                    "name": latest_experiment.get("name"),
                    "status": latest_experiment.get("status"),
                }
            }
        return {
            "labeling": {"ready_datasets": ready_data, "projects_count": len(projects)},
            "orchestration": {
                "active_pipelines": len(clearml_overview.get("active_pipelines", [])),
                "latest_experiments": latest_experiments,
            },
            "tracking": {"projects": wandb_status.get("projects", {}), "total_runs": wandb_status.get("total_runs", 0)},
            "models": {
                "cached": hf_status.get("total_cached", 0),
                "required": hf_status.get("total_required", 0),
                "cache_complete": hf_status.get("cache_complete", False),
            },
            "monitoring": {"daily": langfuse_metrics.get("days", [])},
        }

    def check_deployment_readiness(self) -> dict[str, Any]:
        hf_status = self.providers["ml-huggingface"].get_s3m_model_status()
        missing_models = [name for name, payload in hf_status.get("models", {}).items() if not payload.get("cached", False)]
        unquantized_models = [name for name, payload in hf_status.get("models", {}).items() if not payload.get("quantized", False)]
        llm_health = self.providers["ml-langfuse"].get_llm_health()
        langfuse_status = llm_health.get("overall", "unknown")
        ready = not missing_models and not unquantized_models and langfuse_status == "healthy"
        return {
            "ready": ready,
            "missing_models": missing_models,
            "unquantized_models": unquantized_models,
            "langfuse_status": langfuse_status,
        }

    def health_check(self) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        overall = "ok"
        for provider_id in sorted(self.providers.keys()):
            health = self.providers[provider_id].health_check()
            checks[provider_id] = health
            if health.get("status") != "ok":
                overall = "degraded"
        return {"status": overall, "providers": checks}

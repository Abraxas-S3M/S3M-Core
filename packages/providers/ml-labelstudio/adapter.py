"""Label Studio adapter for S3M training data annotation workflows."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier
from .config import LabelStudioConfig


class LabelStudioAdapter(ProviderAdapter):
    def __init__(self, config: LabelStudioConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or LabelStudioConfig()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="ml-labelstudio",
            category=ProviderCategory.AI_ML_SERVICES,
            tier=ProviderTier.FREE,
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["LABELSTUDIO_URL", "LABELSTUDIO_TOKEN"],
            supported_schemas=["S3MAnnotation", "S3MTrainingDataset"],
        )

    def _build_headers(self) -> dict[str, str]:
        token = self._env("LABELSTUDIO_TOKEN")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Token {token}"
        return headers

    def _env(self, key: str, default: str = "") -> str:
        import os

        return os.getenv(f"S3M_{key}", os.getenv(key, default))

    def validate_credentials(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            projects = self._load_fixture_json("projects_list.json")
            return {"valid": True, "mode": "airgapped", "projects": len(projects.get("results", []))}
        base = self._env("LABELSTUDIO_URL", self.config.base_url).rstrip("/")
        result = self._request("GET", f"{base}/api/projects", headers=self._build_headers())
        return {"valid": "error" not in result, "detail": result}

    def create_project(self, template_name: str) -> dict[str, Any]:
        template = self.config.s3m_project_templates.get(template_name)
        if not template:
            return {"error": "unknown_template", "detail": template_name}
        if self.mode == "airgapped":
            return {"id": 999, "template_name": template_name, **template}
        base = self._env("LABELSTUDIO_URL", self.config.base_url).rstrip("/")
        payload = {
            "title": template["title"],
            "description": template["description"],
            "label_config": template["label_config"],
        }
        return self._request("POST", f"{base}/api/projects", headers=self._build_headers(), payload=payload)

    def list_projects(self) -> list[dict[str, Any]]:
        if self.mode == "airgapped":
            return self._load_fixture_json("projects_list.json").get("results", [])
        base = self._env("LABELSTUDIO_URL", self.config.base_url).rstrip("/")
        return self._request("GET", f"{base}/api/projects", headers=self._build_headers()).get("results", [])

    def import_tasks(self, project_id: int, data: list[dict[str, Any]]) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"project_id": project_id, "imported": len(data), "status": "accepted"}
        base = self._env("LABELSTUDIO_URL", self.config.base_url).rstrip("/")
        return self._request("POST", f"{base}/api/projects/{project_id}/import", headers=self._build_headers(), payload=data)

    def get_annotations(self, project_id: int) -> list[dict[str, Any]]:
        if self.mode == "airgapped":
            if project_id == 101:
                return self._load_fixture_json("annotations_sar.json").get("annotations", [])
            return []
        base = self._env("LABELSTUDIO_URL", self.config.base_url).rstrip("/")
        tasks = self._request("GET", f"{base}/api/projects/{project_id}/tasks", headers=self._build_headers()).get("tasks", [])
        out: list[dict[str, Any]] = []
        for task in tasks:
            task_id = task.get("id")
            if task_id is None:
                continue
            ann = self._request("GET", f"{base}/api/tasks/{task_id}/annotations", headers=self._build_headers())
            if isinstance(ann, list):
                out.extend(ann)
        return out

    def export_project(self, project_id: int, format: str = "JSON") -> dict[str, Any]:
        if self.mode == "airgapped":
            if format.upper() == "JSON":
                return self._load_fixture_json("annotations_sar.json")
            return {"project_id": project_id, "format": format, "results": []}
        base = self._env("LABELSTUDIO_URL", self.config.base_url).rstrip("/")
        return self._request(
            "GET",
            f"{base}/api/projects/{project_id}/export?exportType={format}",
            headers=self._build_headers(),
        )

    def get_labeling_progress(self, project_id: int) -> dict[str, Any]:
        projects = self.list_projects()
        target = next((project for project in projects if int(project.get("id", -1)) == int(project_id)), None)
        if not target:
            return {"total_tasks": 0, "completed": 0, "progress_pct": 0.0, "annotators": 0}
        total = int(target.get("task_number", target.get("total_tasks", 0)))
        completed = int(target.get("num_tasks_with_annotations", 0))
        pct = round((completed / total) * 100.0, 2) if total else 0.0
        annotators = int(target.get("num_annotators", len(target.get("annotators", []))))
        return {"total_tasks": total, "completed": completed, "progress_pct": pct, "annotators": annotators}

    def _convert_to_yolo(self, annotations: list[dict[str, Any]]) -> dict[str, Any]:
        class_map = {"ship": 0, "oil_platform": 1, "buoy": 2, "debris": 3}
        yolo_files: dict[str, list[str]] = {}
        for item in annotations:
            image_name = str(item.get("image", "unknown.jpg"))
            width_px = float(item.get("width", 1.0))
            height_px = float(item.get("height", 1.0))
            records: list[str] = []
            objects = item.get("boxes") or item.get("objects") or []
            for box in objects:
                cls = class_map.get(str(box.get("label", "ship")), 0)
                if {"x_center", "y_center", "width", "height"}.issubset(box.keys()):
                    x_center = float(box.get("x_center", 0.5))
                    y_center = float(box.get("y_center", 0.5))
                    width = float(box.get("width", 0.2))
                    height = float(box.get("height", 0.2))
                else:
                    x = float(box.get("x", 0.0))
                    y = float(box.get("y", 0.0))
                    w = float(box.get("w", box.get("width", 1.0)))
                    h = float(box.get("h", box.get("height", 1.0)))
                    x_center = (x + (w / 2.0)) / max(width_px, 1.0)
                    y_center = (y + (h / 2.0)) / max(height_px, 1.0)
                    width = w / max(width_px, 1.0)
                    height = h / max(height_px, 1.0)
                records.append(f"{cls} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
            yolo_files[Path(image_name).with_suffix(".txt").name] = records
        return {"format": "yolo", "files": yolo_files, "samples": len(annotations)}

    def _convert_to_coco(self, annotations: list[dict[str, Any]]) -> dict[str, Any]:
        categories = [
            {"id": 1, "name": "ship"},
            {"id": 2, "name": "oil_platform"},
            {"id": 3, "name": "buoy"},
            {"id": 4, "name": "debris"},
        ]
        images: list[dict[str, Any]] = []
        coco_annotations: list[dict[str, Any]] = []
        ann_id = 1
        for idx, item in enumerate(annotations, start=1):
            images.append({"id": idx, "file_name": item.get("image", f"image_{idx}.jpg"), "width": 1024, "height": 1024})
            for box in item.get("boxes") or item.get("objects") or []:
                x = float(box.get("x", 0.0))
                y = float(box.get("y", 0.0))
                w = float(box.get("w", box.get("width", 50.0)))
                h = float(box.get("h", box.get("height", 50.0)))
                label = str(box.get("label", "ship"))
                category_id = next((c["id"] for c in categories if c["name"] == label), 1)
                coco_annotations.append(
                    {"id": ann_id, "image_id": idx, "category_id": category_id, "bbox": [x, y, w, h], "area": w * h, "iscrowd": 0}
                )
                ann_id += 1
        return {"format": "coco", "images": images, "annotations": coco_annotations, "categories": categories, "samples": len(annotations)}

    def _convert_to_conll(self, annotations: list[dict[str, Any]]) -> dict[str, Any]:
        lines: list[str] = []
        for item in annotations:
            text = str(item.get("text", ""))
            entities = item.get("entities", [])
            token_labels = {int(entity.get("token_idx", -1)): str(entity.get("label", "O")) for entity in entities}
            for idx, token in enumerate(text.split()):
                label = token_labels.get(idx, "O")
                lines.append(f"{token} {label}")
            lines.append("")
        return {"format": "conll", "content": "\n".join(lines), "samples": len(annotations)}

    def export_for_training(self, project_id: int, output_format: str = "yolo") -> dict[str, Any]:
        if self.mode == "airgapped":
            annotations = self._load_fixture_json("annotations_sar.json").get("annotations", [])
            projects = self.list_projects()
            project = next((p for p in projects if int(p.get("id", -1)) == int(project_id)), {"title": f"project_{project_id}"})
            project_name = str(project.get("title", f"project_{project_id}")).lower().replace(" ", "_")
        else:
            annotations = self.get_annotations(project_id)
            project_name = f"project_{project_id}"

        fmt = output_format.lower()
        if fmt == "yolo":
            converted = self._convert_to_yolo(annotations)
        elif fmt == "coco":
            converted = self._convert_to_coco(annotations)
        elif fmt == "conll":
            converted = self._convert_to_conll(annotations)
        else:
            return {"error": "unsupported_format", "detail": output_format}

        out_dir = Path("data/training") / project_name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"annotations_{fmt}.json"
        out_path.write_text(json.dumps(converted, indent=2), encoding="utf-8")
        return {"output_path": str(out_path), "format": fmt, "samples": int(converted.get("samples", 0))}

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        action = str(params.get("action", "list_projects"))
        if action == "list_projects":
            return {"projects": self.list_projects()}
        if action == "progress":
            return self.get_labeling_progress(int(params.get("project_id", 0)))
        if action == "annotations":
            return {"annotations": self.get_annotations(int(params.get("project_id", 0)))}
        if action == "export":
            return self.export_for_training(int(params.get("project_id", 0)), str(params.get("format", "yolo")))
        return {"error": "unsupported_action", "detail": action}

    def normalize(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        cred = self.validate_credentials()
        return {
            "status": "ok" if cred.get("valid") else "degraded",
            "detail": cred,
            "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
        }

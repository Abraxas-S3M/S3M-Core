from __future__ import annotations

import importlib
from pathlib import Path


def _load():
    adapter_mod = importlib.import_module("packages.providers.ml-labelstudio.adapter")
    config_mod = importlib.import_module("packages.providers.ml-labelstudio.config")
    return adapter_mod.LabelStudioAdapter, config_mod.LabelStudioConfig


def test_manifest_correct() -> None:
    Adapter, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "ml-labelstudio"
    assert m.tier.value == "FREE"
    assert m.auth_type == "api_key"
    assert m.category.value == "AI_ML_SERVICES"


def test_project_templates_defined() -> None:
    _, Config = _load()
    cfg = Config()
    assert len(cfg.s3m_project_templates) == 4
    assert set(cfg.s3m_project_templates.keys()) == {
        "sar_ship_detection",
        "military_vehicle_detection",
        "arabic_ner",
        "threat_classification",
    }


def test_template_label_configs_valid() -> None:
    _, Config = _load()
    cfg = Config()
    for template in cfg.s3m_project_templates.values():
        label_config = template.get("label_config", "")
        assert isinstance(label_config, str)
        assert label_config.strip()
        assert "<View>" in label_config


def test_labeling_progress_structure() -> None:
    Adapter, _ = _load()
    progress = Adapter(mode="airgapped").get_labeling_progress(101)
    assert {"total_tasks", "completed", "progress_pct", "annotators"}.issubset(progress.keys())


def test_export_yolo_format(tmp_path: Path) -> None:
    Adapter, Config = _load()
    cfg = Config()
    adapter = Adapter(config=cfg, mode="airgapped")
    result = adapter.export_for_training(101, "yolo")
    assert result["format"] == "yolo"
    assert result["samples"] == 5
    assert Path(result["output_path"]).exists()


def test_export_coco_format() -> None:
    Adapter, _ = _load()
    adapter = Adapter(mode="airgapped")
    annotations = adapter.get_annotations(101)
    coco = adapter._convert_to_coco(annotations)
    assert coco["format"] == "coco"
    assert len(coco["images"]) == 5
    assert len(coco["annotations"]) >= 5
    assert len(coco["categories"]) == 4


def test_fetch_airgapped() -> None:
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").fetch({"action": "list_projects"})
    assert "projects" in out
    assert len(out["projects"]) == 2

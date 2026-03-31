"""
S3M Weight Vault Manager
Pulls model weights from open-source repos, stores in GCS, syncs to local.
"""

import os
from typing import Optional, Dict
from pathlib import Path
from .engine_registry import EngineRegistry, EngineID, EngineConfig


class WeightStatus:
    def __init__(self, engine_id: EngineID):
        self.engine_id = engine_id
        self.hf_available: bool = False
        self.gcs_available: bool = False
        self.local_available: bool = False
        self.local_size_gb: float = 0.0


class WeightManager:
    def __init__(self, models_root: str = "models"):
        self.registry = EngineRegistry()
        self.models_root = Path(models_root)

    def check_local(self, engine_id: EngineID) -> bool:
        config = self.registry.get_config(engine_id)
        local_path = Path(config.local_path)
        return local_path.exists()

    def check_all_local(self) -> Dict[str, bool]:
        return {e.value: self.check_local(e) for e in EngineID}

    def pull_from_huggingface(self, engine_id: EngineID, token: Optional[str] = None) -> str:
        config = self.registry.get_config(engine_id)
        local_dir = Path(config.local_path).parent
        local_dir.mkdir(parents=True, exist_ok=True)
        command = f"huggingface-cli download {config.hf_repo} {config.model_filename} --local-dir {local_dir}"
        if token:
            command += f" --token {token}"
        return command

    def upload_to_gcs(self, engine_id: EngineID) -> str:
        config = self.registry.get_config(engine_id)
        return f"gsutil cp {config.local_path} {config.gcs_path}"

    def download_from_gcs(self, engine_id: EngineID) -> str:
        config = self.registry.get_config(engine_id)
        local_dir = Path(config.local_path).parent
        local_dir.mkdir(parents=True, exist_ok=True)
        return f"gsutil cp {config.gcs_path} {config.local_path}"

    def get_full_pipeline(self, engine_id: EngineID) -> Dict[str, str]:
        return {
            "step_1_pull": self.pull_from_huggingface(engine_id),
            "step_2_upload": self.upload_to_gcs(engine_id),
            "step_3_verify": f"gsutil ls -l {self.registry.get_config(engine_id).gcs_path}",
            "step_4_deploy": self.download_from_gcs(engine_id),
        }

    def get_all_pipelines(self) -> Dict[str, Dict[str, str]]:
        return {e.value: self.get_full_pipeline(e) for e in EngineID}

    def get_status_report(self) -> str:
        lines = ["S3M Weight Vault Status", "=" * 40]
        for engine_id in EngineID:
            config = self.registry.get_config(engine_id)
            local_exists = self.check_local(engine_id)
            status = "READY" if local_exists else "NOT DOWNLOADED"
            lines.append(f"{config.name} ({config.provider}): {status}")
            lines.append(f"  Local: {config.local_path}")
            lines.append(f"  GCS:   {config.gcs_path}")
            lines.append(f"  HF:    {config.hf_repo}")
        return "\n".join(lines)

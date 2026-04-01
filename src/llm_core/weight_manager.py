"""
S3M Weight Manager v2.0
Orchestrates model weight pulling, uploading, and verification.

Integrity logic is delegated to ModelRegistry as the single source of truth.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from .engine_registry import EngineID, EngineRegistry
from .model_registry import ModelRegistry

logger = logging.getLogger("s3m.weights")


class WeightManager:
    """
    Manage model weights with integrity verification delegation.

    Tactical context:
        Centralized integrity checks reduce divergent trust decisions across
        mission services that consume edge-hosted model artifacts.
    """

    def __init__(
        self,
        models_root: str = "models",
        registry: Optional[EngineRegistry] = None,
        model_registry: Optional[ModelRegistry] = None,
    ):
        self.registry = registry or EngineRegistry()
        self.model_registry = model_registry or ModelRegistry()
        self.models_root = Path(models_root)
        logger.info("WeightManager initialized with ModelRegistry integration")

    def check_local(self, engine_id: EngineID) -> bool:
        """
        Check if the model file exists on local disk.

        This does not perform cryptographic integrity checks.
        """
        config = self.registry.get_config(engine_id)
        exists = Path(config.local_path).exists()
        logger.debug("Local model presence check engine=%s exists=%s", engine_id.value, exists)
        return exists

    def check_all_local(self) -> Dict[str, bool]:
        """Check local availability for all configured engines."""
        return {engine_id.value: self.check_local(engine_id) for engine_id in EngineID}

    def verify_integrity(self, engine_id: EngineID) -> bool:
        """
        Verify artifact integrity via ModelRegistry.
        """
        is_clean, status, reason = self.model_registry.verify_artifact(engine_id)
        if not is_clean:
            logger.warning(
                "Integrity check failed engine=%s status=%s reason=%s",
                engine_id.value,
                status,
                reason,
            )
        return is_clean

    def verify_all_integrity(self) -> Dict[str, bool]:
        """Verify all registered artifacts and return pass/fail map."""
        return {engine_id.value: self.verify_integrity(engine_id) for engine_id in EngineID}

    def pull_from_huggingface(
        self,
        engine_id: EngineID,
        token: Optional[str] = None,
    ) -> str:
        """
        Generate shell command to pull a model from Hugging Face.

        Returns command string only; caller executes in controlled environment.
        """
        config = self.registry.get_config(engine_id)
        local_dir = Path(config.local_path).parent
        local_dir.mkdir(parents=True, exist_ok=True)

        command = (
            f"huggingface-cli download {config.hf_repo} "
            f"{config.model_filename} --local-dir {local_dir}"
        )
        if token:
            command += f" --token {token}"

        logger.info("Generated Hugging Face pull command for engine=%s", engine_id.value)
        return command

    def upload_to_gcs(self, engine_id: EngineID) -> str:
        """Generate shell command to upload local model to GCS."""
        config = self.registry.get_config(engine_id)
        command = f"gsutil cp {config.local_path} {config.gcs_path}"
        logger.info("Generated GCS upload command for engine=%s", engine_id.value)
        return command

    def download_from_gcs(self, engine_id: EngineID) -> str:
        """Generate shell command to download model from GCS."""
        config = self.registry.get_config(engine_id)
        local_dir = Path(config.local_path).parent
        local_dir.mkdir(parents=True, exist_ok=True)

        command = f"gsutil cp {config.gcs_path} {config.local_path}"
        logger.info("Generated GCS download command for engine=%s", engine_id.value)
        return command

    def get_full_pipeline(self, engine_id: EngineID) -> Dict[str, str]:
        """Return named command steps for pull/upload/verify/deploy flow."""
        return {
            "step_1_pull": self.pull_from_huggingface(engine_id),
            "step_2_upload": self.upload_to_gcs(engine_id),
            "step_3_verify": f"gsutil ls -l {self.registry.get_config(engine_id).gcs_path}",
            "step_4_download": self.download_from_gcs(engine_id),
            "step_5_check_integrity": (
                "# Use ModelRegistry to verify integrity:\n"
                f"# model_registry.verify_artifact(EngineID.{engine_id.name})"
            ),
        }

    def get_all_pipelines(self) -> Dict[str, Dict[str, str]]:
        """Return transfer pipelines for all engines."""
        return {engine_id.value: self.get_full_pipeline(engine_id) for engine_id in EngineID}

    def get_status_report(self) -> str:
        """
        Build comprehensive status including local and integrity states.
        """
        lines = ["S3M Weight Vault Status", "=" * 50]

        for engine_id in EngineID:
            config = self.registry.get_config(engine_id)
            local_exists = self.check_local(engine_id)

            artifact = self.model_registry.get_artifact(engine_id)
            if artifact is None:
                integrity_status = "UNREGISTERED"
                last_verified = "never"
            else:
                integrity_status = artifact.status
                last_verified = artifact.last_verified_at[:10]

            lines.append(f"\n{config.name} ({config.provider})")
            lines.append(f"  Local exists:  {local_exists}")
            lines.append(f"  Integrity:     {integrity_status}")
            lines.append(f"  Last verified: {last_verified}")
            lines.append(f"  Local path:    {config.local_path}")
            lines.append(f"  GCS path:      {config.gcs_path}")
            lines.append(f"  HF repo:       {config.hf_repo}")

        return "\n".join(lines)

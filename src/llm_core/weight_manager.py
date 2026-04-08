"""
S3M Weight Manager v2.0
Orchestrates model weight pulling, uploading, and verification.

Integrity logic is delegated to ModelRegistry as the single source of truth.
"""

import logging
from pathlib import Path
from typing import Dict, Optional
import yaml

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

        # Tactical logistics constants keep transfer and storage planning deterministic
        # during disconnected mission operations.
        self._engine_aliases = {
            "phi3_medium": {"PHI3", "PHI3_MEDIUM"},
            "grok1": {"GROK", "GROK1"},
            "mixtral": {"MISTRAL", "MIXTRAL"},
            "allam": {"ALLAM"},
        }
        self._hf_pull_commands = {
            "phi3_medium": (
                "huggingface-cli download microsoft/Phi-3-medium-4k-instruct "
                "--local-dir models/phi3-medium/"
            ),
            "grok1": (
                "huggingface-cli download xai-org/grok-1 --repo-type model "
                "--include 'ckpt-0/*' --local-dir models/grok1/"
            ),
            "mixtral": (
                "huggingface-cli download mistralai/Mixtral-8x7B-Instruct-v0.1 "
                "--local-dir models/mixtral/"
            ),
            "allam": (
                "huggingface-cli download humain-ai/ALLaM-7B-Instruct-preview "
                "--local-dir models/allam/"
            ),
        }
        self._quantized_pull_commands = {
            "phi3_medium": (
                "huggingface-cli download bartowski/Phi-3-medium-4k-instruct-GGUF "
                "Phi-3-medium-4k-instruct-Q4_K_M.gguf --local-dir models/phi3-medium/"
            ),
            "mixtral": (
                "huggingface-cli download TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF "
                "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf --local-dir models/mixtral/"
            ),
            "grok1": "No pre-quantized GGUF available. Must convert from fp16 checkpoints.",
            "allam": "No pre-quantized GGUF available. Must convert from fp16.",
        }
        self._storage_gb = {
            "phi3_medium": {"fp16_gb": 14.0, "q4_gb": 8.0},
            "grok1": {"fp16_gb": 650.0, "q4_gb": 360.0},
            "mixtral": {"fp16_gb": 90.0, "q4_gb": 24.0},
            "allam": {"fp16_gb": 14.0, "q4_gb": 8.0},
        }
        self._training_tier = {
            "phi3_medium": "gpu_required",
            "grok1": "multi_gpu",
            "mixtral": "multi_gpu",
            "allam": "gpu_required",
        }

    def _normalize_engine_key(self, engine_id: EngineID) -> str:
        """Map legacy/new enum names to canonical logistics engine keys."""
        enum_name = getattr(engine_id, "name", str(engine_id))
        for canonical, aliases in self._engine_aliases.items():
            if enum_name in aliases:
                return canonical
        raise ValueError(f"Unsupported engine id for weight operations: {enum_name}")

    def _is_vault_sync_configured(self, config_path: str = "configs/distributed_training.yaml") -> bool:
        """
        Check if vault synchronization is configured from distributed config.
        """
        path = Path(config_path)
        if not path.exists():
            return False

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return False

        section = data.get("distributed_training", data)
        vault = section.get("vault", {})
        vault_ip = section.get("vault_ip") or vault.get("ip")
        vault_base = section.get("vault_base_path") or vault.get("base_path")
        return bool(vault_ip and vault_base)

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
        engine_key = self._normalize_engine_key(engine_id)
        local_dir_map = {
            "phi3_medium": "models/phi3-medium",
            "grok1": "models/grok1",
            "mixtral": "models/mixtral",
            "allam": "models/allam",
        }
        local_dir = Path(local_dir_map[engine_key])
        local_dir.mkdir(parents=True, exist_ok=True)

        command = self._hf_pull_commands[engine_key]
        if token:
            command += f" --token {token}"

        logger.info("Generated Hugging Face pull command for engine=%s", engine_id.value)
        return command

    def pull_quantized_gguf(self, engine_id: EngineID) -> str:
        """
        Return command/message for pre-quantized GGUF acquisition.
        """
        engine_key = self._normalize_engine_key(engine_id)
        return self._quantized_pull_commands[engine_key]

    def get_storage_requirements(self) -> Dict[str, Dict[str, float]]:
        """
        Return per-engine fp16/q4 storage requirements in GB and totals.
        """
        per_engine: Dict[str, Dict[str, float]] = {}
        total_fp16 = 0.0
        total_q4 = 0.0

        for engine, sizes in self._storage_gb.items():
            fp16_gb = float(sizes["fp16_gb"])
            q4_gb = float(sizes["q4_gb"])
            per_engine[engine] = {"fp16_gb": fp16_gb, "q4_gb": q4_gb}
            total_fp16 += fp16_gb
            total_q4 += q4_gb

        per_engine["totals"] = {"fp16_gb": total_fp16, "q4_gb": total_q4}
        return per_engine

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
        storage = self.get_storage_requirements()
        vault_sync_configured = self._is_vault_sync_configured()

        for engine_id in EngineID:
            config = self.registry.get_config(engine_id)
            local_exists = self.check_local(engine_id)
            engine_key = self._normalize_engine_key(engine_id)

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
            lines.append(f"  FP16 size GB:  {storage[engine_key]['fp16_gb']}")
            lines.append(f"  Q4 size GB:    {storage[engine_key]['q4_gb']}")
            lines.append(f"  Training tier: {self._training_tier[engine_key]}")
            lines.append(f"  Vault sync:    {vault_sync_configured}")

        lines.append("\nStorage Totals")
        lines.append(f"  FP16 total GB: {storage['totals']['fp16_gb']}")
        lines.append(f"  Q4 total GB:   {storage['totals']['q4_gb']}")

        return "\n".join(lines)

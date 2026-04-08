"""
Distributed weight synchronization manager for the 3-tier training topology.

Tactical context:
    Reliable movement of base, quantized, and adapter artifacts between cloud
    and vault tiers preserves mission readiness when edge teams must rebuild
    local runtimes without internet dependency.
"""

import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict

import yaml

logger = logging.getLogger("s3m.distributed.sync")


class WeightSyncManager:
    """Programmatic synchronization of model weights across distributed tiers."""

    _ENGINE_ALIASES = {
        "phi3_medium": {"phi3", "phi3_medium", "phi3-medium", "PHI3", "PHI3_MEDIUM"},
        "grok1": {"grok", "grok1", "grok-1", "GROK", "GROK1"},
        "mixtral": {"mistral", "mixtral", "MISTRAL", "MIXTRAL"},
        "allam": {"allam", "ALLAM"},
    }
    _VALID_CONTENT = {"base", "quantized", "adapters"}
    _DEFAULT_VAULT_BASE = "/srv/s3m-weight-vault"

    _ENGINE_METADATA = {
        "phi3_medium": {
            "hf_pull": (
                "huggingface-cli download microsoft/Phi-3-medium-4k-instruct "
                "--local-dir models/phi3-medium/"
            ),
            "fp16_gb": 14.0,
        },
        "grok1": {
            "hf_pull": (
                "huggingface-cli download xai-org/grok-1 --repo-type model "
                "--include 'ckpt-0/*' --local-dir models/grok1/"
            ),
            "fp16_gb": 650.0,
        },
        "mixtral": {
            "hf_pull": (
                "huggingface-cli download mistralai/Mixtral-8x7B-Instruct-v0.1 "
                "--local-dir models/mixtral/"
            ),
            "fp16_gb": 90.0,
        },
        "allam": {
            "hf_pull": (
                "huggingface-cli download humain-ai/ALLaM-7B-Instruct-preview "
                "--local-dir models/allam/"
            ),
            "fp16_gb": 14.0,
        },
    }

    def __init__(self, config_path: str = "configs/distributed_training.yaml"):
        """
        Load distributed training config and cache primary sync settings.
        """
        self.config_path = Path(config_path)
        self.config = self._load_config(self.config_path)
        distributed = self.config.get("distributed_training", self.config)
        vault = distributed.get("vault", {})
        hosts = distributed.get("hosts", {})

        self.vault_ip = distributed.get("vault_ip") or vault.get("ip") or hosts.get("vault_ip") or ""
        self.hetzner_ip = distributed.get("hetzner_ip") or hosts.get("hetzner_ip") or ""
        self.vault_base_path = (
            distributed.get("vault_base_path")
            or vault.get("base_path")
            or self._DEFAULT_VAULT_BASE
        )
        self.vault_user = (
            distributed.get("vault_user")
            or vault.get("user")
            or distributed.get("ssh_user")
            or "ubuntu"
        )

    def _load_config(self, config_path: Path) -> Dict:
        if not config_path.exists():
            logger.warning("Distributed config not found: %s", config_path)
            return {}
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    def _canonical_engine(self, engine: str) -> str:
        if not isinstance(engine, str) or not engine.strip():
            raise ValueError("engine must be a non-empty string")
        raw = engine.strip()
        for canonical, aliases in self._ENGINE_ALIASES.items():
            if raw in aliases:
                return canonical
        raise ValueError(f"Unsupported engine identifier: {engine}")

    def _validate_content(self, content: str) -> str:
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        normalized = content.strip().lower()
        if normalized not in self._VALID_CONTENT:
            raise ValueError(f"content must be one of {sorted(self._VALID_CONTENT)}")
        return normalized

    def _safe_remote_path(self, *parts: str) -> str:
        candidate = str(Path(self.vault_base_path, *parts))
        if ".." in candidate:
            raise ValueError("remote path contains invalid traversal token")
        if not re.fullmatch(r"[A-Za-z0-9._/\-]+", candidate):
            raise ValueError("remote path contains unsupported characters")
        return candidate

    @staticmethod
    def _parse_bytes_transferred(stdout: str, stderr: str) -> int:
        payload = f"{stdout}\n{stderr}"
        patterns = [
            r"Total transferred file size:\s*([0-9,]+)\s*bytes",
            r"total size is\s*([0-9,]+)",
            r"sent\s*([0-9,]+)\s*bytes\s*received\s*([0-9,]+)\s*bytes",
        ]
        for pattern in patterns:
            match = re.search(pattern, payload, flags=re.IGNORECASE)
            if match:
                values = [int(group.replace(",", "")) for group in match.groups()]
                return sum(values)
        return 0

    def pull_from_vault(self, engine: str, target_dir: str, content: str = "base") -> dict:
        """
        Pull base/quantized/adapters for one engine from the vault tier.
        """
        engine_key = self._canonical_engine(engine)
        content_key = self._validate_content(content)
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        if not self.vault_ip:
            return {"status": "error", "engine": engine_key, "bytes_transferred": 0}

        remote_dir = self._safe_remote_path(engine_key, content_key)
        remote = f"{self.vault_user}@{self.vault_ip}:{remote_dir}/"
        cmd = ["rsync", "-az", "--stats", remote, f"{target_path}/"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            logger.error("Vault pull failed engine=%s stderr=%s", engine_key, result.stderr.strip())
            return {"status": "error", "engine": engine_key, "bytes_transferred": 0}

        transferred = self._parse_bytes_transferred(result.stdout, result.stderr)
        return {"status": "ok", "engine": engine_key, "bytes_transferred": int(transferred)}

    def push_to_vault(self, engine: str, source_dir: str, content: str = "adapters") -> dict:
        """
        Push trained adapter/quantized artifacts into the vault tier.
        """
        engine_key = self._canonical_engine(engine)
        content_key = self._validate_content(content)
        source_path = Path(source_dir)
        if not source_path.exists():
            return {"status": "error", "engine": engine_key, "bytes_transferred": 0}

        if not self.vault_ip:
            return {"status": "error", "engine": engine_key, "bytes_transferred": 0}

        remote_dir = self._safe_remote_path(engine_key, content_key)
        remote = f"{self.vault_user}@{self.vault_ip}:{remote_dir}/"
        cmd = ["rsync", "-az", "--stats", f"{source_path}/", remote]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            logger.error("Vault push failed engine=%s stderr=%s", engine_key, result.stderr.strip())
            return {"status": "error", "engine": engine_key, "bytes_transferred": 0}

        transferred = self._parse_bytes_transferred(result.stdout, result.stderr)
        return {"status": "ok", "engine": engine_key, "bytes_transferred": int(transferred)}

    def check_vault_status(self) -> dict:
        """
        Query remote vault disk usage and available engine directories.
        """
        if not self.vault_ip:
            return {"disk_used_gb": 0.0, "disk_free_gb": 0.0, "engines": {}}

        host = f"{self.vault_user}@{self.vault_ip}"
        quoted_base = shlex.quote(self.vault_base_path)
        disk_cmd = (
            f"df -BG {quoted_base} 2>/dev/null | awk 'NR==2 "
            "{gsub(\"G\",\"\",$3); gsub(\"G\",\"\",$4); print $3\" \"$4}'"
        )
        engines_cmd = f"ls -1 {quoted_base} 2>/dev/null || true"

        disk_result = subprocess.run(
            ["ssh", host, disk_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        engines_result = subprocess.run(
            ["ssh", host, engines_cmd],
            capture_output=True,
            text=True,
            check=False,
        )

        used = 0.0
        free = 0.0
        if disk_result.returncode == 0 and disk_result.stdout.strip():
            parts = disk_result.stdout.strip().split()
            if len(parts) >= 2:
                try:
                    used = float(parts[0])
                    free = float(parts[1])
                except ValueError:
                    logger.warning("Unable to parse vault disk usage output: %s", disk_result.stdout.strip())

        listed = {
            line.strip()
            for line in engines_result.stdout.splitlines()
            if line.strip()
        }
        engine_map = {
            engine: {"available": engine in listed}
            for engine in self._ENGINE_METADATA
        }
        return {"disk_used_gb": used, "disk_free_gb": free, "engines": engine_map}

    def get_engine_weight_status(self) -> dict:
        """
        Determine per-engine base/quantized/adapters availability on vault.
        """
        if not self.vault_ip:
            return {
                engine: {"base": False, "quantized": False, "adapters": False}
                for engine in self._ENGINE_METADATA
            }

        host = f"{self.vault_user}@{self.vault_ip}"
        status: Dict[str, Dict[str, bool]] = {}

        for engine in self._ENGINE_METADATA:
            status[engine] = {}
            for content in sorted(self._VALID_CONTENT):
                remote_dir = self._safe_remote_path(engine, content)
                cmd = f"test -d {shlex.quote(remote_dir)} && echo 1 || echo 0"
                result = subprocess.run(
                    ["ssh", host, cmd],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                status[engine][content] = result.returncode == 0 and result.stdout.strip() == "1"

        return status

    def generate_pull_commands(self) -> dict:
        """
        Return Hugging Face pull commands for all engines.
        """
        return {engine: metadata["hf_pull"] for engine, metadata in self._ENGINE_METADATA.items()}

    def estimate_download_time(self, bandwidth_mbps: float = 100) -> dict:
        """
        Estimate fp16 download durations for each engine at given bandwidth.
        """
        if bandwidth_mbps <= 0:
            raise ValueError("bandwidth_mbps must be positive")

        estimates = {}
        total_seconds = 0.0
        for engine, metadata in self._ENGINE_METADATA.items():
            fp16_gb = float(metadata["fp16_gb"])
            total_bits = fp16_gb * (1024 ** 3) * 8
            seconds = total_bits / (bandwidth_mbps * 1_000_000)
            total_seconds += seconds
            estimates[engine] = {
                "fp16_gb": fp16_gb,
                "estimated_minutes": round(seconds / 60.0, 2),
                "estimated_hours": round(seconds / 3600.0, 2),
            }

        estimates["totals"] = {
            "estimated_minutes": round(total_seconds / 60.0, 2),
            "estimated_hours": round(total_seconds / 3600.0, 2),
        }
        return estimates

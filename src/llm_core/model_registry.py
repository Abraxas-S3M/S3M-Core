"""
S3M Model Registry
Tracks model artifact integrity for offline tactical deployments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
from typing import Dict, Optional

from .engine_registry import EngineID, EngineRegistry


STALE_VERIFICATION_DAYS = 7


@dataclass
class ModelArtifact:
    """Integrity record for one edge model artifact."""

    engine_id: EngineID
    local_path: str
    version_tag: str = "v1.0.0"
    expected_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None
    status: str = "UNKNOWN"
    drift_reason: Optional[str] = None
    last_verified_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    exists: bool = False

    def age_since_verification_days(self) -> int:
        """Return age in days for maintenance and drift governance."""
        try:
            verified = datetime.fromisoformat(self.last_verified_at)
        except Exception:
            return 0
        delta = datetime.utcnow() - verified
        return max(0, int(delta.total_seconds() // 86400))


@dataclass
class RegistryStatus:
    """Aggregate status for all model artifacts in the registry."""

    artifacts: Dict[str, ModelArtifact]
    total_artifacts: int
    clean_artifacts: int
    missing_artifacts: int
    mismatched_artifacts: int
    stale_artifacts: int
    review_required: bool

    def summary(self) -> str:
        """Compact summary for operator dashboards."""
        if self.review_required:
            return (
                f"REVIEW required: clean={self.clean_artifacts} "
                f"missing={self.missing_artifacts} mismatched={self.mismatched_artifacts} "
                f"stale={self.stale_artifacts}"
            )
        return f"HEALTHY: clean={self.clean_artifacts}/{self.total_artifacts}"


class ModelRegistry:
    """
    Offline model integrity registry.

    Tactical context:
    Verification is local-only and deterministic so operators can trust drift
    decisions without external network dependencies.
    """

    def __init__(self, registry: Optional[EngineRegistry] = None) -> None:
        self.registry = registry or EngineRegistry()
        self._artifacts: Dict[EngineID, ModelArtifact] = {}
        self._last_status: Optional[RegistryStatus] = None
        self._initialize_artifacts()

    def _initialize_artifacts(self) -> None:
        for engine_id in EngineID:
            config = self.registry.get_config(engine_id)
            self._artifacts[engine_id] = ModelArtifact(
                engine_id=engine_id,
                local_path=config.local_path,
                version_tag=config.version_tag or "v1.0.0",
                expected_sha256=config.sha256_hash,
                status="UNKNOWN",
            )

    def get_artifact(self, engine_id: EngineID) -> Optional[ModelArtifact]:
        """Return artifact by engine ID."""
        return self._artifacts.get(engine_id)

    def verify_artifact(self, engine_id: EngineID) -> ModelArtifact:
        """Verify one artifact and update cached state."""
        artifact = self._artifacts[engine_id]
        path = Path(artifact.local_path)
        artifact.last_verified_at = datetime.utcnow().isoformat()

        if not path.exists():
            artifact.exists = False
            artifact.actual_sha256 = None
            artifact.status = "MISSING"
            artifact.drift_reason = "Model file not found"
            return artifact

        artifact.exists = True
        artifact.actual_sha256 = self._compute_sha256(path)
        if artifact.expected_sha256 and artifact.actual_sha256 != artifact.expected_sha256:
            artifact.status = "MISMATCHED"
            artifact.drift_reason = "SHA256 hash mismatch"
            return artifact

        artifact.status = "CLEAN"
        artifact.drift_reason = None
        return artifact

    def list_registry_status(self, recompute: bool = False) -> RegistryStatus:
        """
        Return registry-wide integrity status.

        Tactical context:
        A stale verification is treated as degraded posture, ensuring operators
        are alerted before old integrity assumptions drive mission decisions.
        """
        if self._last_status is not None and not recompute:
            return self._last_status

        artifacts: Dict[str, ModelArtifact] = {}
        clean = missing = mismatched = stale = 0
        now = datetime.utcnow()
        stale_cutoff = now - timedelta(days=STALE_VERIFICATION_DAYS)

        for engine_id in EngineID:
            artifact = self.verify_artifact(engine_id)
            if artifact.status == "CLEAN":
                try:
                    verified_at = datetime.fromisoformat(artifact.last_verified_at)
                    if verified_at < stale_cutoff:
                        artifact.status = "STALE"
                        artifact.drift_reason = "Verification is older than policy window"
                except Exception:
                    artifact.status = "STALE"
                    artifact.drift_reason = "Invalid verification timestamp"

            if artifact.status == "CLEAN":
                clean += 1
            elif artifact.status == "MISSING":
                missing += 1
            elif artifact.status == "MISMATCHED":
                mismatched += 1
            elif artifact.status == "STALE":
                stale += 1

            artifacts[engine_id.value] = artifact

        total = len(artifacts)
        status = RegistryStatus(
            artifacts=artifacts,
            total_artifacts=total,
            clean_artifacts=clean,
            missing_artifacts=missing,
            mismatched_artifacts=mismatched,
            stale_artifacts=stale,
            review_required=(missing > 0 or mismatched > 0 or stale > 0),
        )
        self._last_status = status
        return status

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

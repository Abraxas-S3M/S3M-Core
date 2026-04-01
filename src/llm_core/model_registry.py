"""
S3M Model Registry v1.0
Integrity verification and drift detection via SHA256 hashing.

Mission context:
    This registry protects deployed tactical AI assets by continuously
    validating model artifacts on edge storage. Any drift, corruption, or
    untracked model swap is surfaced for operator review before mission use.

Answers:
  - Has a model changed since deployment?
  - Are model files still present and untampered?
  - Is verification stale relative to tactical assurance policy?
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from .engine_registry import EngineID, EngineRegistry


logger = logging.getLogger("s3m.registry")


# Configuration constants.
REGISTRY_FILE = "data/model_registry.json"
CHUNK_SIZE = 8192
STALE_THRESHOLD_DAYS = 30
VERSION_SEPARATOR = "."
TIMESTAMP_FORMAT_NOTE = "ISO-8601 UTC naive datetime string"

# Status constants.
STATUS_CLEAN = "CLEAN"
STATUS_MISSING = "MISSING"
STATUS_MISMATCH = "MISMATCH"
STATUS_STALE = "STALE"
STATUS_UNREGISTERED = "UNREGISTERED"

# Registry schema constants.
REGISTRY_SCHEMA_VERSION = 1


@dataclass
class ModelArtifact:
    """
    Single model artifact record (one engine -> one active model file).

    All timestamps are serialized as ISO strings for deterministic JSON storage.
    """

    engine_id: str
    model_filename: str
    local_path: str
    sha256_hash: str
    file_size_bytes: int
    registered_at: str
    last_verified_at: str
    version_tag: str
    status: str
    drift_reason: Optional[str] = None

    def is_clean(self) -> bool:
        """Return True when artifact integrity is mission-ready."""
        return self.status == STATUS_CLEAN

    def is_stale(self, days_threshold: int = STALE_THRESHOLD_DAYS) -> bool:
        """
        Return True if last verification exceeds tactical assurance threshold.

        If timestamp parsing fails, default to stale for security-first posture.
        """
        last_check = _safe_parse_iso(self.last_verified_at)
        if last_check is None:
            return True
        return (datetime.utcnow() - last_check).days > days_threshold

    def age_since_verification_days(self) -> int:
        """Return verification age in days; large sentinel value on parse failure."""
        last_check = _safe_parse_iso(self.last_verified_at)
        if last_check is None:
            return 9999
        return (datetime.utcnow() - last_check).days

    def to_dict(self) -> Dict[str, object]:
        """Serialize to a JSON-safe dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "ModelArtifact":
        """Build artifact from deserialized JSON payload."""
        return cls(
            engine_id=str(payload.get("engine_id", "")),
            model_filename=str(payload.get("model_filename", "")),
            local_path=str(payload.get("local_path", "")),
            sha256_hash=str(payload.get("sha256_hash", "")),
            file_size_bytes=int(payload.get("file_size_bytes", 0)),
            registered_at=str(payload.get("registered_at", "")),
            last_verified_at=str(payload.get("last_verified_at", "")),
            version_tag=str(payload.get("version_tag", "v1.0.0")),
            status=str(payload.get("status", STATUS_UNREGISTERED)),
            drift_reason=payload.get("drift_reason")
            if payload.get("drift_reason") is None
            else str(payload.get("drift_reason")),
        )

    def refresh_integrity_snapshot(self, *, status: str, drift_reason: Optional[str]) -> None:
        """
        Update in-memory state after an integrity pass.

        Tactical context:
            Keeping status and rationale together improves review traceability
            for post-mission forensic timelines.
        """
        self.status = status
        self.drift_reason = drift_reason


@dataclass
class RegistryStatus:
    """Aggregated health snapshot for all tracked model artifacts."""

    total_artifacts: int
    clean_artifacts: int
    missing_artifacts: int
    mismatched_artifacts: int
    stale_artifacts: int
    review_required: bool
    artifacts: Dict[str, ModelArtifact]
    timestamp: str

    def summary(self) -> str:
        """Return human-readable registry summary."""
        lines = [
            f"Registry Status @ {self.timestamp}",
            f"{'-' * 40}",
            f"Total artifacts:     {self.total_artifacts}",
            f"Clean:               {self.clean_artifacts}",
            f"Missing:             {self.missing_artifacts}",
            f"Mismatched:          {self.mismatched_artifacts}",
            f"Stale:               {self.stale_artifacts}",
            f"Review required:     {self.review_required}",
        ]
        return "\n".join(lines)

    def has_issues(self) -> bool:
        """Return True when any integrity issue requires operator review."""
        return self.review_required


class ModelRegistry:
    """
    Content-addressable model registry with drift detection.

    Responsibilities:
      1) Register model artifacts with SHA256 metadata.
      2) Persist metadata to local JSON for deterministic edge recovery.
      3) Verify artifact existence + integrity.
      4) Detect stale verification windows.
      5) Provide mission-friendly status rollups.
    """

    def __init__(
        self,
        registry_file: str = REGISTRY_FILE,
        registry: Optional[EngineRegistry] = None,
    ):
        self.registry_file = Path(registry_file)
        self.registry = registry or EngineRegistry()
        self.artifacts: Dict[str, ModelArtifact] = {}

        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_registry()
        logger.info("ModelRegistry initialized with %s artifacts", len(self.artifacts))

    # ---------------------------------------------------------------------
    # PRIMARY API
    # ---------------------------------------------------------------------
    def register_artifact(
        self,
        engine_id: EngineID,
        local_path: str,
        source: str = "deployment",
    ) -> ModelArtifact:
        """
        Register a model artifact and persist its integrity baseline.

        The optional `source` tag is currently logged for tactical audit trails
        and future provenance reporting.
        """
        self._validate_engine_id(engine_id)
        path = Path(local_path)
        self._validate_local_file(path)

        # Ensure engine exists in registry; result is used for validation only.
        self.registry.get_config(engine_id)

        file_hash = self.compute_sha256(str(path))
        file_size = path.stat().st_size
        version_tag = self._generate_version_tag(engine_id)
        now = datetime.utcnow().isoformat()

        artifact = ModelArtifact(
            engine_id=engine_id.value,
            model_filename=path.name,
            local_path=str(path),
            sha256_hash=file_hash,
            file_size_bytes=file_size,
            registered_at=now,
            last_verified_at=now,
            version_tag=version_tag,
            status=STATUS_CLEAN,
            drift_reason=None,
        )
        self.artifacts[engine_id.value] = artifact
        self._save_registry()

        logger.info(
            "Registered artifact engine=%s version=%s size=%s source=%s hash_prefix=%s",
            engine_id.value,
            version_tag,
            file_size,
            source,
            file_hash[:16],
        )
        return artifact

    def compute_sha256(self, file_path: str) -> str:
        """
        Compute SHA256 for file bytes using streaming reads.

        Tactical context:
            Streaming avoids memory spikes on large quantized model files used
            on constrained edge hardware.
        """
        path = Path(file_path)
        self._validate_local_file(path)

        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    def verify_artifact(
        self,
        engine_id: EngineID,
        recompute: bool = False,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Verify one artifact and update persisted status.

        Returns:
            (is_clean, status, reason)
        """
        self._validate_engine_id(engine_id)
        engine_key = engine_id.value
        artifact = self.artifacts.get(engine_key)

        if artifact is None:
            return False, STATUS_UNREGISTERED, "Artifact not in registry"

        artifact_path = Path(artifact.local_path)
        if not artifact_path.exists():
            reason = f"File not found: {artifact.local_path}"
            artifact.refresh_integrity_snapshot(status=STATUS_MISSING, drift_reason=reason)
            self._save_registry()
            logger.warning("Artifact missing for engine=%s", engine_key)
            return False, STATUS_MISSING, reason

        if recompute:
            try:
                current_hash = self.compute_sha256(artifact.local_path)
            except Exception as exc:  # pragma: no cover - defensive IO branch
                reason = f"Error reading file: {exc}"
                artifact.refresh_integrity_snapshot(status=STATUS_MISSING, drift_reason=reason)
                self._save_registry()
                logger.error("Error reading artifact engine=%s err=%s", engine_key, exc)
                return False, STATUS_MISSING, reason
        else:
            current_hash = artifact.sha256_hash

        if current_hash != artifact.sha256_hash:
            reason = (
                f"Hash mismatch: expected {artifact.sha256_hash[:16]}..., "
                f"got {current_hash[:16]}..."
            )
            artifact.refresh_integrity_snapshot(status=STATUS_MISMATCH, drift_reason=reason)
            self._save_registry()
            logger.warning("Artifact hash mismatch for engine=%s", engine_key)
            return False, STATUS_MISMATCH, reason

        if artifact.is_stale():
            age_days = artifact.age_since_verification_days()
            reason = f"Last verified {age_days} days ago"
            artifact.refresh_integrity_snapshot(status=STATUS_STALE, drift_reason=reason)
            self._save_registry()
            logger.warning("Artifact stale for engine=%s age_days=%s", engine_key, age_days)
            return False, STATUS_STALE, reason

        artifact.last_verified_at = datetime.utcnow().isoformat()
        artifact.refresh_integrity_snapshot(status=STATUS_CLEAN, drift_reason=None)
        self._save_registry()
        logger.debug("Artifact clean for engine=%s", engine_key)
        return True, STATUS_CLEAN, None

    def detect_drift(
        self,
        engine_id: EngineID,
        recompute: bool = True,
    ) -> Optional[str]:
        """
        Return drift reason when artifact is not clean, else None.
        """
        is_clean, _, reason = self.verify_artifact(engine_id=engine_id, recompute=recompute)
        return None if is_clean else reason

    def list_registry_status(self, recompute: bool = False) -> RegistryStatus:
        """
        Return status snapshot across tracked artifacts.

        Only registered artifacts are counted in totals.
        """
        clean = 0
        missing = 0
        mismatched = 0
        stale = 0

        for engine_key in list(self.artifacts.keys()):
            maybe_engine = _engine_id_from_value(engine_key)
            if maybe_engine is None:
                # Unknown engine entries are retained for forensic continuity
                # but counted as mismatched review-required artifacts.
                mismatched += 1
                artifact = self.artifacts[engine_key]
                artifact.refresh_integrity_snapshot(
                    status=STATUS_MISMATCH,
                    drift_reason="Unknown engine id in registry entry",
                )
                continue

            is_clean, status, _ = self.verify_artifact(maybe_engine, recompute=recompute)
            if is_clean:
                clean += 1
            elif status == STATUS_MISSING:
                missing += 1
            elif status == STATUS_MISMATCH:
                mismatched += 1
            elif status == STATUS_STALE:
                stale += 1
            elif status == STATUS_UNREGISTERED:
                # Not expected here because we iterate artifacts, keep defensive.
                mismatched += 1

        total = len(self.artifacts)
        review_required = any([missing > 0, mismatched > 0, stale > 0])
        snapshot = RegistryStatus(
            total_artifacts=total,
            clean_artifacts=clean,
            missing_artifacts=missing,
            mismatched_artifacts=mismatched,
            stale_artifacts=stale,
            review_required=review_required,
            artifacts=dict(self.artifacts),
            timestamp=datetime.utcnow().isoformat(),
        )
        logger.info(
            "Registry snapshot clean=%s total=%s review_required=%s",
            clean,
            total,
            review_required,
        )
        return snapshot

    def get_artifact(self, engine_id: EngineID) -> Optional[ModelArtifact]:
        """Return artifact by engine id."""
        self._validate_engine_id(engine_id)
        return self.artifacts.get(engine_id.value)

    def list_artifacts(self) -> Dict[str, ModelArtifact]:
        """Return a copy of all artifacts for read-only callers."""
        return dict(self.artifacts)

    def clear_registry(self) -> None:
        """Clear registry records (primarily used by tests)."""
        self.artifacts.clear()
        self._save_registry()
        logger.info("Model registry cleared")

    def remove_artifact(self, engine_id: EngineID) -> bool:
        """Remove a registered artifact entry for one engine."""
        self._validate_engine_id(engine_id)
        removed = self.artifacts.pop(engine_id.value, None) is not None
        if removed:
            self._save_registry()
            logger.info("Removed artifact for engine=%s", engine_id.value)
        return removed

    def mark_verified_now(self, engine_id: EngineID) -> bool:
        """
        Mark artifact as just verified without recomputing hash.

        Tactical context:
            Useful when external attestation completed elsewhere and we only
            need to refresh staleness bookkeeping in this registry.
        """
        self._validate_engine_id(engine_id)
        artifact = self.artifacts.get(engine_id.value)
        if artifact is None:
            return False
        artifact.last_verified_at = datetime.utcnow().isoformat()
        if artifact.status == STATUS_STALE:
            artifact.refresh_integrity_snapshot(status=STATUS_CLEAN, drift_reason=None)
        self._save_registry()
        return True

    def ensure_registered_for_existing_models(self) -> Dict[str, str]:
        """
        Register all engine models that currently exist on disk.

        Returns:
            Mapping of engine_id -> result ("registered"|"already_registered"|"missing").
        """
        outcomes: Dict[str, str] = {}
        for engine_id in EngineID:
            if engine_id.value in self.artifacts:
                outcomes[engine_id.value] = "already_registered"
                continue

            config = self.registry.get_config(engine_id)
            model_path = Path(config.local_path)
            if not model_path.exists():
                outcomes[engine_id.value] = "missing"
                continue

            self.register_artifact(engine_id, str(model_path), source="discovered_local")
            outcomes[engine_id.value] = "registered"
        return outcomes

    # ---------------------------------------------------------------------
    # PRIVATE METHODS
    # ---------------------------------------------------------------------
    def _load_registry(self) -> None:
        """Load registry from JSON if present and parse schema variants safely."""
        if not self.registry_file.exists():
            self.artifacts = {}
            return

        try:
            data = json.loads(self.registry_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed loading registry JSON: %s", exc)
            self.artifacts = {}
            return

        parsed_artifacts: Dict[str, ModelArtifact] = {}

        if isinstance(data, dict) and "artifacts" in data:
            artifacts_payload = data.get("artifacts", {})
            schema_version = data.get("schema_version", REGISTRY_SCHEMA_VERSION)
            if schema_version != REGISTRY_SCHEMA_VERSION:
                logger.warning("Loading registry with schema_version=%s", schema_version)
        else:
            artifacts_payload = data

        if not isinstance(artifacts_payload, dict):
            logger.error("Registry artifact payload is not a dictionary")
            self.artifacts = {}
            return

        for engine_key, artifact_payload in artifacts_payload.items():
            if not isinstance(artifact_payload, dict):
                logger.warning("Skipping malformed artifact payload for engine=%s", engine_key)
                continue
            try:
                artifact = ModelArtifact.from_dict(artifact_payload)
                if not artifact.engine_id:
                    artifact.engine_id = str(engine_key)
                parsed_artifacts[str(engine_key)] = artifact
            except Exception as exc:
                logger.warning("Skipping invalid artifact engine=%s err=%s", engine_key, exc)

        self.artifacts = parsed_artifacts
        logger.info("Loaded model registry entries=%s", len(self.artifacts))

    def _save_registry(self) -> None:
        """Persist registry to disk as deterministic JSON."""
        payload = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "generated_at": datetime.utcnow().isoformat(),
            "artifacts": {
                engine_key: artifact.to_dict()
                for engine_key, artifact in sorted(self.artifacts.items(), key=lambda kv: kv[0])
            },
        }
        try:
            self.registry_file.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed saving model registry: %s", exc)

    def _generate_version_tag(self, engine_id: EngineID) -> str:
        """Generate next semantic version tag by incrementing patch component."""
        current = self.artifacts.get(engine_id.value)
        if current is None:
            return "v1.0.0"

        parsed = _parse_version_tag(current.version_tag)
        if parsed is None:
            return "v1.0.0"
        major, minor, patch = parsed
        return f"v{major}{VERSION_SEPARATOR}{minor}{VERSION_SEPARATOR}{patch + 1}"

    def _validate_engine_id(self, engine_id: EngineID) -> None:
        if not isinstance(engine_id, EngineID):
            raise TypeError(f"Expected EngineID, got {type(engine_id)!r}")

    @staticmethod
    def _validate_local_file(path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Path is not a file: {path}")

    # ---------------------------------------------------------------------
    # OPTIONAL ANALYTICS HELPERS
    # ---------------------------------------------------------------------
    def count_by_status(self) -> Dict[str, int]:
        """Return status histogram for dashboard-style summaries."""
        histogram = {
            STATUS_CLEAN: 0,
            STATUS_MISSING: 0,
            STATUS_MISMATCH: 0,
            STATUS_STALE: 0,
            STATUS_UNREGISTERED: 0,
        }
        for artifact in self.artifacts.values():
            histogram.setdefault(artifact.status, 0)
            histogram[artifact.status] += 1
        return histogram

    def get_review_required_engines(self) -> Dict[str, str]:
        """
        Return engines requiring review and their reasons.
        """
        flagged: Dict[str, str] = {}
        for engine_key, artifact in self.artifacts.items():
            if artifact.status != STATUS_CLEAN:
                flagged[engine_key] = artifact.drift_reason or "unspecified drift reason"
        return flagged

    def iter_artifacts(self) -> Iterable[Tuple[str, ModelArtifact]]:
        """Yield artifact entries in deterministic engine-key order."""
        for engine_key in sorted(self.artifacts.keys()):
            yield engine_key, self.artifacts[engine_key]

    def set_artifact_status(
        self,
        engine_id: EngineID,
        status: str,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Administrative helper to force status updates (mainly test and tooling use).
        """
        self._validate_engine_id(engine_id)
        artifact = self.artifacts.get(engine_id.value)
        if artifact is None:
            return False
        artifact.refresh_integrity_snapshot(status=status, drift_reason=reason)
        self._save_registry()
        return True


def _safe_parse_iso(value: str) -> Optional[datetime]:
    """Best-effort ISO parser; returns None on invalid values."""
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _parse_version_tag(version_tag: str) -> Optional[Tuple[int, int, int]]:
    """Parse `vX.Y.Z` version tags."""
    if not version_tag:
        return None
    raw = version_tag.strip().lstrip("v")
    parts = raw.split(VERSION_SEPARATOR)
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _engine_id_from_value(value: str) -> Optional[EngineID]:
    """Map string engine id to EngineID enum, returning None for unknown values."""
    for engine_id in EngineID:
        if engine_id.value == value:
            return engine_id
    return None


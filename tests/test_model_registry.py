"""Tests for model registry integrity verification and drift detection."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from src.llm_core.engine_registry import EngineID
from src.llm_core.model_registry import ModelRegistry


class TestModelRegistry:
    """Test model registry and drift detection."""

    @pytest.fixture
    def temp_registry(self, tmp_path):
        """Temporary registry for testing."""
        registry_file = tmp_path / "registry.json"
        return ModelRegistry(str(registry_file))

    @pytest.fixture
    def temp_model_file(self, tmp_path):
        """Create a temporary model file."""
        model_dir = tmp_path / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_file = model_dir / "test-model.gguf"
        model_file.write_bytes(b"fake model data")
        return str(model_file)

    def test_compute_sha256(self, temp_registry, temp_model_file):
        """SHA256 computation works."""
        hash1 = temp_registry.compute_sha256(temp_model_file)
        hash2 = temp_registry.compute_sha256(temp_model_file)

        assert hash1 == hash2
        assert len(hash1) == 64
        assert hash1.islower()

    def test_register_artifact(self, temp_registry, temp_model_file):
        """Artifact registration works."""
        artifact = temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)

        assert artifact.engine_id == "phi3-medium"
        assert artifact.status == "CLEAN"
        assert artifact.version_tag == "v1.0.0"
        assert artifact.sha256_hash

    def test_verify_clean_artifact(self, temp_registry, temp_model_file):
        """Clean artifact verifies successfully."""
        temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)

        is_clean, status, reason = temp_registry.verify_artifact(EngineID.PHI3_MEDIUM)
        assert is_clean is True
        assert status == "CLEAN"
        assert reason is None

    def test_detect_missing_file(self, temp_registry, temp_model_file):
        """Missing file detected."""
        artifact = temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)
        Path(artifact.local_path).unlink()

        is_clean, status, reason = temp_registry.verify_artifact(EngineID.PHI3_MEDIUM)
        assert is_clean is False
        assert status == "MISSING"
        assert reason is not None
        assert "not found" in reason.lower()

    def test_detect_hash_mismatch(self, temp_registry, temp_model_file):
        """Hash mismatch detected."""
        temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)
        Path(temp_model_file).write_bytes(b"different data")

        is_clean, status, reason = temp_registry.verify_artifact(
            EngineID.PHI3_MEDIUM,
            recompute=True,
        )
        assert is_clean is False
        assert status == "MISMATCH"
        assert reason is not None
        assert "mismatch" in reason.lower()

    def test_stale_verification(self, temp_registry, temp_model_file):
        """Stale verification detected."""
        artifact = temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)

        old_time = (datetime.utcnow() - timedelta(days=35)).isoformat()
        artifact.last_verified_at = old_time
        temp_registry.artifacts["phi3-medium"] = artifact
        temp_registry._save_registry()

        is_clean, status, reason = temp_registry.verify_artifact(EngineID.PHI3_MEDIUM)
        assert is_clean is False
        assert status == "STALE"
        assert reason is not None
        assert "days ago" in reason.lower()

    def test_registry_status(self, temp_registry, temp_model_file):
        """Registry status calculation."""
        temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)

        status = temp_registry.list_registry_status()
        assert status.total_artifacts == 1
        assert status.clean_artifacts == 1
        assert status.review_required is False

    def test_version_increment(self, temp_registry, temp_model_file):
        """Version tags increment."""
        artifact1 = temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)
        assert artifact1.version_tag == "v1.0.0"

        Path(temp_model_file).write_bytes(b"new data")
        artifact2 = temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)
        assert artifact2.version_tag == "v1.0.1"

    def test_drift_detection(self, temp_registry, temp_model_file):
        """Drift detection works."""
        temp_registry.register_artifact(EngineID.PHI3_MEDIUM, temp_model_file)

        drift1 = temp_registry.detect_drift(EngineID.PHI3_MEDIUM)
        assert drift1 is None

        Path(temp_model_file).write_bytes(b"modified")
        drift2 = temp_registry.detect_drift(EngineID.PHI3_MEDIUM, recompute=True)
        assert drift2 is not None

    def test_unregistered_artifact(self, temp_registry):
        """Unregistered artifact detection."""
        is_clean, status, reason = temp_registry.verify_artifact(EngineID.GROK1)
        assert is_clean is False
        assert status == "UNREGISTERED"
        assert reason is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

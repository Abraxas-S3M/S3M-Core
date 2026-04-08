from pathlib import Path

from src.security.model_scanner import ModelScanner
from src.security.model_trust import ModelTrustManager


def test_scan_model_integrity_flags_missing_model():
    scanner = ModelScanner()
    result = scanner.scan_model_integrity("models/does-not-exist.gguf")
    assert result["clean"] is False
    assert "model_file_missing" in result["issues"]


def test_scan_model_integrity_records_trust_state(tmp_path: Path):
    model_path = tmp_path / "test-model.gguf"
    model_path.write_bytes(b"test-model-weights")

    manager = ModelTrustManager()
    scanner = ModelScanner(trust_manager=manager)
    result = scanner.scan_model_integrity(str(model_path))
    assert "clean" in result

    trust = manager.get_trust_status()
    assert "engines" in trust
    assert "test-model" in trust["engines"]


def test_probe_llm_vulnerabilities_updates_trust_status():
    manager = ModelTrustManager()
    scanner = ModelScanner(trust_manager=manager)
    result = scanner.probe_llm_vulnerabilities("phi3")

    assert "vulnerabilities" in result
    assert "score" in result
    assert 0 <= result["score"] <= 100

    trust = manager.get_trust_status()
    assert "phi3" in trust["engines"]
    assert "vulnerabilities" in trust["engines"]["phi3"]


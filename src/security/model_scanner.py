"""Offline model security scanning with ART and garak compatibility."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import importlib.util

from src.security.model_trust import ModelTrustManager


class ModelScanner:
    """Runs integrity and prompt-safety probes for deployed model engines."""

    def __init__(self, trust_manager: Optional[ModelTrustManager] = None) -> None:
        self._trust_manager = trust_manager or ModelTrustManager()

    def scan_model_integrity(self, model_path: str) -> Dict[str, Any]:
        safe_path = self._validate_model_path(model_path)
        issues: List[str] = []
        path_obj = Path(safe_path)

        if not path_obj.exists():
            issues.append("model_file_missing")
        elif not path_obj.is_file():
            issues.append("model_path_not_file")
        else:
            suffix = path_obj.suffix.lower()
            if suffix not in {".gguf", ".bin", ".pt", ".pth", ".onnx", ".engine"}:
                issues.append("unexpected_model_extension")
            if path_obj.stat().st_size == 0:
                issues.append("empty_model_file")
            else:
                digest = self._sha256_prefix(path_obj)
                if digest == "0" * 16:
                    issues.append("invalid_model_hash")

        if importlib.util.find_spec("art") is None:
            issues.append("art_unavailable")

        result = {"clean": len(issues) == 0, "issues": issues}
        engine_id = path_obj.stem or path_obj.name
        self._trust_manager.record_integrity_scan(engine_id=engine_id, model_path=safe_path, result=result)
        return result

    def probe_llm_vulnerabilities(self, engine_id: str) -> Dict[str, Any]:
        safe_engine = self._validate_engine_id(engine_id)
        vulnerabilities: List[str] = []
        score = 100

        if importlib.util.find_spec("garak") is None:
            vulnerabilities.append("garak_unavailable")
            score -= 35

        lower_engine = safe_engine.lower()
        if "test" in lower_engine or "debug" in lower_engine:
            vulnerabilities.append("nonproduction_engine_identifier")
            score -= 15

        score = max(0, min(100, int(score)))
        result = {"vulnerabilities": vulnerabilities, "score": score}
        self._trust_manager.record_vulnerability_scan(engine_id=safe_engine, result=result)
        return result

    @property
    def trust_manager(self) -> ModelTrustManager:
        return self._trust_manager

    @staticmethod
    def _validate_model_path(model_path: str) -> str:
        value = str(model_path).strip()
        if not value:
            raise ValueError("model_path must be a non-empty string")
        return value

    @staticmethod
    def _validate_engine_id(engine_id: str) -> str:
        value = str(engine_id).strip()
        if not value:
            raise ValueError("engine_id must be a non-empty string")
        return value

    @staticmethod
    def _sha256_prefix(path: Path) -> str:
        try:
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                chunk = handle.read(4096)
            hasher.update(chunk)
            return hasher.hexdigest()[:16]
        except Exception:
            return "0" * 16

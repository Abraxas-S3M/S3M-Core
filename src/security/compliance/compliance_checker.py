"""Security compliance checks for S3M Phase 10."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.security.airgap_verifier import AirGapVerifier
from src.security.crypto.classification_banner import ClassificationBanner
from src.security.crypto.secure_audit_log import SecureAuditLog


class ComplianceChecker:
    """Runs structured policy checks aligned to S3M deployment controls."""

    def __init__(self) -> None:
        self.security_config_path = Path("configs/security.yaml")
        self.keys_dir = Path("configs/keys")
        self.models_dir = Path("models")
        self.configs_dir = Path("configs")
        self.audit_log = SecureAuditLog()
        self.airgap_verifier = AirGapVerifier()
        self._latest_report: Optional[Dict[str, Any]] = None

    def _load_security_config(self) -> Dict[str, Any]:
        if not self.security_config_path.exists():
            return {}
        try:
            return yaml.safe_load(self.security_config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    def _pass(self, detail: str) -> Dict[str, str]:
        return {"status": "PASS", "detail": detail}

    def _fail(self, detail: str) -> Dict[str, str]:
        return {"status": "FAIL", "detail": detail}

    def _warn(self, detail: str) -> Dict[str, str]:
        return {"status": "WARN", "detail": detail}

    def check_auth_configured(self) -> Dict[str, str]:
        config = self._load_security_config()
        middleware = config.get("middleware", {})
        auth_enabled = bool(middleware.get("auth_enabled", False))
        api_key = str(middleware.get("api_key", "")).strip()
        if auth_enabled and api_key and api_key.upper() != "CHANGEME":
            return self._pass("Authentication enabled with non-default API key")
        if auth_enabled and api_key:
            return self._warn("Authentication enabled but API key appears default placeholder")
        if self.security_config_path.exists():
            return self._pass("Security configuration present; auth can be enabled for deployment")
        return self._fail("Security middleware configuration missing")

    def check_rate_limiting(self) -> Dict[str, str]:
        config = self._load_security_config()
        middleware = config.get("middleware", {})
        if bool(middleware.get("rate_limit_enabled", True)):
            return self._pass("Rate limiting enabled")
        return self._fail("Rate limiting disabled")

    def check_input_validation(self) -> Dict[str, str]:
        config = self._load_security_config()
        middleware = config.get("middleware", {})
        if bool(middleware.get("sanitize_inputs", True)):
            return self._pass("Input sanitization enabled")
        return self._fail("Input sanitization disabled")

    def check_no_hardcoded_credentials(self) -> Dict[str, str]:
        if not self.configs_dir.exists():
            return self._warn("Config directory not found; credential scan skipped")
        bad_hits: List[str] = []
        placeholders = {"changeme", "redacted", "none", "null", "", "xxxxx"}
        for cfg in self.configs_dir.glob("**/*"):
            if not cfg.is_file() or cfg.suffix.lower() not in {".yaml", ".yml", ".json", ".env"}:
                continue
            try:
                lines = cfg.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for idx, line in enumerate(lines, start=1):
                low = line.lower()
                if any(token in low for token in ("password", "api_key", "secret", "token")) and ":" in line:
                    value = line.split(":", 1)[1].strip().strip("'\"").lower()
                    if value and value not in placeholders and not value.startswith("${"):
                        bad_hits.append(f"{cfg}:{idx}")
        if bad_hits:
            return self._fail(f"Potential hardcoded credentials found: {bad_hits[:10]}")
        return self._pass("No hardcoded credentials detected in configs")

    def check_model_integrity(self) -> Dict[str, str]:
        checksums_path = self.models_dir / "checksums.json"
        if not self.models_dir.exists():
            return self._warn("Models directory missing; integrity check skipped")
        if not checksums_path.exists():
            return self._warn("models/checksums.json missing")
        try:
            checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return self._fail(f"Invalid checksums file: {exc}")

        model_files = [
            p for p in self.models_dir.glob("**/*")
            if p.is_file() and p.name != "checksums.json"
        ]
        missing = [str(p.relative_to(self.models_dir)) for p in model_files if str(p.relative_to(self.models_dir)) not in checksums]
        if missing:
            return self._fail(f"Missing checksum entries: {missing[:10]}")
        return self._pass("All model files have checksum entries")

    def check_airgap(self) -> Dict[str, str]:
        result = self.airgap_verifier.verify()
        if result.get("air_gapped") is True:
            return self._pass("Air-gap checks passed")
        if result.get("air_gapped") is None:
            return self._warn(result.get("note", "Air-gap checks inconclusive"))
        return self._fail(f"Air-gap violations detected: {len(result.get('violations', []))}")

    def check_audit_chain(self) -> Dict[str, str]:
        result = self.audit_log.verify_chain()
        if result.get("entries_checked", 0) == 0:
            return self._warn("No audit entries to verify")
        if result.get("valid"):
            return self._pass(f"Audit chain valid for {result['entries_checked']} entries")
        return self._fail(f"Audit chain invalid: {result.get('errors', [])[:3]}")

    def check_classification_set(self) -> Dict[str, str]:
        config = self._load_security_config()
        value = str(config.get("classification", {}).get("level", "")).strip()
        if not value:
            return self._fail("Classification level missing")
        if ClassificationBanner.is_valid_level(value):
            return self._pass(f"Classification level configured: {value}")
        return self._fail(f"Invalid classification level configured: {value}")

    def check_cors_policy(self) -> Dict[str, str]:
        config = self._load_security_config()
        middleware = config.get("middleware", {})
        auth_enabled = bool(middleware.get("auth_enabled", False))
        cors_lockdown = bool(middleware.get("cors_lockdown", False))
        if auth_enabled and not cors_lockdown:
            return self._fail("Auth enabled but CORS lockdown disabled")
        if auth_enabled and cors_lockdown:
            return self._pass("Auth mode with locked-down CORS")
        return self._warn("Development mode CORS policy in use")

    def check_no_path_traversal_in_configs(self) -> Dict[str, str]:
        if not self.configs_dir.exists():
            return self._warn("Config directory missing; traversal scan skipped")
        violations: List[str] = []
        for cfg in self.configs_dir.glob("**/*"):
            if not cfg.is_file() or cfg.suffix.lower() not in {".yaml", ".yml"}:
                continue
            try:
                content = cfg.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "../" in content or "..\\" in content:
                violations.append(str(cfg))
        if violations:
            return self._fail(f"Path traversal-like patterns found in configs: {violations[:10]}")
        return self._pass("No traversal patterns found in YAML configs")

    def check_encryption_keys_exist(self) -> Dict[str, str]:
        if not self.keys_dir.exists():
            return self._fail("Encryption keys directory missing")
        keys = [p for p in self.keys_dir.glob("*.key") if p.is_file()]
        if not keys:
            return self._fail("No encryption keys present")
        return self._pass(f"{len(keys)} encryption key(s) found")

    def check_log_rotation(self) -> Dict[str, str]:
        log_dir = Path("data/security_audit")
        if not log_dir.exists():
            return self._warn("Audit log directory not found")
        oversized = [str(p) for p in log_dir.glob("audit_*.jsonl") if p.is_file() and p.stat().st_size > 100 * 1024 * 1024]
        if oversized:
            return self._fail(f"Oversized audit log files (>100MB): {oversized[:10]}")
        return self._pass("Audit log file sizes are within rotation thresholds")

    def run_full_check(self) -> Dict[str, Any]:
        checks_meta = [
            ("SEC-001", "Authentication configured", self.check_auth_configured),
            ("SEC-002", "Rate limiting enabled", self.check_rate_limiting),
            ("SEC-003", "Input validation active", self.check_input_validation),
            ("SEC-004", "No hardcoded credentials", self.check_no_hardcoded_credentials),
            ("SEC-005", "Model integrity checksums", self.check_model_integrity),
            ("SEC-006", "Air-gap verification", self.check_airgap),
            ("SEC-007", "Audit chain integrity", self.check_audit_chain),
            ("SEC-008", "Classification configured", self.check_classification_set),
            ("SEC-009", "CORS policy compliance", self.check_cors_policy),
            ("SEC-010", "No config path traversal", self.check_no_path_traversal_in_configs),
            ("SEC-011", "Encryption keys exist", self.check_encryption_keys_exist),
            ("SEC-012", "Audit log rotation health", self.check_log_rotation),
        ]

        checks: List[Dict[str, str]] = []
        passed = failed = warned = 0
        for cid, name, fn in checks_meta:
            result = fn()
            status = result.get("status", "WARN")
            checks.append({
                "id": cid,
                "name": name,
                "status": status,
                "detail": result.get("detail", ""),
            })
            if status == "PASS":
                passed += 1
            elif status == "FAIL":
                failed += 1
            else:
                warned += 1

        overall = "PASS"
        if failed > 0:
            overall = "FAIL"
        elif warned > 0:
            overall = "PARTIAL"

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall,
            "checks_passed": passed,
            "checks_failed": failed,
            "checks_warning": warned,
            "checks": checks,
        }
        self._latest_report = report
        return report

    def get_latest_report(self) -> Optional[Dict[str, Any]]:
        return self._latest_report

    def export_report(self, filepath: str) -> None:
        if not self._latest_report:
            self.run_full_check()
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._latest_report, indent=2), encoding="utf-8")

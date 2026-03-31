#!/usr/bin/env python3
"""Unit tests for compliance checker."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.compliance.compliance_checker import ComplianceChecker


class TestComplianceChecker(unittest.TestCase):
    def test_run_full_check_returns_expected_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.security.compliance.compliance_checker.Path", wraps=Path):
                checker = ComplianceChecker()
            report = checker.run_full_check()
            self.assertIn("overall_status", report)
            self.assertIn("checks", report)
            self.assertIsInstance(report["checks"], list)

    def test_check_no_hardcoded_credentials_detects_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            configs = Path(tmp) / "configs"
            configs.mkdir(parents=True, exist_ok=True)
            (configs / "bad.yaml").write_text("password: mysecret\n", encoding="utf-8")
            checker = ComplianceChecker()
            checker.configs_dir = configs
            result = checker.check_no_hardcoded_credentials()
            self.assertEqual(result["status"], "FAIL")

    def test_check_no_hardcoded_credentials_passes_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            configs = Path(tmp) / "configs"
            configs.mkdir(parents=True, exist_ok=True)
            (configs / "ok.yaml").write_text("password: CHANGEME\n", encoding="utf-8")
            checker = ComplianceChecker()
            checker.configs_dir = configs
            result = checker.check_no_hardcoded_credentials()
            self.assertEqual(result["status"], "PASS")

    def test_check_no_path_traversal_in_configs_detects_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            configs = Path(tmp) / "configs"
            configs.mkdir(parents=True, exist_ok=True)
            (configs / "bad.yaml").write_text("model_path: ../secrets/model.gguf\n", encoding="utf-8")
            checker = ComplianceChecker()
            checker.configs_dir = configs
            result = checker.check_no_path_traversal_in_configs()
            self.assertEqual(result["status"], "FAIL")

    def test_check_classification_set_passes_when_level_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "security.yaml"
            cfg.write_text("classification:\n  level: UNCLASSIFIED - FOUO\n", encoding="utf-8")
            checker = ComplianceChecker()
            checker.security_config_path = cfg
            result = checker.check_classification_set()
            self.assertEqual(result["status"], "PASS")

    def test_overall_status_is_fail_when_any_check_fails(self):
        checker = ComplianceChecker()

        def _fail():
            return {"status": "FAIL", "detail": "forced"}

        checker.check_auth_configured = _fail  # type: ignore[method-assign]
        report = checker.run_full_check()
        self.assertEqual(report["overall_status"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)

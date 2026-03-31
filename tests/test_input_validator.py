#!/usr/bin/env python3
"""Unit tests for InputValidator."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.input_validator import InputValidator


class TestInputValidator(unittest.TestCase):
    def test_check_path_traversal_detects_dotdot_and_encoded(self):
        self.assertTrue(InputValidator.check_path_traversal("../etc/passwd"))
        self.assertTrue(InputValidator.check_path_traversal("..%2e%2e/secret"))

    def test_check_path_traversal_passes_clean_path(self):
        self.assertFalse(InputValidator.check_path_traversal("models/phi3/model.gguf"))

    def test_check_injection_detects_sql_drop(self):
        self.assertTrue(InputValidator.check_injection("x'; DROP TABLE users;"))

    def test_check_injection_detects_command_injection(self):
        self.assertTrue(InputValidator.check_injection("run ; rm -rf /tmp"))

    def test_check_injection_detects_xss(self):
        self.assertTrue(InputValidator.check_injection("<script>alert(1)</script>"))

    def test_check_injection_passes_normal_text_including_arabic(self):
        self.assertFalse(InputValidator.check_injection("مهمة استطلاع دورية في القطاع ألف"))
        self.assertFalse(InputValidator.check_injection("normal mission text"))

    def test_check_payload_size_rejects_oversized(self):
        self.assertTrue(InputValidator.check_payload_size(10_485_761))
        self.assertFalse(InputValidator.check_payload_size(1024))

    def test_validate_file_path_rejects_absolute_paths_outside_allowed(self):
        valid, reason = InputValidator.validate_file_path("/tmp/secret.txt")
        self.assertFalse(valid)
        self.assertIn("outside allowed", reason)

    def test_validate_file_path_accepts_models_prefix(self):
        valid, reason = InputValidator.validate_file_path("models/phi3/model.gguf")
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")

    def test_sanitize_string_strips_null_bytes_preserves_arabic(self):
        value = " \x00مرحبا\t"
        cleaned = InputValidator.sanitize_string(value)
        self.assertEqual(cleaned, "مرحبا")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Tests for secure hash-chained audit log."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.crypto import SecureAuditLog


class TestSecureAuditLog(unittest.TestCase):
    def test_log_creates_entry_with_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = SecureAuditLog(log_dir=tmp)
            entry = audit.log("login", {"user": "alpha"})
            self.assertIn("entry_hash", entry)
            self.assertTrue(entry["entry_hash"])

    def test_consecutive_entries_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = SecureAuditLog(log_dir=tmp)
            first = audit.log("a", {"i": 1})
            second = audit.log("b", {"i": 2})
            self.assertEqual(second["previous_hash"], first["entry_hash"])

    def test_verify_chain_passes_on_valid_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = SecureAuditLog(log_dir=tmp)
            audit.log("a", {"v": 1})
            audit.log("b", {"v": 2})
            result = audit.verify_chain()
            self.assertTrue(result["valid"])

    def test_verify_chain_detects_tampered_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = SecureAuditLog(log_dir=tmp)
            audit.log("a", {"v": 1})
            audit.log("b", {"v": 2})
            file_path = sorted(Path(tmp).glob("audit_*.jsonl"))[0]
            rows = file_path.read_text(encoding="utf-8").splitlines()
            entry = json.loads(rows[0])
            entry["action"] = "tampered"
            rows[0] = json.dumps(entry)
            file_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            result = audit.verify_chain()
            self.assertFalse(result["valid"])

    def test_query_filters_by_action_and_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = SecureAuditLog(log_dir=tmp)
            audit.log("alpha", {"k": 1}, severity="INFO")
            audit.log("beta", {"k": 2}, severity="WARNING")
            rows = audit.query(action="beta", severity="WARNING", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["action"], "beta")

    def test_get_stats_returns_correct_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = SecureAuditLog(log_dir=tmp)
            audit.log("x", {"v": 1}, severity="INFO", source="s1")
            audit.log("y", {"v": 2}, severity="WARNING", source="s2")
            stats = audit.get_stats()
            self.assertEqual(stats["total_entries"], 2)
            self.assertEqual(stats["entries_by_severity"]["INFO"], 1)
            self.assertEqual(stats["entries_by_source"]["s1"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

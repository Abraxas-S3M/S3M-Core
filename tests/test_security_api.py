#!/usr/bin/env python3
"""Integration tests for Phase 10 security API routes."""

import os
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.server import app


class TestSecurityAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_security_status(self):
        resp = self.client.get("/security/status")
        self.assertEqual(resp.status_code, 200)

    def test_get_security_audit(self):
        self.client.get("/security/status")
        resp = self.client.get("/security/audit")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_get_security_audit_verify(self):
        resp = self.client.get("/security/audit/verify")
        self.assertEqual(resp.status_code, 200)

    def test_post_airgap_verify(self):
        resp = self.client.post("/security/airgap/verify")
        self.assertEqual(resp.status_code, 200)

    def test_post_compliance_check(self):
        resp = self.client.post("/security/compliance/check")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("overall_status", resp.json())

    def test_post_vulnerability_scan(self):
        resp = self.client.post("/security/vulnerability/scan")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("findings", resp.json())

    def test_get_classification(self):
        resp = self.client.get("/security/classification")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("level", resp.json())

    def test_get_interop_status(self):
        resp = self.client.get("/security/interop/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("protocols", resp.json())

    def test_post_encrypt_invalid_filepath(self):
        resp = self.client.post(
            "/security/encrypt",
            json={"filepath": "/etc/passwd", "key_id": "default"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)

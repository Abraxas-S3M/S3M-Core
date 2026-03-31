#!/usr/bin/env python3
"""Unit tests for AirGapVerifier."""

import os
import platform
import socket
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.airgap_verifier import AirGapVerifier


class TestAirGapVerifier(unittest.TestCase):
    def test_verify_returns_expected_structure(self):
        verifier = AirGapVerifier()
        result = verifier.verify()
        self.assertIn("timestamp", result)
        self.assertIn("violations", result)
        self.assertIn("checks_performed", result)
        self.assertIn("air_gapped", result)

    def test_non_linux_returns_skipped_status(self):
        verifier = AirGapVerifier()
        with patch("platform.system", return_value="Darwin"):
            result = verifier.verify()
        self.assertIsNone(result.get("air_gapped"))
        self.assertIn("skipped", result.get("note", "").lower())

    def test_dns_check_handles_failure_as_pass(self):
        verifier = AirGapVerifier()
        violations = []
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("no dns")):
            verifier._check_dns(violations)
        self.assertEqual(violations, [])

    def test_outbound_connectivity_check_flags_success(self):
        verifier = AirGapVerifier()
        violations = []

        class _Conn:
            def close(self):
                return None

        with patch("socket.create_connection", return_value=_Conn()):
            verifier._check_outbound_connectivity(violations)
        self.assertTrue(any(v.get("check") == "outbound_connectivity" for v in violations))

    def test_get_allowed_ports_includes_8080(self):
        verifier = AirGapVerifier(allowed_extra_ports=[3000, 9090])
        ports = verifier.get_allowed_ports()
        self.assertIn(8080, ports)
        self.assertIn(3000, ports)


if __name__ == "__main__":
    unittest.main(verbosity=2)

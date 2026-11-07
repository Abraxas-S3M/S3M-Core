"""Unit tests for range egress guard."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from range.egress_guard import assert_range_egress_blocked, probe_external_egress


def test_probe_reports_blocked_on_os_error() -> None:
    with patch("range.egress_guard.socket.create_connection", side_effect=OSError("no route")):
        result = probe_external_egress(host="203.0.113.53", port=443)
    assert result.connected is False


def test_assert_fails_when_egress_succeeds() -> None:
    fake_conn = MagicMock()
    with patch("range.egress_guard.socket.create_connection", return_value=fake_conn):
        with pytest.raises(RuntimeError, match="egress guard failed"):
            assert_range_egress_blocked()


def test_assert_passes_when_all_probes_fail() -> None:
    with patch("range.egress_guard.socket.create_connection", side_effect=socket.timeout):
        assert_range_egress_blocked()

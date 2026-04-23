"""Unit tests for canary deployment and trip detection."""

from __future__ import annotations

import socket
import time

from s3m_core.defense.testing.canary_deployer import CanaryDeployer


def test_deploy_canaries_creates_all_expected_types(tmp_path) -> None:
    deployer = CanaryDeployer(canary_root=tmp_path / "canaries")
    try:
        canaries = deployer.deploy_canaries("container-a")
        assert len(canaries) == 6
        assert len({canary.token for canary in canaries}) == 6
        assert {canary.type for canary in canaries} == {
            "fake_credentials_file",
            "fake_ssh_key",
            "fake_db_config",
            "honeypot_service",
            "fake_git_repository",
            "environment_variable",
        }
    finally:
        deployer.shutdown()


def test_check_canaries_reports_honeypot_connection(tmp_path) -> None:
    deployer = CanaryDeployer(canary_root=tmp_path / "canaries")
    try:
        canaries = deployer.deploy_canaries("container-b")
        service_canary = next(canary for canary in canaries if canary.type == "honeypot_service")
        host, port_text = service_canary.location.rsplit(":", maxsplit=1)

        with socket.create_connection((host, int(port_text)), timeout=1.0) as conn:
            conn.recv(1024)

        deadline = time.time() + 1.0
        while time.time() < deadline:
            trips = deployer.check_canaries()
            if any(trip.canary_id == service_canary.canary_id for trip in trips):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("expected a canary trip after honeypot connection")
    finally:
        deployer.shutdown()


def test_check_canaries_reports_observed_token_usage(tmp_path) -> None:
    events: list[dict[str, str]] = []

    def observer(tokens: set[str]) -> list[dict[str, str]]:
        return [event for event in events if event["token"] in tokens]

    deployer = CanaryDeployer(canary_root=tmp_path / "canaries", token_observer=observer)
    try:
        canaries = deployer.deploy_canaries("container-c")
        file_canary = next(canary for canary in canaries if canary.type == "fake_credentials_file")
        events.append(
            {
                "token": file_canary.token,
                "accessed_at": "2026-01-01T00:00:00+00:00",
                "accessed_by": "unit-test",
                "method": "credential_use",
            }
        )

        trips = deployer.check_canaries()
        assert any(
            trip.canary_id == file_canary.canary_id
            and trip.accessed_by == "unit-test"
            and trip.method == "credential_use"
            for trip in trips
        )
    finally:
        deployer.shutdown()

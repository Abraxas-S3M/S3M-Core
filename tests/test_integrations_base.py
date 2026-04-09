"""Unit tests for shared S3M integration adapter primitives."""

from __future__ import annotations

import json

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class _DummyIntegrationAdapter(IntegrationAdapter):
    integration_id = "dummy"
    domain = "intel"

    def get_manifest(self) -> IntegrationManifest:
        return IntegrationManifest(
            name="Dummy",
            slug="dummy",
            domain=self.domain,
            source_url="https://example.invalid/dummy",
            license="MIT",
            description="Dummy integration for tactical adapter tests.",
            integration_type="adapter",
        )

    def validate_availability(self) -> bool:
        return True

    def execute(self, params=None):
        return {"ok": True, "params": params or {}}


def test_adapter_mode_defaults_to_online_when_airgap_disabled(monkeypatch) -> None:
    monkeypatch.setenv("S3M_AIRGAPPED", "false")
    adapter = _DummyIntegrationAdapter()
    assert adapter.mode == "online"
    assert adapter.is_airgapped is False


def test_adapter_mode_defaults_to_airgapped_from_env(monkeypatch) -> None:
    monkeypatch.setenv("S3M_AIRGAPPED", "yes")
    adapter = _DummyIntegrationAdapter()
    assert adapter.mode == "airgapped"
    assert adapter.is_airgapped is True


def test_adapter_mode_respects_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("S3M_AIRGAPPED", "true")
    adapter = _DummyIntegrationAdapter(mode="online")
    assert adapter.mode == "online"
    assert adapter.is_airgapped is False


def test_adapter_env_helper_checks_s3m_prefix(monkeypatch) -> None:
    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.setenv("S3M_TOKEN", "secure-token")
    adapter = _DummyIntegrationAdapter()
    assert adapter._env("TOKEN") == "secure-token"  # noqa: SLF001 - helper under test


def test_adapter_reads_fixture_and_returns_empty_when_missing(tmp_path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir(parents=True)
    fixture_file = fixture_dir / "status.json"
    fixture_file.write_text(json.dumps({"status": "ok"}), encoding="utf-8")

    adapter = _DummyIntegrationAdapter()
    adapter._fixture_dir = fixture_dir  # noqa: SLF001 - controlled test fixture path

    assert adapter._read_fixture("status.json") == {"status": "ok"}  # noqa: SLF001
    assert adapter._read_fixture("missing.json") == {}  # noqa: SLF001


def test_adapter_health_check_reports_uniform_fields() -> None:
    adapter = _DummyIntegrationAdapter(mode="airgapped")
    health = adapter.health_check()
    assert health == {
        "integration_id": "dummy",
        "domain": "intel",
        "mode": "airgapped",
        "available": True,
        "airgapped": True,
    }

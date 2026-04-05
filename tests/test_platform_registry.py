"""Unit tests for platform adapter registry used by HOOL startup."""

from __future__ import annotations

import types

from src.platforms.common.platform_registry import PlatformRegistry


class _AdapterStub:
    def __init__(self) -> None:
        self._position = (0.0, 0.0, 0.0)

    def connect(self) -> bool:
        return True

    def read_state(self) -> object:
        return types.SimpleNamespace(
            position=self._position,
            health_state=types.SimpleNamespace(value="nominal"),
        )


def test_platform_registry_registers_and_lists_metadata() -> None:
    registry = PlatformRegistry()
    registry.register_adapter(
        platform_id="alpha-1",
        platform_type="uav",
        adapter_class="AdapterStub",
        adapter=_AdapterStub(),
        initial_position=(10.0, 20.0, 30.0),
    )

    rows = registry.list_platforms()
    assert len(rows) == 1
    assert rows[0].platform_id == "alpha-1"
    assert rows[0].platform_type == "uav"


def test_platform_registry_fleet_status_summary_reads_adapter_state() -> None:
    registry = PlatformRegistry()
    adapter = _AdapterStub()
    adapter._position = (1.0, 2.0, 3.0)  # noqa: SLF001 - test fixture injection
    registry.register_adapter(
        platform_id="alpha-2",
        platform_type="ugv",
        adapter_class="AdapterStub",
        adapter=adapter,
        initial_position=(0.0, 0.0, 0.0),
    )

    summary = registry.fleet_status_summary()
    assert len(summary) == 1
    assert summary[0]["platform_id"] == "alpha-2"
    assert summary[0]["position"] == (1.0, 2.0, 3.0)
    assert summary[0]["health_state"] == "nominal"

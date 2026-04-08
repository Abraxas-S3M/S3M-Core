"""Adapter initialization uses operational persistence when available."""

from __future__ import annotations

import importlib
import sys
import types


class _FakeStore:
    def __init__(self, table_has_data: dict[str, bool] | None = None) -> None:
        self._table_has_data = table_has_data or {}

    def has_data(self, table: str) -> bool:
        return bool(self._table_has_data.get(table, False))


def _install_seed_stub(monkeypatch, table_has_data: dict[str, bool] | None = None) -> _FakeStore:
    fake_store = _FakeStore(table_has_data=table_has_data)
    seeder_module = types.ModuleType("src.persistence.store_seeder")
    seeder_module.seed_store_if_empty = lambda: fake_store
    monkeypatch.setitem(sys.modules, "src.persistence.store_seeder", seeder_module)
    return fake_store


def _reload_module(module_path: str):
    sys.modules.pop(module_path, None)
    return importlib.import_module(module_path)


def test_sustainment_init_sets_store_flags(monkeypatch) -> None:
    _install_seed_stub(monkeypatch, {"fleet_assets": True, "supply_items": False})
    module = _reload_module("src.api.gui_bridge.adapters.sustainment_adapter")
    adapter = module.SustainmentAdapter()
    assert adapter._store is not None
    assert adapter._use_store_fleet is True
    assert adapter._use_store_supply is False


def test_readiness_init_sets_store_flags(monkeypatch) -> None:
    _install_seed_stub(monkeypatch, {"readiness_personnel": True})
    readiness_routes = types.ModuleType("src.api.readiness_routes")
    readiness_routes._readiness_store = lambda: {}
    monkeypatch.setitem(sys.modules, "src.api.readiness_routes", readiness_routes)
    module = _reload_module("src.api.gui_bridge.adapters.readiness_adapter")
    adapter = module.ReadinessAdapter()
    assert adapter._store is not None
    assert adapter._use_store_units is True


def test_cyber_init_sets_store_flags(monkeypatch) -> None:
    _install_seed_stub(monkeypatch, {"incidents": True})
    cyber_services = types.ModuleType("services.cyber.soc_manager")

    class _SOCManager:
        pass

    cyber_services.SOCManager = _SOCManager
    monkeypatch.setitem(sys.modules, "services.cyber.soc_manager", cyber_services)
    module = _reload_module("src.api.gui_bridge.adapters.cyber_adapter")
    adapter = module.CyberAdapter()
    assert adapter._store is not None
    assert adapter._use_store_incidents is True


def test_comms_init_sets_store_flags(monkeypatch) -> None:
    _install_seed_stub(monkeypatch, {"messages": True})
    comms_services = types.ModuleType("services.comms.comms_manager")

    class _CommsManager:
        pass

    comms_services.CommsManager = _CommsManager
    monkeypatch.setitem(sys.modules, "services.comms.comms_manager", comms_services)
    module = _reload_module("src.api.gui_bridge.adapters.comms_adapter")
    adapter = module.CommsAdapter()
    assert adapter._store is not None
    assert adapter._use_store_messages is True


def test_simulation_init_sets_store_flags(monkeypatch) -> None:
    _install_seed_stub(monkeypatch, {"scenarios": True})
    module = _reload_module("src.api.gui_bridge.adapters.simulation_adapter")
    adapter = module.SimulationAdapter()
    assert adapter._store is not None
    assert adapter._use_store_scenarios is True


def test_decision_init_sets_store_flags(monkeypatch) -> None:
    _install_seed_stub(monkeypatch, {"decisions": True})
    provider_module = types.ModuleType("src.dashboard.providers.autonomy_dash_provider")

    class _Provider:
        def get_decision_feed(self, limit: int = 500):
            return []

    provider_module.AutonomyDashProvider = _Provider
    monkeypatch.setitem(sys.modules, "src.dashboard.providers.autonomy_dash_provider", provider_module)
    module = _reload_module("src.api.gui_bridge.adapters.decision_adapter")
    adapter = module.DecisionAdapter()
    assert adapter._store is not None
    assert adapter._use_store_decisions is True


def test_cop_init_sets_store_flags(monkeypatch) -> None:
    _install_seed_stub(monkeypatch, {"tracks": True, "threats": False})
    provider_module = types.ModuleType("src.dashboard.providers.cop_provider")

    class _Provider:
        def get_tracks(self):
            return []

        def get_threats(self):
            return []

    provider_module.COPDataProvider = _Provider
    monkeypatch.setitem(sys.modules, "src.dashboard.providers.cop_provider", provider_module)
    module = _reload_module("src.api.gui_bridge.adapters.cop_adapter")
    adapter = module.COPAdapter()
    assert adapter._store is not None
    assert adapter._use_store_tracks is True
    assert adapter._use_store_threats is False

from __future__ import annotations

import sys
import types

from src.persistence.store_seeder import seed_store_if_empty


def test_seed_store_if_empty_populates_tables(monkeypatch) -> None:
    adapter_rows = {
        "src.api.gui_bridge.adapters.comms_adapter": {"CommsAdapter": {"_default_inbox": [{"id": "MSG-1"}]}},
        "src.api.gui_bridge.adapters.sustainment_adapter": {
            "SustainmentAdapter": {
                "_default_fleet": [{"unitId": "U-1"}],
                "_default_supply": [{"category": "fuel"}],
            }
        },
        "src.api.gui_bridge.adapters.readiness_adapter": {
            "ReadinessAdapter": {"_default_units": [{"unitId": "ALPHA-1"}]}
        },
        "src.api.gui_bridge.adapters.simulation_adapter": {
            "SimulationAdapter": {"_defaults": [{"id": "SCN-001"}]}
        },
        "src.api.gui_bridge.adapters.cyber_adapter": {
            "CyberAdapter": {"_default_incidents": [{"id": "CYB-001"}]}
        },
    }

    for module_name, cls_payload in adapter_rows.items():
        module = types.ModuleType(module_name)
        for class_name, method_map in cls_payload.items():
            attrs = {name: staticmethod(lambda rows=rows: rows) for name, rows in method_map.items()}
            setattr(module, class_name, type(class_name, (), attrs))
        monkeypatch.setitem(sys.modules, module_name, module)

    class _StoreStub:
        def __init__(self) -> None:
            self.tables: dict[str, list[dict]] = {}

        def has_data(self, table: str) -> bool:
            return bool(self.tables.get(table))

        def upsert(self, table: str, row: dict) -> None:
            self.tables.setdefault(table, []).append(dict(row))

    store = _StoreStub()
    seeded = seed_store_if_empty(store=store)
    assert seeded is store
    assert store.tables["messages"][0]["id"] == "MSG-1"
    assert store.tables["fleet_assets"][0]["unitId"] == "U-1"
    assert store.tables["supply_items"][0]["category"] == "fuel"
    assert store.tables["readiness_personnel"][0]["unitId"] == "ALPHA-1"
    assert store.tables["scenarios"][0]["id"] == "SCN-001"
    assert store.tables["incidents"][0]["id"] == "CYB-001"


def test_seed_store_if_empty_skips_non_empty_tables(monkeypatch) -> None:
    comms_module = types.ModuleType("src.api.gui_bridge.adapters.comms_adapter")
    comms_module.CommsAdapter = type(
        "CommsAdapter",
        (),
        {"_default_inbox": staticmethod(lambda: [{"id": "MSG-NEW"}])},
    )
    monkeypatch.setitem(sys.modules, "src.api.gui_bridge.adapters.comms_adapter", comms_module)

    class _StoreStub:
        def __init__(self) -> None:
            self.tables = {"messages": [{"id": "MSG-OLD"}]}

        def has_data(self, table: str) -> bool:
            return bool(self.tables.get(table))

        def upsert(self, table: str, row: dict) -> None:
            self.tables.setdefault(table, []).append(dict(row))

    store = _StoreStub()
    seed_store_if_empty(store=store)
    assert store.tables["messages"] == [{"id": "MSG-OLD"}]

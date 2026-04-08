"""Bootstrap persistence with existing GUI adapter default records."""

from __future__ import annotations

import importlib
from typing import Any

from src.persistence.operational_store import OperationalStore


SEED_SOURCES: dict[str, tuple[str, str, str]] = {
    "messages": (
        "src.api.gui_bridge.adapters.comms_adapter",
        "CommsAdapter",
        "_default_inbox",
    ),
    "fleet_assets": (
        "src.api.gui_bridge.adapters.sustainment_adapter",
        "SustainmentAdapter",
        "_default_fleet",
    ),
    "supply_items": (
        "src.api.gui_bridge.adapters.sustainment_adapter",
        "SustainmentAdapter",
        "_default_supply",
    ),
    "readiness_personnel": (
        "src.api.gui_bridge.adapters.readiness_adapter",
        "ReadinessAdapter",
        "_default_units",
    ),
    "scenarios": (
        "src.api.gui_bridge.adapters.simulation_adapter",
        "SimulationAdapter",
        "_defaults",
    ),
    "incidents": (
        "src.api.gui_bridge.adapters.cyber_adapter",
        "CyberAdapter",
        "_default_incidents",
    ),
}


def _to_record(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        payload = value.model_dump()
        if isinstance(payload, dict):
            return payload
    if hasattr(value, "to_dict"):
        payload = value.to_dict()
        if isinstance(payload, dict):
            return payload
    return {}


def _read_default_rows(module_name: str, class_name: str, method_name: str) -> list[dict[str, Any]]:
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    method = getattr(cls, method_name)
    rows = method() if callable(method) else []
    if not isinstance(rows, list):
        return []
    return [record for item in rows if (record := _to_record(item))]


def seed_store_if_empty(store: OperationalStore | None = None) -> OperationalStore:
    operational_store = store or OperationalStore()

    for table, source in SEED_SOURCES.items():
        if operational_store.has_data(table):
            continue
        module_name, class_name, method_name = source
        try:
            rows = _read_default_rows(module_name, class_name, method_name)
        except Exception:
            continue
        for row in rows:
            operational_store.upsert(table, row)

    return operational_store

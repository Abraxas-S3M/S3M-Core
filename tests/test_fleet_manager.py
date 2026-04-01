from __future__ import annotations

from services.maintenance.assets import AssetRegistry, FleetManager
from services.maintenance.models import AssetCondition


def _register_asset(registry: AssetRegistry):
    return registry.register(
        name="F-15SA",
        designation="F-15SA #990",
        asset_type="FIGHTER_JET",
        serial_number="SN-F15-990",
        manufacturer="S3M Aero",
        model="F-15SA",
        location="Air Base",
        assigned_unit="RSAF Test Wing",
        operating_hours=1200.0,
    )


def test_ingest_telemetry_updates_asset_condition():
    registry = AssetRegistry()
    asset = _register_asset(registry)
    fleet = FleetManager(asset_registry=registry)

    out = fleet.ingest_telemetry(
        asset.asset_id,
        readings={"temperature_c": 460.0, "vibration_g": 3.0, "pressure_psi": 34.0},
        operating_mode="cruise",
    )
    assert out["asset_id"] == asset.asset_id
    assert registry.get_asset(asset.asset_id).condition in {AssetCondition.FAIR, AssetCondition.GOOD}


def test_ingest_telemetry_critical_reading_generates_alert():
    registry = AssetRegistry()
    asset = _register_asset(registry)
    fleet = FleetManager(asset_registry=registry)

    out = fleet.ingest_telemetry(
        asset.asset_id,
        readings={"temperature_c": 540.0, "vibration_g": 6.2, "pressure_psi": 18.0},
        operating_mode="combat",
    )
    assert any(alert["severity"] == "critical" for alert in out["alerts"])


def test_run_fleet_health_check_returns_summary_for_all_assets():
    registry = AssetRegistry()
    a1 = _register_asset(registry)
    a2 = registry.register(
        name="M1A2 Abrams",
        designation="M1A2 #991",
        asset_type="TANK",
        serial_number="SN-M1A2-991",
        manufacturer="S3M Land",
        model="M1A2",
        location="Ground Base",
        assigned_unit="Armor Test Unit",
        operating_hours=1800.0,
    )
    fleet = FleetManager(asset_registry=registry)
    fleet.ingest_telemetry(a1.asset_id, {"temperature_c": 430.0, "vibration_g": 2.0, "pressure_psi": 34.0})
    fleet.ingest_telemetry(a2.asset_id, {"temperature_c": 410.0, "vibration_g": 1.8, "pressure_psi": 32.0})

    summary = fleet.run_fleet_health_check()
    assert summary["total_assets"] == 2
    assert "readiness_score" in summary
    assert isinstance(summary["assets_needing_attention"], list)


def test_get_fleet_readiness_computes_operational_percentage():
    registry = AssetRegistry()
    _register_asset(registry)
    _register_asset(registry)
    fleet = FleetManager(asset_registry=registry)
    readiness = fleet.get_fleet_readiness()
    assert readiness["total_assets"] == 2
    assert readiness["operational"] == 2
    assert readiness["readiness_pct"] == 100.0

from __future__ import annotations

from services.maintenance import MaintenanceManager


def test_full_pipeline_register_ingest_predict_work_order_procurement():
    manager = MaintenanceManager()
    manager.spare_parts.create_standard_inventory()
    asset = manager.register_asset(
        name="F-15SA",
        designation="F-15SA #501",
        asset_type="FIGHTER_JET",
        serial_number="F15-501",
        manufacturer="S3M Aero",
        model="F-15SA",
        location="Air Base",
        assigned_unit="RSAF",
        operating_hours=4700,
    )

    for i in range(12):
        manager.ingest_telemetry(
            asset.asset_id,
            {
                "temperature_c": 510 + i,
                "vibration_g": 5.3,
                "pressure_psi": 19.0,
                "oil_temp_c": 126.0,
                "rpm": 12500,
                "fuel_flow_rate": 0.9,
                "rpm_deviation_pct": 11.0,
            },
            "combat",
        )
    prediction = manager.predict_rul(asset.asset_id)
    assert prediction.asset_id == asset.asset_id

    generated = manager.generate_work_orders()
    assert isinstance(generated, list)
    assert generated

    procurement = manager.check_procurement_needs()
    assert isinstance(procurement, list)


def test_generate_fleet_report_non_empty():
    manager = MaintenanceManager()
    manager.asset_registry.create_saudi_fleet_template()
    report = manager.generate_fleet_report()
    assert isinstance(report, str)
    assert report.strip()


def test_health_check_returns_subsystem_statuses():
    manager = MaintenanceManager()
    health = manager.health_check()
    assert health["status"] == "operational"
    for key in ["predictive_engine", "asset_registry", "fleet_manager", "scheduler", "procurement", "spare_parts", "erp"]:
        assert key in health

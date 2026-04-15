"""Unit tests for STANAG 4586 UAS interoperability layer."""

from __future__ import annotations

import logging

from services.interop.uas4586 import UAS4586Interface


def _registered_interface() -> UAS4586Interface:
    interface = UAS4586Interface(config={"max_loi": 3, "registered_uavs": [], "publish_interval_seconds": 1})
    interface.register_uav("falcon-uav-1", "MALE", ["LOI1", "LOI2", "LOI3", "EO_IR"])
    return interface


def test_register_uav_friendly_uav() -> None:
    interface = UAS4586Interface(config={"max_loi": 3})
    registration = interface.register_uav("falcon-uav-9", "TACTICAL_UAV", ["LOI1", "LOI2", "LOI3", "SAR"])
    assert registration["uav_id"] == "falcon-uav-9"
    assert registration["uav_type"] == "TACTICAL_UAV"
    assert registration["capabilities"] == ["LOI1", "LOI2", "LOI3", "SAR"]
    assert registration["effective_loi"] == 3
    assert registration["supported_loi"] == [1, 2, 3]


def test_publish_vehicle_status_position() -> None:
    interface = _registered_interface()
    published = interface.publish_vehicle_status(
        "falcon-uav-1",
        {
            "position": {"lat": 24.71360000, "lon": 46.67530000, "altitude": 800.0},
            "speed": 52.5,
            "heading": 270.0,
            "fuel": 65.0,
            "mode": "ON_STATION",
        },
    )
    assert published is True
    xml = interface.get_published_messages("vehicle_status")[0]
    assert "<Latitude>24.71360000</Latitude>" in xml
    assert "<Longitude>46.67530000</Longitude>" in xml
    assert "<AltitudeMeters>800.00</AltitudeMeters>" in xml


def test_publish_payload_status_camera() -> None:
    interface = _registered_interface()
    published = interface.publish_payload_status(
        "falcon-uav-1",
        {
            "sensor_type": "EO_CAMERA",
            "pointing_angles": {"azimuth": 135.0, "elevation": -10.0},
            "fov": 28.0,
            "operational_status": "TRACKING",
        },
    )
    assert published is True
    xml = interface.get_published_messages("payload_status")[0]
    assert "<SensorType>EO_CAMERA</SensorType>" in xml
    assert "<AzimuthDeg>135.00</AzimuthDeg>" in xml
    assert "<ElevationDeg>-10.00</ElevationDeg>" in xml
    assert "<FOVDeg>28.00</FOVDeg>" in xml


def test_loi_levels_1_through_3() -> None:
    interface = _registered_interface()
    payload_events: list[dict] = []
    interface.receive_payload_command(lambda event: payload_events.append(event))

    assert interface.publish_isr_product(
        "falcon-uav-1",
        {"product_type": "imagery", "reference": "file:///data/isr/target-grid-23.jpg"},
    )
    assert interface.publish_vehicle_status(
        "falcon-uav-1",
        {
            "position": {"latitude": 24.70, "longitude": 46.61, "altitude": 750.0},
            "speed": 43.0,
            "heading": 110.0,
            "fuel": 72.0,
            "mode": "ORBIT",
        },
    )
    assert interface.publish_payload_status(
        "falcon-uav-1",
        {
            "sensor_type": "EO_IR_TURRET",
            "pointing_angles": {"azimuth": 90.0, "elevation": -15.0},
            "fov": 24.0,
            "operational_status": "ACTIVE",
        },
    )

    command_result = interface.handle_payload_command(
        {
            "uav_id": "falcon-uav-1",
            "command_name": "SLEW_TO_AZ_EL",
            "azimuth": 182.0,
            "elevation": -8.0,
        }
    )
    assert command_result["accepted"] is True
    assert payload_events and payload_events[0]["command_name"] == "SLEW_TO_AZ_EL"


def test_loi_4_5_rejected(caplog) -> None:
    interface = _registered_interface()
    vehicle_events: list[dict] = []
    interface.receive_vehicle_command(lambda event: vehicle_events.append(event))

    with caplog.at_level(logging.WARNING):
        result = interface.handle_vehicle_command(
            {"uav_id": "falcon-uav-1", "command_name": "EXECUTE_AUTO_TAKEOFF", "runway": "AUX-01"}
        )

    assert result["accepted"] is False
    assert "LOI 4/5 vehicle control disabled" in result["reason"]
    assert vehicle_events and vehicle_events[0]["accepted"] is False
    assert any("Rejected STANAG 4586 vehicle command" in rec.message for rec in caplog.records)

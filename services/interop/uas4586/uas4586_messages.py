"""STANAG 4586 XML message build/parse helpers for coalition UAS exchanges."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import xml.etree.ElementTree as ET


class UAS4586MessageHandler:
    """Build and parse representative STANAG 4586 XML messages."""

    namespace = "urn:nato:stanag:4586"

    def __init__(self) -> None:
        ET.register_namespace("", self.namespace)

    def build_vehicle_status(self, uav_id: str, status: dict[str, Any]) -> str:
        """Build VehicleStatusMessage from DroneOps vehicle telemetry."""
        vehicle_id = self._ensure_non_empty_text(uav_id, "uav_id")
        if not isinstance(status, dict):
            raise ValueError("status must be a dictionary")
        lat, lon, altitude = self._extract_position(status)
        speed = self._as_float(status.get("speed", status.get("groundspeed", 0.0)), "speed", minimum=0.0)
        heading = self._normalize_heading(status.get("heading", 0.0))
        fuel = self._as_float(status.get("fuel", status.get("fuel_pct", 100.0)), "fuel", minimum=0.0, maximum=100.0)
        mode = self._ensure_non_empty_text(status.get("mode", "UNKNOWN"), "mode")

        root = ET.Element(self._tag("VehicleStatusMessage"))
        header = ET.SubElement(root, self._tag("Header"))
        ET.SubElement(header, self._tag("MessageType")).text = "VehicleStatus"
        ET.SubElement(header, self._tag("Timestamp")).text = self._normalize_timestamp(status.get("timestamp"))

        vehicle = ET.SubElement(root, self._tag("Vehicle"))
        ET.SubElement(vehicle, self._tag("UAVId")).text = vehicle_id
        position = ET.SubElement(vehicle, self._tag("Position"))
        ET.SubElement(position, self._tag("Latitude")).text = f"{lat:.8f}"
        ET.SubElement(position, self._tag("Longitude")).text = f"{lon:.8f}"
        ET.SubElement(vehicle, self._tag("AltitudeMeters")).text = f"{altitude:.2f}"
        ET.SubElement(vehicle, self._tag("SpeedMps")).text = f"{speed:.2f}"
        ET.SubElement(vehicle, self._tag("HeadingDeg")).text = f"{heading:.2f}"
        ET.SubElement(vehicle, self._tag("FuelPercent")).text = f"{fuel:.2f}"
        ET.SubElement(vehicle, self._tag("Mode")).text = mode
        return ET.tostring(root, encoding="unicode")

    def parse_vehicle_status(self, xml_str: str) -> dict[str, Any]:
        """Parse VehicleStatusMessage into DroneOps-friendly telemetry."""
        root = self._parse_xml(xml_str, "VehicleStatusMessage")
        vehicle = self._find_required_node(root, "Vehicle")
        position = self._find_required_node(vehicle, "Position")
        lat = self._as_float(self._find_text(position, "Latitude", "0.0"), "latitude", minimum=-90.0, maximum=90.0)
        lon = self._as_float(self._find_text(position, "Longitude", "0.0"), "longitude", minimum=-180.0, maximum=180.0)
        altitude = self._as_float(self._find_text(vehicle, "AltitudeMeters", "0.0"), "altitude")
        speed = self._as_float(self._find_text(vehicle, "SpeedMps", "0.0"), "speed", minimum=0.0)
        heading = self._normalize_heading(self._find_text(vehicle, "HeadingDeg", "0.0"))
        fuel = self._as_float(self._find_text(vehicle, "FuelPercent", "100.0"), "fuel", minimum=0.0, maximum=100.0)
        return {
            "uav_id": self._find_text(vehicle, "UAVId", ""),
            "position": [lat, lon],
            "altitude": altitude,
            "speed": speed,
            "heading": heading,
            "fuel": fuel,
            "mode": self._find_text(vehicle, "Mode", "UNKNOWN"),
            "timestamp": self._find_text(self._find_node(root, "Header"), "Timestamp", ""),
        }

    def build_payload_status(self, uav_id: str, payload: dict[str, Any]) -> str:
        """Build PayloadStatusMessage with sensor state and orientation."""
        vehicle_id = self._ensure_non_empty_text(uav_id, "uav_id")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary")
        pointing = payload.get("pointing_angles", {})
        if pointing is None:
            pointing = {}
        if not isinstance(pointing, dict):
            raise ValueError("pointing_angles must be a dictionary")

        sensor_type = self._ensure_non_empty_text(payload.get("sensor_type", "UNKNOWN"), "sensor_type")
        azimuth = self._as_float(payload.get("azimuth", pointing.get("azimuth", 0.0)), "azimuth")
        elevation = self._as_float(payload.get("elevation", pointing.get("elevation", 0.0)), "elevation")
        fov = self._as_float(payload.get("fov", payload.get("field_of_view", 0.0)), "fov", minimum=0.0)
        status = self._ensure_non_empty_text(
            payload.get("operational_status", payload.get("status", "OPERATIONAL")),
            "operational_status",
        )

        root = ET.Element(self._tag("PayloadStatusMessage"))
        header = ET.SubElement(root, self._tag("Header"))
        ET.SubElement(header, self._tag("MessageType")).text = "PayloadStatus"
        ET.SubElement(header, self._tag("Timestamp")).text = self._normalize_timestamp(payload.get("timestamp"))

        sensor = ET.SubElement(root, self._tag("Payload"))
        ET.SubElement(sensor, self._tag("UAVId")).text = vehicle_id
        ET.SubElement(sensor, self._tag("SensorType")).text = sensor_type
        pointing_el = ET.SubElement(sensor, self._tag("Pointing"))
        ET.SubElement(pointing_el, self._tag("AzimuthDeg")).text = f"{azimuth:.2f}"
        ET.SubElement(pointing_el, self._tag("ElevationDeg")).text = f"{elevation:.2f}"
        ET.SubElement(sensor, self._tag("FOVDeg")).text = f"{fov:.2f}"
        ET.SubElement(sensor, self._tag("OperationalStatus")).text = status
        return ET.tostring(root, encoding="unicode")

    def parse_payload_status(self, xml_str: str) -> dict[str, Any]:
        """Parse PayloadStatusMessage into DroneOps payload state format."""
        root = self._parse_xml(xml_str, "PayloadStatusMessage")
        payload = self._find_required_node(root, "Payload")
        pointing = self._find_required_node(payload, "Pointing")
        azimuth = self._as_float(self._find_text(pointing, "AzimuthDeg", "0.0"), "azimuth")
        elevation = self._as_float(self._find_text(pointing, "ElevationDeg", "0.0"), "elevation")
        fov = self._as_float(self._find_text(payload, "FOVDeg", "0.0"), "fov", minimum=0.0)
        return {
            "uav_id": self._find_text(payload, "UAVId", ""),
            "sensor_type": self._find_text(payload, "SensorType", "UNKNOWN"),
            "pointing_angles": {"azimuth": azimuth, "elevation": elevation},
            "fov": fov,
            "operational_status": self._find_text(payload, "OperationalStatus", "UNKNOWN"),
            "timestamp": self._find_text(self._find_node(root, "Header"), "Timestamp", ""),
        }

    def build_payload_command(self, uav_id: str, command: dict[str, Any]) -> str:
        """Build PayloadCommandMessage for LOI 3 partner sensor control."""
        vehicle_id = self._ensure_non_empty_text(uav_id, "uav_id")
        if not isinstance(command, dict):
            raise ValueError("command must be a dictionary")
        command_name = self._ensure_non_empty_text(command.get("command_name", command.get("action")), "command_name")

        root = ET.Element(self._tag("PayloadCommandMessage"))
        header = ET.SubElement(root, self._tag("Header"))
        ET.SubElement(header, self._tag("MessageType")).text = "PayloadCommand"
        ET.SubElement(header, self._tag("Timestamp")).text = self._normalize_timestamp(command.get("timestamp"))

        command_el = ET.SubElement(root, self._tag("Command"))
        ET.SubElement(command_el, self._tag("UAVId")).text = vehicle_id
        ET.SubElement(command_el, self._tag("Name")).text = command_name
        params = ET.SubElement(command_el, self._tag("Parameters"))
        for key, value in sorted(command.items()):
            if key in {"uav_id", "command_name", "action", "timestamp"}:
                continue
            param_el = ET.SubElement(params, self._tag("Parameter"))
            param_el.set("key", str(key))
            param_el.text = str(value)
        return ET.tostring(root, encoding="unicode")

    def parse_payload_command(self, xml_str: str) -> dict[str, Any]:
        """Parse PayloadCommandMessage into executable command dictionary."""
        root = self._parse_xml(xml_str, "PayloadCommandMessage")
        command = self._find_required_node(root, "Command")
        parsed: dict[str, Any] = {
            "uav_id": self._find_text(command, "UAVId", ""),
            "command_name": self._find_text(command, "Name", ""),
            "timestamp": self._find_text(self._find_node(root, "Header"), "Timestamp", ""),
        }
        params_node = self._find_node(command, "Parameters")
        if params_node is not None:
            for node in self._find_all_nodes(params_node, "Parameter"):
                key = str(node.attrib.get("key", "")).strip()
                if not key:
                    continue
                parsed[key] = self._coerce_text_value((node.text or "").strip())
        return parsed

    def build_isr_product(self, uav_id: str, product: dict[str, Any]) -> str:
        """Build ISRProductMessage for LOI 1/2 intelligence product sharing."""
        vehicle_id = self._ensure_non_empty_text(uav_id, "uav_id")
        if not isinstance(product, dict):
            raise ValueError("product must be a dictionary")

        product_type = self._ensure_non_empty_text(product.get("product_type", "imagery"), "product_type")
        reference = self._ensure_non_empty_text(
            product.get("reference", product.get("uri", product.get("url"))),
            "reference",
        )
        classification = self._ensure_non_empty_text(product.get("classification", "UNCLASSIFIED"), "classification")

        root = ET.Element(self._tag("ISRProductMessage"))
        header = ET.SubElement(root, self._tag("Header"))
        ET.SubElement(header, self._tag("MessageType")).text = "ISRProduct"
        ET.SubElement(header, self._tag("Timestamp")).text = self._normalize_timestamp(product.get("timestamp"))

        payload = ET.SubElement(root, self._tag("ISRProduct"))
        ET.SubElement(payload, self._tag("UAVId")).text = vehicle_id
        ET.SubElement(payload, self._tag("ProductType")).text = product_type
        ET.SubElement(payload, self._tag("Reference")).text = reference
        ET.SubElement(payload, self._tag("Classification")).text = classification
        return ET.tostring(root, encoding="unicode")

    def parse_isr_product(self, xml_str: str) -> dict[str, Any]:
        """Parse ISRProductMessage into DroneOps ISR metadata format."""
        root = self._parse_xml(xml_str, "ISRProductMessage")
        isr = self._find_required_node(root, "ISRProduct")
        return {
            "uav_id": self._find_text(isr, "UAVId", ""),
            "product_type": self._find_text(isr, "ProductType", "imagery"),
            "reference": self._find_text(isr, "Reference", ""),
            "classification": self._find_text(isr, "Classification", "UNCLASSIFIED"),
            "timestamp": self._find_text(self._find_node(root, "Header"), "Timestamp", ""),
        }

    def _extract_position(self, status: dict[str, Any]) -> tuple[float, float, float]:
        raw_position = status.get("position", {})
        lat: Any = None
        lon: Any = None
        altitude: Any = status.get("altitude", status.get("relative_altitude", 0.0))

        if isinstance(raw_position, dict):
            lat = raw_position.get("latitude", raw_position.get("lat"))
            lon = raw_position.get("longitude", raw_position.get("lon"))
            if "altitude" in raw_position and "altitude" not in status:
                altitude = raw_position["altitude"]
        elif isinstance(raw_position, (list, tuple)) and len(raw_position) >= 2:
            lat = raw_position[0]
            lon = raw_position[1]
            if len(raw_position) >= 3 and "altitude" not in status:
                altitude = raw_position[2]
        else:
            lat = status.get("latitude", status.get("lat"))
            lon = status.get("longitude", status.get("lon"))

        latitude = self._as_float(lat, "latitude", minimum=-90.0, maximum=90.0)
        longitude = self._as_float(lon, "longitude", minimum=-180.0, maximum=180.0)
        altitude_m = self._as_float(altitude, "altitude")
        return latitude, longitude, altitude_m

    @staticmethod
    def _coerce_text_value(value: str) -> Any:
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def _normalize_heading(self, value: Any) -> float:
        heading = self._as_float(value, "heading")
        heading = heading % 360.0
        return 360.0 if heading == 0.0 and str(value) == "360" else heading

    def _normalize_timestamp(self, value: Any) -> str:
        if value is None:
            return datetime.now(timezone.utc).isoformat()
        text = str(value).strip()
        if not text:
            return datetime.now(timezone.utc).isoformat()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc).isoformat()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    def _parse_xml(self, xml_str: str, expected_root: str) -> ET.Element:
        text = str(xml_str or "").strip()
        if not text:
            raise ValueError("xml_str must be non-empty")
        root = ET.fromstring(text)
        expected_tag = self._tag(expected_root)
        if root.tag not in {expected_tag, expected_root}:
            raise ValueError(f"expected root element {expected_root}")
        return root

    def _tag(self, tag: str) -> str:
        return f"{{{self.namespace}}}{tag}"

    def _find_node(self, node: ET.Element | None, tag: str) -> ET.Element | None:
        if node is None:
            return None
        direct = node.find(self._tag(tag))
        if direct is not None:
            return direct
        return node.find(tag)

    def _find_all_nodes(self, node: ET.Element, tag: str) -> list[ET.Element]:
        namespaced = node.findall(self._tag(tag))
        if namespaced:
            return namespaced
        return node.findall(tag)

    def _find_required_node(self, node: ET.Element, tag: str) -> ET.Element:
        found = self._find_node(node, tag)
        if found is None:
            raise ValueError(f"missing required XML element: {tag}")
        return found

    def _find_text(self, node: ET.Element | None, tag: str, default: str = "") -> str:
        if node is None:
            return default
        child = self._find_node(node, tag)
        if child is None or child.text is None:
            return default
        return child.text.strip()

    @staticmethod
    def _ensure_non_empty_text(value: Any, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field_name} is required")
        return text

    @staticmethod
    def _as_float(
        value: Any,
        field_name: str,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} must be numeric") from None
        if minimum is not None and parsed < minimum:
            raise ValueError(f"{field_name} must be >= {minimum}")
        if maximum is not None and parsed > maximum:
            raise ValueError(f"{field_name} must be <= {maximum}")
        return parsed

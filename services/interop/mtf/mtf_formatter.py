"""APP-11-style XML-MTF formatter for NATO-aligned tactical message exchange."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any
from xml.etree import ElementTree as ET


class MTFFormatter:
    """Formats and parses a focused set of APP-11 message families."""

    SUPPORTED_TYPES = {"INTSUM", "SITREP", "OPREP3", "POSREP", "WARNORD"}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = dict(config or {})
        self.namespace = str(cfg.get("namespace", "urn:nato:mtf:app11d"))
        # Tactical default keeps outbound headers stable when caller omits originator.
        self.default_originator = str(
            cfg.get("originator") or os.environ.get("S3M_MTF_ORIGINATOR", "S3M INTEL CENTER")
        )
        self._serial_counter = int(cfg.get("start_serial", 1))
        ET.register_namespace("mtf", self.namespace)

    def format_message(
        self,
        report_type: str,
        content: dict[str, Any],
        originator: str,
        classification: str,
    ) -> str:
        canonical_type = self._canonical_report_type(report_type)
        if canonical_type not in self.SUPPORTED_TYPES:
            raise ValueError(f"Unsupported MTF report type: {report_type}")

        payload = dict(content or {})
        originator_value = str(originator or self.default_originator).strip() or self.default_originator
        classification_value = self._classification_to_nato(str(classification or "UNCLASSIFIED"))
        dtg = self._build_dtg(datetime.now(timezone.utc))
        serial = self._next_serial()

        root = ET.Element(self._q("message"))
        self._append_msgid(
            root=root,
            message_type=canonical_type,
            originator=originator_value,
            serial=serial,
            classification=classification_value,
            dtg=dtg,
        )

        body = ET.SubElement(root, self._q(canonical_type))
        self._append_msgid(
            root=body,
            message_type=canonical_type,
            originator=originator_value,
            serial=serial,
            classification=classification_value,
            dtg=dtg,
        )

        if canonical_type == "INTSUM":
            self._build_intsum(body, payload, dtg)
        elif canonical_type == "SITREP":
            self._build_sitrep(body, payload)
        elif canonical_type == "OPREP3":
            self._build_oprep3(body, payload)
        elif canonical_type == "POSREP":
            self._build_posrep(body, payload, dtg)
        elif canonical_type == "WARNORD":
            self._build_warnord(body, payload)

        return ET.tostring(root, encoding="unicode")

    def parse_message(self, xml_str: str) -> dict[str, Any]:
        root = ET.fromstring(xml_str)
        body = self._find_body(root)
        if body is None:
            raise ValueError("MTF message body not found")

        report_type = self._tag(body)
        if report_type not in self.SUPPORTED_TYPES:
            raise ValueError(f"Unsupported MTF message body: {report_type}")

        msgid = self._extract_msgid(body) or self._extract_msgid(root) or {}
        content: dict[str, Any]
        if report_type == "INTSUM":
            content = self._parse_intsum(body)
        elif report_type == "SITREP":
            content = self._parse_sitrep(body)
        elif report_type == "OPREP3":
            content = self._parse_oprep3(body)
        elif report_type == "POSREP":
            content = self._parse_posrep(body)
        else:
            content = self._parse_warnord(body)

        return {
            "message_type": report_type,
            "originator": msgid.get("originator", ""),
            "classification": msgid.get("classification", ""),
            "serial_number": msgid.get("serial", ""),
            "datetime_group": msgid.get("dtg", ""),
            "content": content,
        }

    @staticmethod
    def _build_dtg(dt: datetime) -> str:
        utc_dt = dt.astimezone(timezone.utc)
        return utc_dt.strftime("%d%H%MZ %b %Y").upper()

    @staticmethod
    def _classification_to_nato(s3m_class: str) -> str:
        mapping = {
            "UNCLASSIFIED": "UNCLASSIFIED",
            "FOUO": "NATO UNCLASSIFIED",
            "CONFIDENTIAL": "NATO CONFIDENTIAL",
            "SECRET": "NATO SECRET",
            "TOP_SECRET": "COSMIC TOP SECRET",
        }
        return mapping.get(str(s3m_class).upper(), str(s3m_class).upper())

    def _q(self, local_name: str) -> str:
        return f"{{{self.namespace}}}{local_name}"

    def _next_serial(self) -> str:
        serial = f"{self._serial_counter:06d}"
        self._serial_counter += 1
        return serial

    def _append_msgid(
        self,
        root: ET.Element,
        message_type: str,
        originator: str,
        serial: str,
        classification: str,
        dtg: str,
    ) -> None:
        msgid = ET.SubElement(root, self._q("MSGID"))
        ET.SubElement(msgid, self._q("MSGTYPE")).text = message_type
        ET.SubElement(msgid, self._q("ORIGINATOR")).text = originator
        ET.SubElement(msgid, self._q("SERIAL")).text = serial
        ET.SubElement(msgid, self._q("CLASSIFICATION")).text = classification
        ET.SubElement(msgid, self._q("DTG")).text = dtg

    def _build_intsum(self, body: ET.Element, payload: dict[str, Any], dtg: str) -> None:
        period = ET.SubElement(body, self._q("PERIOD"))
        ET.SubElement(period, self._q("FROM")).text = str(payload.get("period_from", dtg))
        ET.SubElement(period, self._q("TO")).text = str(payload.get("period_to", dtg))

        situation = ET.SubElement(body, self._q("SITUATION"))
        ET.SubElement(situation, self._q("GENTEXT")).text = str(
            payload.get("summary_text", payload.get("summary", ""))
        )

        assessment = ET.SubElement(body, self._q("ASSESSMENT"))
        ET.SubElement(assessment, self._q("GENTEXT")).text = str(
            payload.get("assessment_text", payload.get("assessment", ""))
        )

    def _build_sitrep(self, body: ET.Element, payload: dict[str, Any]) -> None:
        situation = ET.SubElement(body, self._q("SITUATION"))
        ET.SubElement(situation, self._q("GENTEXT")).text = str(payload.get("sitrep_text", ""))

        operations = ET.SubElement(body, self._q("OPERATIONS"))
        ET.SubElement(operations, self._q("GENTEXT")).text = str(payload.get("ops_text", ""))

        logistics = ET.SubElement(body, self._q("LOGISTICS"))
        ET.SubElement(logistics, self._q("GENTEXT")).text = str(payload.get("logistics_text", ""))

    def _build_oprep3(self, body: ET.Element, payload: dict[str, Any]) -> None:
        incident = ET.SubElement(body, self._q("INCIDENT"))
        ET.SubElement(incident, self._q("GENTEXT")).text = str(payload.get("incident_description", ""))

        lat, lon, _ = self._coerce_coords(payload)
        location = ET.SubElement(body, self._q("LOCATION"))
        ET.SubElement(location, self._q("COORDS")).text = f"{lat},{lon}"

    def _build_posrep(self, body: ET.Element, payload: dict[str, Any], dtg: str) -> None:
        ET.SubElement(body, self._q("UNITID")).text = str(payload.get("unit_designation", ""))
        lat, lon, alt = self._coerce_coords(payload)
        location = ET.SubElement(body, self._q("LOCATION"))
        ET.SubElement(location, self._q("COORDS")).text = f"{lat},{lon},{alt}"
        ET.SubElement(body, self._q("DTG")).text = str(payload.get("datetime_group", dtg))
        ET.SubElement(body, self._q("ACTIVITY")).text = str(payload.get("current_activity", ""))

    def _build_warnord(self, body: ET.Element, payload: dict[str, Any]) -> None:
        situation = ET.SubElement(body, self._q("SITUATION"))
        ET.SubElement(situation, self._q("GENTEXT")).text = str(payload.get("situation", ""))

        mission = ET.SubElement(body, self._q("MISSION"))
        ET.SubElement(mission, self._q("GENTEXT")).text = str(payload.get("mission_statement", ""))

        execution = ET.SubElement(body, self._q("EXECUTION"))
        ET.SubElement(execution, self._q("GENTEXT")).text = str(payload.get("execution_details", ""))

    @staticmethod
    def _canonical_report_type(report_type: str) -> str:
        value = str(report_type or "").strip().upper()
        if value == "OPREP-3":
            return "OPREP3"
        return value

    @staticmethod
    def _tag(node: ET.Element) -> str:
        return node.tag.rsplit("}", 1)[-1]

    @classmethod
    def _find(cls, root: ET.Element, local_name: str) -> ET.Element | None:
        for node in root.iter():
            if cls._tag(node) == local_name:
                return node
        return None

    @classmethod
    def _find_child(cls, root: ET.Element, local_name: str) -> ET.Element | None:
        for node in list(root):
            if cls._tag(node) == local_name:
                return node
        return None

    @classmethod
    def _text(cls, root: ET.Element, local_name: str, default: str = "") -> str:
        node = cls._find(root, local_name)
        if node is None or node.text is None:
            return default
        return node.text.strip()

    def _find_body(self, root: ET.Element) -> ET.Element | None:
        for child in list(root):
            if self._tag(child) in self.SUPPORTED_TYPES:
                return child
        return None

    def _extract_msgid(self, root: ET.Element) -> dict[str, str] | None:
        msgid = self._find_child(root, "MSGID")
        if msgid is None:
            return None
        return {
            "message_type": self._text(msgid, "MSGTYPE"),
            "originator": self._text(msgid, "ORIGINATOR"),
            "serial": self._text(msgid, "SERIAL"),
            "classification": self._text(msgid, "CLASSIFICATION"),
            "dtg": self._text(msgid, "DTG"),
        }

    def _parse_intsum(self, body: ET.Element) -> dict[str, Any]:
        period = self._find_child(body, "PERIOD")
        situation_node = self._find_child(body, "SITUATION")
        assessment_node = self._find_child(body, "ASSESSMENT")
        return {
            "period_from": self._text(period if period is not None else body, "FROM"),
            "period_to": self._text(period if period is not None else body, "TO"),
            "summary_text": self._text(
                situation_node if situation_node is not None else body,
                "GENTEXT",
            ),
            "assessment_text": self._text(
                assessment_node if assessment_node is not None else body,
                "GENTEXT",
            ),
        }

    def _parse_sitrep(self, body: ET.Element) -> dict[str, Any]:
        situation_node = self._find_child(body, "SITUATION")
        operations_node = self._find_child(body, "OPERATIONS")
        logistics_node = self._find_child(body, "LOGISTICS")
        return {
            "sitrep_text": self._text(situation_node if situation_node is not None else body, "GENTEXT"),
            "ops_text": self._text(operations_node if operations_node is not None else body, "GENTEXT"),
            "logistics_text": self._text(logistics_node if logistics_node is not None else body, "GENTEXT"),
        }

    def _parse_oprep3(self, body: ET.Element) -> dict[str, Any]:
        location_node = self._find_child(body, "LOCATION")
        incident_node = self._find_child(body, "INCIDENT")
        coords = self._text(location_node if location_node is not None else body, "COORDS")
        lat, lon, _ = self._parse_coords_text(coords)
        return {
            "incident_description": self._text(incident_node if incident_node is not None else body, "GENTEXT"),
            "lat": lat,
            "lon": lon,
        }

    def _parse_posrep(self, body: ET.Element) -> dict[str, Any]:
        location_node = self._find_child(body, "LOCATION")
        coords = self._text(location_node if location_node is not None else body, "COORDS")
        lat, lon, alt = self._parse_coords_text(coords)
        return {
            "unit_designation": self._text(body, "UNITID"),
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "datetime_group": self._text(body, "DTG"),
            "current_activity": self._text(body, "ACTIVITY"),
        }

    def _parse_warnord(self, body: ET.Element) -> dict[str, Any]:
        situation_node = self._find_child(body, "SITUATION")
        mission_node = self._find_child(body, "MISSION")
        execution_node = self._find_child(body, "EXECUTION")
        return {
            "situation": self._text(situation_node if situation_node is not None else body, "GENTEXT"),
            "mission_statement": self._text(mission_node if mission_node is not None else body, "GENTEXT"),
            "execution_details": self._text(execution_node if execution_node is not None else body, "GENTEXT"),
        }

    @staticmethod
    def _coerce_coords(payload: dict[str, Any]) -> tuple[float, float, float]:
        lat = float(payload.get("lat", 0.0))
        lon = float(payload.get("lon", 0.0))
        alt = float(payload.get("alt", 0.0))
        return lat, lon, alt

    @staticmethod
    def _parse_coords_text(text: str) -> tuple[float, float, float]:
        parts = [part.strip() for part in str(text).split(",") if part.strip()]
        values: list[float] = []
        for part in parts[:3]:
            try:
                values.append(float(part))
            except ValueError:
                values.append(0.0)
        while len(values) < 3:
            values.append(0.0)
        return values[0], values[1], values[2]

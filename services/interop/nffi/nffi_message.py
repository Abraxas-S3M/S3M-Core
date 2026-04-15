"""NFFI v1.4 XML message builder/parser for blue-force tactical tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List
import xml.etree.ElementTree as ET


class NFFIMessageBuilder:
    """Build and parse STANAG 5527 NFFI payloads for coalition sharing."""

    namespace = "urn:nffi:xml:1.4"

    def __init__(self) -> None:
        ET.register_namespace("", self.namespace)

    def build_message(self, tracks: List[dict], country_iso3: str, system_id: str) -> str:
        country = str(country_iso3 or "").strip().upper()
        if len(country) != 3 or not country.isalpha():
            raise ValueError("country_iso3 must be a 3-letter ISO-3166 alpha-3 code")
        system = str(system_id or "").strip()
        if not system:
            raise ValueError("system_id is required")

        root = ET.Element(self._tag("nffi"))
        for track in tracks:
            if not self._is_friendly_track(track):
                continue

            position = track.get("position", [0.0, 0.0, 0.0])
            if not isinstance(position, (list, tuple)) or len(position) != 3:
                continue
            try:
                lat = float(position[0])
                lon = float(position[1])
                alt = float(position[2])
            except (TypeError, ValueError):
                continue

            speed = float(track.get("speed", 0.0) or 0.0)
            course = float(track.get("course", 0.0) or 0.0)
            unit_id = str(track.get("unit_id", "")).strip()
            if not unit_id:
                continue
            status = self._status_to_nffi(str(track.get("status", "active")))
            unit_designation = str(track.get("unit_callsign") or track.get("callsign") or track.get("role") or unit_id)
            unit_symbol = str(track.get("sidc") or track.get("unit_symbol") or self._role_to_sidc(track.get("role")))

            track_el = ET.SubElement(root, self._tag("track"))
            positional = ET.SubElement(track_el, self._tag("positionalData"))
            ET.SubElement(positional, self._tag("trackSource")).text = country
            ET.SubElement(positional, self._tag("systemId")).text = system
            ET.SubElement(positional, self._tag("deviceId")).text = unit_id
            ET.SubElement(positional, self._tag("dateTime")).text = self._iso_to_nffi_datetime(
                track.get("timestamp") or track.get("updated_at")
            )
            ET.SubElement(positional, self._tag("latitude")).text = f"{lat:.8f}"
            ET.SubElement(positional, self._tag("longitude")).text = f"{lon:.8f}"
            ET.SubElement(positional, self._tag("altitude")).text = f"{alt:.3f}"
            ET.SubElement(positional, self._tag("speed")).text = f"{speed:.3f}"
            ET.SubElement(positional, self._tag("course")).text = f"{course:.3f}"

            identification = ET.SubElement(track_el, self._tag("identificationData"))
            ET.SubElement(identification, self._tag("unitSymbol")).text = unit_symbol
            ET.SubElement(identification, self._tag("unitDesignation")).text = unit_designation

            op_data = ET.SubElement(track_el, self._tag("operStatusData"))
            ET.SubElement(op_data, self._tag("operationalStatus")).text = status

        return ET.tostring(root, encoding="unicode")

    def parse_message(self, xml_str: str) -> List[dict]:
        if not str(xml_str or "").strip():
            return []
        root = ET.fromstring(xml_str)
        tracks: List[dict] = []

        track_nodes = root.findall(f".//{self._tag('track')}")
        if not track_nodes:
            track_nodes = root.findall(".//track")

        for track_el in track_nodes:
            pos = self._find_node(track_el, "positionalData")
            ident = self._find_node(track_el, "identificationData")
            oper = self._find_node(track_el, "operStatusData")
            if pos is None:
                continue

            try:
                lat = float(self._find_text(pos, "latitude", "0.0"))
                lon = float(self._find_text(pos, "longitude", "0.0"))
                alt = float(self._find_text(pos, "altitude", "0.0"))
                speed = float(self._find_text(pos, "speed", "0.0"))
                course = float(self._find_text(pos, "course", "0.0"))
            except ValueError:
                continue

            nffi_status = self._find_text(oper, "operationalStatus", "OPERATIONAL") if oper is not None else "OPERATIONAL"
            unit_id = self._find_text(pos, "deviceId", "")
            designation = self._find_text(ident, "unitDesignation", unit_id) if ident is not None else unit_id
            tracks.append(
                {
                    "unit_id": unit_id,
                    "position": [lat, lon, alt],
                    "role": designation or "friendly",
                    "status": self._nffi_to_status(nffi_status),
                    "updated_at": self._nffi_datetime_to_iso(self._find_text(pos, "dateTime", "")),
                    "timestamp": self._nffi_datetime_to_iso(self._find_text(pos, "dateTime", "")),
                    "affiliation": "friendly",
                    "source_protocol": "nffi",
                    "source_country_iso3": self._find_text(pos, "trackSource", ""),
                    "system_id": self._find_text(pos, "systemId", ""),
                    "sidc": self._find_text(ident, "unitSymbol", "") if ident is not None else "",
                    "speed": speed,
                    "course": course,
                }
            )

        return tracks

    def _status_to_nffi(self, s3m_status: str) -> str:
        value = str(s3m_status or "").strip().lower()
        if value == "damaged":
            return "DEGRADED"
        if value == "destroyed":
            return "DESTROYED"
        return "OPERATIONAL"

    def _nffi_to_status(self, nffi_status: str) -> str:
        value = str(nffi_status or "").strip().upper()
        if value == "DEGRADED":
            return "damaged"
        if value == "DESTROYED":
            return "destroyed"
        return "active"

    def _tag(self, tag: str) -> str:
        return f"{{{self.namespace}}}{tag}"

    def _find_node(self, node: ET.Element, tag: str) -> ET.Element | None:
        return node.find(self._tag(tag)) or node.find(tag)

    def _find_text(self, node: ET.Element | None, tag: str, default: str = "") -> str:
        if node is None:
            return default
        child = node.find(self._tag(tag)) or node.find(tag)
        if child is None or child.text is None:
            return default
        return child.text.strip()

    def _iso_to_nffi_datetime(self, value: str | None) -> str:
        if not value:
            dt = datetime.now(timezone.utc)
            return dt.strftime("%Y%m%d%H%M%S")
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")

    def _nffi_datetime_to_iso(self, value: str) -> str:
        text = str(value or "").strip()
        try:
            dt = datetime.strptime(text, "%Y%m%d%H%M%S")
        except ValueError:
            return datetime.now(timezone.utc).isoformat()
        return dt.replace(tzinfo=timezone.utc).isoformat()

    def _is_friendly_track(self, track: dict) -> bool:
        if not isinstance(track, dict):
            return False
        fields = [
            str(track.get("affiliation", "")),
            str(track.get("allegiance", "")),
            str(track.get("iff_status", "")),
            str(track.get("classification", "")),
            str(track.get("role", "")),
            str(track.get("side", "")),
        ]
        marker = " ".join(fields).lower()
        hostile_markers = ("hostile", "enemy", "adversary", "red", "opfor")
        friendly_markers = ("friendly", "blue", "coalition", "ally", "allied", "friend")
        if any(token in marker for token in hostile_markers):
            return False
        if any(token in marker for token in friendly_markers):
            return True
        # Tactical safety fallback: Force Awareness feed is blue-force by design.
        return True

    def _role_to_sidc(self, role: object) -> str:
        text = str(role or "").lower()
        if "armor" in text or "tank" in text:
            return "SFGPUCA----K---"
        if "air" in text or "uav" in text:
            return "SFGPUCI----K---"
        if "nav" in text or "ship" in text:
            return "SFGPUCNS---K---"
        return "SFGPUCI----K---"

"""Cursor-on-Target event XML factory for tactical force-track exchange."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import xml.etree.ElementTree as ET


class CotEventFactory:
    """Build and parse CoT 2.0 event XML with strict tactical input validation."""

    _MAX_XML_BYTES = 256_000

    def __init__(self, config: dict | None = None):
        cfg = dict(config or {})
        if isinstance(cfg.get("cot"), dict):
            cfg = dict(cfg["cot"])
        self.stale_seconds = max(1, int(cfg.get("stale_seconds", 120)))
        self.callsign_prefix = str(cfg.get("callsign_prefix", "S3M")).strip() or "S3M"

    def build_event(self, track: dict) -> str:
        """Generate CoT event XML from S3M track data."""
        if not isinstance(track, dict):
            raise ValueError("track must be a dictionary")

        uid = str(track.get("uid") or track.get("unit_id") or track.get("id") or "").strip()
        if not uid:
            raise ValueError("track requires uid/unit_id/id")

        lat, lon, hae = self._extract_position(track)
        self._validate_coordinates(lat, lon, hae)

        affiliation = self._normalize_affiliation(
            track.get("affiliation") or track.get("allegiance") or track.get("identity")
        )
        domain = self._normalize_domain(track.get("domain") or self._infer_domain(track))
        entity_type = str(track.get("entity_type") or track.get("role") or track.get("type") or "unknown")

        cot_type = self._s3m_type_to_cot(entity_type=entity_type, affiliation=affiliation, domain=domain)
        sidc = str(track.get("sidc") or "").strip().upper()
        cot_type = self._extend_with_sidc(cot_type, sidc)

        course = float(track.get("heading", track.get("course", 0.0)))
        speed = max(0.0, float(track.get("speed", track.get("speed_m_s", 0.0))))

        event_time = self._parse_time(track.get("time"))
        stale_seconds = max(1, int(track.get("stale_seconds", self.stale_seconds)))
        stale_time = event_time + timedelta(seconds=stale_seconds)

        callsign = str(track.get("callsign") or track.get("name") or f"{self.callsign_prefix}-{uid}").strip()
        if not callsign:
            callsign = f"{self.callsign_prefix}-{uid}"

        event = ET.Element(
            "event",
            {
                "version": "2.0",
                "uid": uid,
                "type": cot_type,
                "time": self._iso8601_utc(event_time),
                "start": self._iso8601_utc(event_time),
                "stale": self._iso8601_utc(stale_time),
                "how": "m-g",
            },
        )
        ET.SubElement(
            event,
            "point",
            {
                "lat": f"{lat:.7f}",
                "lon": f"{lon:.7f}",
                "hae": f"{hae:.2f}",
                "ce": "10.0",
                "le": "10.0",
            },
        )
        detail = ET.SubElement(event, "detail")
        ET.SubElement(detail, "contact", {"callsign": callsign})
        ET.SubElement(detail, "track", {"course": f"{course:.2f}", "speed": f"{speed:.2f}"})
        ET.SubElement(detail, "__group", {"name": affiliation, "role": "Team Member"})
        return ET.tostring(event, encoding="unicode")

    def parse_event(self, xml_str: str) -> dict:
        """Parse CoT event XML back to S3M track dictionary fields."""
        root = self._safe_parse_xml(xml_str)
        if root.tag != "event":
            raise ValueError("CoT XML root must be <event>")

        uid = str(root.attrib.get("uid", "")).strip()
        if not uid:
            raise ValueError("CoT event missing uid")

        cot_type = str(root.attrib.get("type", "a-u-G")).strip() or "a-u-G"
        entity_type, mapped_affiliation, _domain = self._cot_to_s3m_type(cot_type)

        point = root.find("point")
        if point is None:
            raise ValueError("CoT event missing <point>")

        lat = float(point.attrib.get("lat", "0.0"))
        lon = float(point.attrib.get("lon", "0.0"))
        hae = float(point.attrib.get("hae", "0.0"))
        self._validate_coordinates(lat, lon, hae)

        detail = root.find("detail")
        callsign = ""
        course = 0.0
        speed = 0.0
        affiliation = mapped_affiliation
        if detail is not None:
            contact = detail.find("contact")
            if contact is not None:
                callsign = str(contact.attrib.get("callsign", "")).strip()
            track = detail.find("track")
            if track is not None:
                course = float(track.attrib.get("course", "0.0"))
                speed = float(track.attrib.get("speed", "0.0"))
            group = detail.find("__group")
            if group is not None:
                affiliation = self._normalize_affiliation(group.attrib.get("name", affiliation))

        return {
            "uid": uid,
            "type": cot_type,
            "lat": lat,
            "lon": lon,
            "hae": hae,
            "course": course,
            "speed": speed,
            "callsign": callsign,
            "affiliation": affiliation,
            "entity_type": entity_type,
            "time": str(root.attrib.get("time", "")),
            "stale": str(root.attrib.get("stale", "")),
        }

    def _s3m_type_to_cot(self, entity_type: str, affiliation: str, domain: str) -> str:
        """Map S3M entity and allegiance fields to CoT type tree."""
        _ = entity_type
        aff = self._normalize_affiliation(affiliation)
        dom = self._normalize_domain(domain)
        if aff == "friendly":
            return {"air": "a-f-A", "ground": "a-f-G", "surface": "a-f-S"}[dom]
        if aff == "hostile":
            return {"air": "a-h-A", "ground": "a-h-G", "surface": "a-h-S"}[dom]
        if aff == "neutral":
            return "a-n-G"
        return "a-u-G"

    def _cot_to_s3m_type(self, cot_type: str) -> tuple[str, str, str]:
        """Reverse-map CoT type to (entity_type, affiliation, domain)."""
        raw = str(cot_type or "a-u-G").strip()
        parts = raw.split("-")
        aff_char = parts[1].lower() if len(parts) >= 2 else "u"
        dom_char = parts[2].upper() if len(parts) >= 3 else "G"

        affiliation = {
            "f": "friendly",
            "h": "hostile",
            "n": "neutral",
            "u": "unknown",
        }.get(aff_char, "unknown")
        domain = {"A": "air", "G": "ground", "S": "surface"}.get(dom_char, "ground")

        entity_type = f"{affiliation}_{domain}"
        if len(parts) >= 5 and parts[3].upper() == "U" and parts[4].upper() == "C":
            entity_type = "unit_combat"
        elif len(parts) >= 5 and parts[3].upper() == "M" and parts[4].upper() == "F":
            entity_type = "military_fixed_wing"
        return (entity_type, affiliation, domain)

    def _extract_position(self, track: dict) -> tuple[float, float, float]:
        pos = track.get("position")
        if isinstance(pos, (list, tuple)) and len(pos) >= 3:
            lat = float(pos[0])
            lon = float(pos[1])
            hae = float(pos[2])
            return lat, lon, hae
        if isinstance(pos, dict):
            lat = float(pos.get("lat", pos.get("latitude", 0.0)))
            lon = float(pos.get("lon", pos.get("longitude", 0.0)))
            hae = float(
                pos.get(
                    "hae",
                    pos.get(
                        "alt",
                        pos.get("altitude", pos.get("msl", 0.0)),
                    ),
                )
            )
            return lat, lon, hae
        lat = float(track.get("lat", track.get("latitude", 0.0)))
        lon = float(track.get("lon", track.get("longitude", 0.0)))
        # Tactical note: CoT requires HAE/WGS84 altitude; if only MSL is supplied by
        # a sensor source we forward the numeric value to preserve track continuity.
        hae = float(track.get("hae", track.get("alt", track.get("altitude", track.get("msl", 0.0)))))
        return lat, lon, hae

    def _infer_domain(self, track: dict) -> str:
        text = " ".join(
            [
                str(track.get("domain", "")),
                str(track.get("entity_type", "")),
                str(track.get("role", "")),
                str(track.get("type", "")),
            ]
        ).lower()
        if "air" in text or "uav" in text or "aircraft" in text:
            return "air"
        if "surface" in text or "ship" in text or "vessel" in text:
            return "surface"
        return "ground"

    @staticmethod
    def _normalize_affiliation(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"friendly", "ally", "blue", "f"}:
            return "friendly"
        if text in {"hostile", "enemy", "red", "h"}:
            return "hostile"
        if text in {"neutral", "n"}:
            return "neutral"
        if text in {"unknown", "u"}:
            return "unknown"
        return "unknown"

    @staticmethod
    def _normalize_domain(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"air", "aerial", "a"}:
            return "air"
        if text in {"surface", "maritime", "sea", "s"}:
            return "surface"
        return "ground"

    @staticmethod
    def _validate_coordinates(lat: float, lon: float, hae: float) -> None:
        if not (-90.0 <= float(lat) <= 90.0):
            raise ValueError("latitude out of range")
        if not (-180.0 <= float(lon) <= 180.0):
            raise ValueError("longitude out of range")
        if not (-10000.0 <= float(hae) <= 100000.0):
            raise ValueError("HAE altitude out of range")

    @staticmethod
    def _iso8601_utc(ts: datetime) -> str:
        return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if value is None or value == "":
            return datetime.now(timezone.utc)
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("invalid ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _safe_parse_xml(self, xml_str: str) -> ET.Element:
        if not isinstance(xml_str, str):
            raise ValueError("xml_str must be a string")
        raw = xml_str.strip()
        if not raw:
            raise ValueError("xml_str is empty")
        if len(raw.encode("utf-8")) > self._MAX_XML_BYTES:
            raise ValueError("xml_str exceeds size limit")
        lowered = raw.lower()
        if "<!doctype" in lowered or "<!entity" in lowered:
            raise ValueError("unsafe XML declaration is not allowed")
        try:
            return ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ValueError("invalid CoT XML") from exc

    @staticmethod
    def _extend_with_sidc(cot_type: str, sidc: str) -> str:
        if not sidc:
            return cot_type
        if len(sidc) >= 16:
            function_id = sidc[10:16]
            chars = [ch for ch in function_id if ch.isalnum()]
            if len(chars) >= 2:
                return f"{cot_type}-{chars[0].upper()}-{chars[1].upper()}"
        return cot_type


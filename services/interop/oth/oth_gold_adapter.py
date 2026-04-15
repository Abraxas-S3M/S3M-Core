"""OTH-Gold adapter for maritime/air track interoperability exchanges.

Military/tactical context:
This adapter normalizes S3M maritime tracks into OTH-Gold XML so coalition
command systems can share over-the-horizon contacts during naval operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


class OTHGoldAdapter:
    """Converts S3M maritime tracks to/from OTH-Gold XML and TCP transport."""

    OTH_VERSION = "3.0"
    MPS_PER_KNOT = 0.514444

    _IDENTITY_MAP = {
        "friendly": "FRIEND",
        "hostile": "HOSTILE",
        "neutral": "NEUTRAL",
        "unknown": "UNKNOWN",
    }
    _IDENTITY_REVERSE_MAP = {value: key for key, value in _IDENTITY_MAP.items()}

    _PLATFORM_MAP = {
        "FRIENDLY_SHIP": "SURFACE_COMBATANT",
        "ENEMY_SHIP": "SURFACE_COMBATANT",
        "CIVILIAN": "MERCHANT",
    }
    _PLATFORM_REVERSE_MAP = {
        "SURFACE_COMBATANT": "FRIENDLY_SHIP",
        "SUBMARINE": "SUBMARINE",
        "MERCHANT": "CIVILIAN",
        "FISHING": "CIVILIAN",
    }

    def __init__(self) -> None:
        self.gateway_url: Optional[str] = None
        self.connected = False
        self._socket: Optional[socket.socket] = None
        self._receive_buffer = ""
        self._published_messages = 0
        self._published_tracks = 0
        self._received_tracks_total = 0

    @staticmethod
    def _tag(node: ET.Element) -> str:
        return node.tag.rsplit("}", 1)[-1]

    @classmethod
    def _find(cls, root: ET.Element, local_name: str) -> Optional[ET.Element]:
        for node in root.iter():
            if cls._tag(node) == local_name:
                return node
        return None

    @classmethod
    def _find_text(cls, root: ET.Element, local_name: str, default: str = "") -> str:
        node = cls._find(root, local_name)
        if node is None or node.text is None:
            return default
        return node.text.strip()

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_classification(value: Any) -> str:
        normalized = str(value or "UNCLASSIFIED").strip().upper()
        if normalized in {"UNCLASSIFIED", "CONFIDENTIAL", "SECRET"}:
            return normalized
        return "UNCLASSIFIED"

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _extract_track_id(self, track: Dict[str, Any], index: int) -> str:
        raw = (
            track.get("track_id")
            or track.get("trackNumber")
            or track.get("entity_id")
            or track.get("id")
            or track.get("mmsi")
        )
        if raw is None:
            return f"oth-track-{index}"
        return str(raw)

    def _extract_position(self, track: Dict[str, Any]) -> tuple[float, float]:
        pos = track.get("position", {})
        if isinstance(pos, dict):
            lat = self._safe_float(pos.get("lat", pos.get("latitude", track.get("latitude", 0.0))), 0.0)
            lon = self._safe_float(pos.get("lon", pos.get("longitude", track.get("longitude", 0.0))), 0.0)
            return (lat, lon)
        return (
            self._safe_float(track.get("latitude", 0.0), 0.0),
            self._safe_float(track.get("longitude", 0.0), 0.0),
        )

    def _extract_course_speed(self, track: Dict[str, Any]) -> tuple[float, float]:
        kinematics = track.get("kinematics", {})
        if not isinstance(kinematics, dict):
            kinematics = {}
        course = self._safe_float(
            kinematics.get("course", track.get("course_deg", track.get("course", track.get("heading", 0.0)))),
            0.0,
        )
        speed_mps = self._safe_float(
            kinematics.get("speed_mps", track.get("speed_mps", track.get("speed", 0.0))),
            0.0,
        )
        return (course, speed_mps)

    def _extract_platform(self, track: Dict[str, Any]) -> tuple[str, str, str]:
        platform = track.get("platform", {})
        if not isinstance(platform, dict):
            platform = {}

        entity_type = str(track.get("entity_type", track.get("platform_type", ""))).strip().upper()
        platform_type = str(platform.get("type", "")).strip().upper()
        if not platform_type:
            platform_type = self._platform_type_map(entity_type)
        if not platform_type:
            platform_type = "UNKNOWN"

        nationality = str(
            platform.get("nationality", track.get("nationality", track.get("country_code", "UNK")))
        ).strip().upper()
        if not nationality:
            nationality = "UNK"
        if len(nationality) > 3:
            nationality = nationality[:3]

        hull_number = str(
            platform.get(
                "hullNumber",
                track.get("hull_number", track.get("hullNumber", track.get("platform_id", ""))),
            )
        ).strip()
        return (platform_type, nationality, hull_number)

    def _extract_observation(self, track: Dict[str, Any]) -> tuple[str, str]:
        observation = track.get("observation", {})
        if not isinstance(observation, dict):
            observation = {}
        date_time = str(
            observation.get(
                "dateTime",
                track.get("timestamp", track.get("date_time", track.get("observed_at", self._utc_now_iso()))),
            )
        ).strip()
        if not date_time:
            date_time = self._utc_now_iso()
        source = str(observation.get("source", track.get("source", "S3M"))).strip() or "S3M"
        return (date_time, source)

    def _is_maritime_track(self, track: Dict[str, Any]) -> bool:
        if bool(track.get("is_maritime")):
            return True

        domain = track.get("domain")
        domain_text = str(domain or "").strip().lower()
        if domain == 3 or domain_text in {"3", "maritime", "surface", "sea"}:
            return True

        platform = track.get("platform", {})
        platform_type = ""
        if isinstance(platform, dict):
            platform_type = str(platform.get("type", "")).strip().upper()
        entity_type = str(track.get("entity_type", track.get("platform_type", ""))).strip().upper()
        maritime_tokens = {
            "SHIP",
            "SURFACE",
            "SUBMARINE",
            "VESSEL",
            "MERCHANT",
            "FISHING",
            "NAVAL",
        }
        joined = f"{entity_type} {platform_type}"
        if any(token in joined for token in maritime_tokens):
            return True

        return bool(track.get("mmsi") or track.get("hull_number") or (isinstance(platform, dict) and platform.get("hullNumber")))

    def build_message(self, tracks: List[Dict[str, Any]]) -> str:
        """Convert S3M maritime tracks into OTH-Gold XML."""
        root = ET.Element("OTHGold", {"version": self.OTH_VERSION})

        for index, track in enumerate(list(tracks or [])):
            if not isinstance(track, dict) or not self._is_maritime_track(track):
                continue

            # Tactical interop rule: OTH-Gold channel should only carry maritime
            # tracks to avoid polluting coalition naval COP feeds.
            track_node = ET.SubElement(root, "track")
            ET.SubElement(track_node, "trackNumber").text = self._extract_track_id(track, index)
            ET.SubElement(track_node, "identity").text = self._identity_map(str(track.get("affiliation", "unknown")))
            ET.SubElement(track_node, "classification").text = self._normalize_classification(
                track.get("classification", "UNCLASSIFIED")
            )

            lat, lon = self._extract_position(track)
            position = ET.SubElement(track_node, "position")
            ET.SubElement(position, "latitude").text = f"{lat:.8f}"
            ET.SubElement(position, "longitude").text = f"{lon:.8f}"

            course_deg, speed_mps = self._extract_course_speed(track)
            speed_knots = speed_mps / self.MPS_PER_KNOT
            kinematics = ET.SubElement(track_node, "kinematics")
            ET.SubElement(kinematics, "course").text = f"{course_deg:.3f}"
            ET.SubElement(kinematics, "speed").text = f"{speed_knots:.3f}"

            platform_type, nationality, hull_number = self._extract_platform(track)
            platform = ET.SubElement(track_node, "platform")
            ET.SubElement(platform, "type").text = platform_type
            ET.SubElement(platform, "nationality").text = nationality
            ET.SubElement(platform, "hullNumber").text = hull_number

            date_time, source = self._extract_observation(track)
            observation = ET.SubElement(track_node, "observation")
            ET.SubElement(observation, "dateTime").text = date_time
            ET.SubElement(observation, "source").text = source

        return ET.tostring(root, encoding="unicode")

    def parse_message(self, xml_str: str) -> List[Dict[str, Any]]:
        """Parse OTH-Gold XML payload into S3M track dictionaries."""
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return []

        parsed_tracks: List[Dict[str, Any]] = []
        track_nodes = root.findall(".//{*}track")
        if not track_nodes:
            track_nodes = root.findall("track")
        for track_node in track_nodes:
            track_number = self._find_text(track_node, "trackNumber", "")
            identity = self._find_text(track_node, "identity", "UNKNOWN").upper()
            affiliation = self._IDENTITY_REVERSE_MAP.get(identity, "unknown")
            classification = self._normalize_classification(self._find_text(track_node, "classification", "UNCLASSIFIED"))

            lat = self._safe_float(self._find_text(track_node, "latitude", "0.0"), 0.0)
            lon = self._safe_float(self._find_text(track_node, "longitude", "0.0"), 0.0)
            course_deg = self._safe_float(self._find_text(track_node, "course", "0.0"), 0.0)
            speed_knots = self._safe_float(self._find_text(track_node, "speed", "0.0"), 0.0)
            speed_mps = speed_knots * self.MPS_PER_KNOT

            platform_type = self._find_text(track_node, "type", "UNKNOWN").upper()
            entity_type = self._PLATFORM_REVERSE_MAP.get(platform_type, platform_type)
            nationality = self._find_text(track_node, "nationality", "UNK").upper()
            hull_number = self._find_text(track_node, "hullNumber", "")

            date_time = self._find_text(track_node, "dateTime", self._utc_now_iso())
            source = self._find_text(track_node, "source", "OTH-GOLD")

            parsed_tracks.append(
                {
                    "track_id": track_number,
                    "affiliation": affiliation,
                    "classification": classification,
                    "entity_type": entity_type,
                    "domain": "maritime",
                    "position": {"lat": lat, "lon": lon},
                    "kinematics": {"course_deg": course_deg, "speed_mps": speed_mps},
                    "course_deg": course_deg,
                    "speed_mps": speed_mps,
                    "nationality": nationality,
                    "hull_number": hull_number,
                    "observation": {"date_time": date_time, "source": source},
                    "timestamp": date_time,
                    "source": source,
                }
            )

        return parsed_tracks

    def _identity_map(self, affiliation: str) -> str:
        key = str(affiliation or "unknown").strip().lower()
        return self._IDENTITY_MAP.get(key, "UNKNOWN")

    def _platform_type_map(self, entity_type: str) -> str:
        key = str(entity_type or "").strip().upper()
        if key in self._PLATFORM_MAP:
            return self._PLATFORM_MAP[key]
        if "SUBMARINE" in key:
            return "SUBMARINE"
        if "FISH" in key:
            return "FISHING"
        if "MERCHANT" in key:
            return "MERCHANT"
        if "SHIP" in key or "SURFACE" in key or "VESSEL" in key:
            return "SURFACE_COMBATANT"
        return "UNKNOWN"

    @staticmethod
    def _parse_gateway_target(gateway_url: str) -> tuple[str, int]:
        text = str(gateway_url or "").strip()
        if not text:
            raise ValueError("gateway_url is required")
        parsed = urlparse(text if "://" in text else f"tcp://{text}")
        if parsed.scheme and parsed.scheme.lower() not in {"tcp", "oth", "oth-gold"}:
            raise ValueError("gateway_url must use tcp/oth scheme")
        if not parsed.hostname or not parsed.port:
            raise ValueError("gateway_url must include host and port")
        return (parsed.hostname, int(parsed.port))

    def connect(self, gateway_url: str) -> bool:
        """Establish a TCP link to the OTH-Gold partner gateway."""
        self.disconnect()
        try:
            host, port = self._parse_gateway_target(gateway_url)
            sock = socket.create_connection((host, port), timeout=2.0)
            sock.settimeout(0.05)
        except (OSError, ValueError):
            self.connected = False
            self.gateway_url = gateway_url
            return False

        self._socket = sock
        self.connected = True
        self.gateway_url = gateway_url
        self._receive_buffer = ""
        return True

    def publish(self, tracks: List[Dict[str, Any]]) -> int:
        """Publish maritime tracks over the active OTH-Gold TCP connection."""
        if not self.connected or self._socket is None:
            return 0

        maritime_tracks = [track for track in list(tracks or []) if isinstance(track, dict) and self._is_maritime_track(track)]
        if not maritime_tracks:
            return 0

        xml_payload = self.build_message(maritime_tracks)
        try:
            self._socket.sendall(xml_payload.encode("utf-8") + b"\n")
        except OSError:
            self.disconnect()
            return 0

        self._published_messages += 1
        self._published_tracks += len(maritime_tracks)
        return len(maritime_tracks)

    def _extract_complete_messages(self) -> List[str]:
        messages: List[str] = []
        closing_tag = "</OTHGold>"
        while True:
            end_idx = self._receive_buffer.find(closing_tag)
            if end_idx < 0:
                break
            end_idx += len(closing_tag)
            start_idx = self._receive_buffer.find("<OTHGold")
            if start_idx < 0 or start_idx >= end_idx:
                self._receive_buffer = self._receive_buffer[end_idx:]
                continue
            messages.append(self._receive_buffer[start_idx:end_idx])
            self._receive_buffer = self._receive_buffer[end_idx:]
        return messages

    def receive(self) -> List[Dict[str, Any]]:
        """Receive and parse any pending OTH-Gold tracks from TCP socket."""
        if not self.connected or self._socket is None:
            return []

        try:
            data = self._socket.recv(65535)
        except (BlockingIOError, TimeoutError, socket.timeout):
            return []
        except OSError:
            self.disconnect()
            return []

        if not data:
            self.disconnect()
            return []

        self._receive_buffer += data.decode("utf-8", errors="ignore")
        messages = self._extract_complete_messages()
        tracks: List[Dict[str, Any]] = []
        for message in messages:
            tracks.extend(self.parse_message(message))
        self._received_tracks_total += len(tracks)
        return tracks

    def disconnect(self) -> None:
        """Tear down the active OTH-Gold TCP connection."""
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None
        self.connected = False
        self._receive_buffer = ""

    def status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "gateway_url": self.gateway_url,
            "published_messages": self._published_messages,
            "published_tracks": self._published_tracks,
            "received_tracks_total": self._received_tracks_total,
        }

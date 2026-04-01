"""AIS parsing for file-based air-gapped maritime surveillance ingestion."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from services.sensor_analytics.models import AISMessage


def _parse_ts(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class AISParser:
    """Parses AIS NMEA or CSV files into AISMessage entities."""

    def __init__(self) -> None:
        self.static_data: Dict[str, Dict[str, str]] = {}

    def decode_payload(self, payload: str, pad_bits: int = 0) -> List[int]:
        bits: List[int] = []
        for char in payload:
            value = ord(char) - 48
            if value > 40:
                value -= 8
            for shift in range(5, -1, -1):
                bits.append((value >> shift) & 1)
        if pad_bits > 0:
            bits = bits[: len(bits) - pad_bits]
        return bits

    def _bits_to_int(self, bits: List[int], start: int, length: int, signed: bool = False) -> int:
        segment = bits[start : start + length]
        value = 0
        for bit in segment:
            value = (value << 1) | bit
        if signed and segment and segment[0] == 1:
            value -= 1 << length
        return value

    def _bits_to_text(self, bits: List[int], start: int, length: int) -> str:
        out = []
        for idx in range(start, start + length, 6):
            value = self._bits_to_int(bits, idx, 6, signed=False)
            if value < 32:
                value += 64
            ch = chr(value)
            if ch == "@":
                ch = " "
            out.append(ch)
        return "".join(out).strip()

    def parse_nmea(self, nmea_sentence: str) -> Optional[AISMessage]:
        line = nmea_sentence.strip()
        if not line or (not line.startswith("!AIVDM") and not line.startswith("!AIVDO")):
            return None
        parts = line.split(",")
        if len(parts) < 7:
            return None
        payload = parts[5]
        pad_bits = int(parts[6].split("*")[0]) if "*" in parts[6] else int(parts[6])
        bits = self.decode_payload(payload, pad_bits=pad_bits)
        if len(bits) < 38:
            return None
        msg_type = self._bits_to_int(bits, 0, 6)
        mmsi = str(self._bits_to_int(bits, 8, 30)).zfill(9)
        now = datetime.now(timezone.utc)

        if msg_type in (1, 2, 3, 18):
            nav_status = self._bits_to_int(bits, 38, 4) if msg_type in (1, 2, 3) else 0
            sog_raw = self._bits_to_int(bits, 50 if msg_type in (1, 2, 3) else 46, 10)
            cog_raw = self._bits_to_int(bits, 116 if msg_type in (1, 2, 3) else 112, 12)
            hdg_raw = self._bits_to_int(bits, 128 if msg_type in (1, 2, 3) else 124, 9)
            lon_raw = self._bits_to_int(bits, 61 if msg_type in (1, 2, 3) else 57, 28, signed=True)
            lat_raw = self._bits_to_int(bits, 89 if msg_type in (1, 2, 3) else 85, 27, signed=True)
            lon = lon_raw / 600000.0
            lat = lat_raw / 600000.0
            speed = float(sog_raw) / 10.0 if sog_raw < 1023 else 0.0
            course = float(cog_raw) / 10.0 if cog_raw < 3600 else 0.0
            heading = float(hdg_raw) if hdg_raw < 511 else 0.0
            static = self.static_data.get(mmsi, {})
            return AISMessage(
                mmsi=mmsi,
                timestamp=now,
                message_type=msg_type,
                lat=lat,
                lon=lon,
                speed_knots=speed,
                course_deg=course,
                heading_deg=heading,
                vessel_name=static.get("vessel_name"),
                vessel_type=int(static.get("vessel_type", "0")),
                destination=static.get("destination"),
                nav_status=nav_status,
                raw_nmea=line,
            )

        if msg_type == 5 and len(bits) >= 424:
            vessel_name = self._bits_to_text(bits, 112, 120)
            vessel_type = self._bits_to_int(bits, 232, 8)
            destination = self._bits_to_text(bits, 302, 120)
            self.static_data[mmsi] = {
                "vessel_name": vessel_name,
                "vessel_type": str(vessel_type),
                "destination": destination,
            }
            return AISMessage(
                mmsi=mmsi,
                timestamp=now,
                message_type=msg_type,
                lat=0.0,
                lon=0.0,
                speed_knots=0.0,
                course_deg=0.0,
                heading_deg=0.0,
                vessel_name=vessel_name or None,
                vessel_type=vessel_type,
                destination=destination or None,
                nav_status=0,
                raw_nmea=line,
            )

        if msg_type == 24:
            vessel_name = self._bits_to_text(bits, 40, 120) if len(bits) >= 160 else ""
            vessel_type = self._bits_to_int(bits, 40, 8) if len(bits) >= 48 else 0
            current = self.static_data.get(mmsi, {})
            if vessel_name:
                current["vessel_name"] = vessel_name
            if vessel_type:
                current["vessel_type"] = str(vessel_type)
            self.static_data[mmsi] = current
            return AISMessage(
                mmsi=mmsi,
                timestamp=now,
                message_type=msg_type,
                lat=0.0,
                lon=0.0,
                speed_knots=0.0,
                course_deg=0.0,
                heading_deg=0.0,
                vessel_name=current.get("vessel_name"),
                vessel_type=int(current.get("vessel_type", "0")),
                destination=current.get("destination"),
                nav_status=0,
                raw_nmea=line,
            )

        return None

    def parse_csv(self, filepath: str) -> List[AISMessage]:
        messages: List[AISMessage] = []
        with open(filepath, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                msg = AISMessage(
                    mmsi=str(row.get("MMSI", "")).strip(),
                    timestamp=_parse_ts(str(row.get("timestamp", ""))),
                    message_type=int(row.get("message_type", 1) or 1),
                    lat=float(row.get("lat", 0.0) or 0.0),
                    lon=float(row.get("lon", 0.0) or 0.0),
                    speed_knots=float(row.get("speed", 0.0) or 0.0),
                    course_deg=float(row.get("course", 0.0) or 0.0),
                    heading_deg=float(row.get("heading", 0.0) or 0.0),
                    vessel_name=(row.get("vessel_name") or None),
                    vessel_type=int(row.get("vessel_type", 0) or 0),
                    destination=(row.get("destination") or None),
                    nav_status=int(row.get("nav_status", 0) or 0),
                    raw_nmea=None,
                )
                if msg.mmsi:
                    messages.append(msg)
        return messages

    def parse_file(self, filepath: str) -> List[AISMessage]:
        suffix = Path(filepath).suffix.lower()
        messages: List[AISMessage] = []
        if suffix == ".csv":
            return self.parse_csv(filepath)
        if suffix == ".nmea":
            with open(filepath, "r", encoding="utf-8") as handle:
                for line in handle:
                    parsed = self.parse_nmea(line)
                    if parsed is not None:
                        messages.append(parsed)
            return messages
        # fallback by content
        with open(filepath, "r", encoding="utf-8") as handle:
            first = handle.readline().strip()
            handle.seek(0)
            if first.startswith("!AIVDM") or first.startswith("!AIVDO"):
                for line in handle:
                    parsed = self.parse_nmea(line)
                    if parsed is not None:
                        messages.append(parsed)
                return messages
        return self.parse_csv(filepath)

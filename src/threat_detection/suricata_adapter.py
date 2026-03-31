"""Suricata EVE JSON adapter for S3M Layer 02 threat ingestion."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource

LOGGER = logging.getLogger(__name__)


class SuricataAdapter:
    """Parse Suricata EVE alerts and convert them into tactical threat events.

    Example EVE JSON alert line:
    {
      "timestamp": "2026-03-31T10:30:45.123456+0000",
      "event_type": "alert",
      "src_ip": "10.10.4.22",
      "src_port": 49822,
      "dest_ip": "172.16.1.10",
      "dest_port": 443,
      "proto": "TCP",
      "alert": {
        "severity": 2,
        "signature_id": 2019236,
        "signature": "ET TROJAN Possible Malware CnC Check-in",
        "category": "A Network Trojan was detected"
      }
    }
    """

    def __init__(self, poll_interval_seconds: float = 1.0) -> None:
        if not isinstance(poll_interval_seconds, (int, float)) or poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be a positive number")
        self.poll_interval_seconds = float(poll_interval_seconds)

    def _map_severity(self, severity: int) -> ThreatLevel:
        """Map Suricata severity (1-4) to S3M tactical severity."""
        mapping = {
            1: ThreatLevel.CRITICAL,
            2: ThreatLevel.HIGH,
            3: ThreatLevel.MEDIUM,
            4: ThreatLevel.LOW,
        }
        return mapping.get(int(severity), ThreatLevel.INFO)

    def _map_category(self, category: str) -> ThreatCategory:
        """Map Suricata rule category text to military threat domain."""
        if not isinstance(category, str):
            return ThreatCategory.UNKNOWN
        normalized = category.lower()
        if any(
            marker in normalized
            for marker in [
                "trojan",
                "malware",
                "information leak",
                "intrusion",
                "command and control",
                "attempted administrator privilege gain",
                "attempted user privilege gain",
                "potentially bad traffic",
            ]
        ):
            return ThreatCategory.CYBER
        if "scan" in normalized or "recon" in normalized:
            return ThreatCategory.SURVEILLANCE
        return ThreatCategory.UNKNOWN

    def parse_event(self, json_dict: Dict[str, Any]) -> Optional[ThreatEvent]:
        """Parse a single EVE event dictionary into ThreatEvent."""
        if not isinstance(json_dict, dict):
            raise ValueError("json_dict must be a dictionary")

        if json_dict.get("event_type") != "alert":
            return None

        alert = json_dict.get("alert")
        if not isinstance(alert, dict):
            LOGGER.warning("Skipping Suricata alert without alert object")
            return None

        severity = alert.get("severity", 4)
        category_raw = str(alert.get("category", "Unknown"))
        signature = str(alert.get("signature", "Suricata alert"))
        signature_id = alert.get("signature_id")
        try:
            severity_int = int(severity)
        except (TypeError, ValueError):
            severity_int = 4

        timestamp_raw = json_dict.get("timestamp")
        timestamp = datetime.now(timezone.utc)
        if isinstance(timestamp_raw, str) and timestamp_raw.strip():
            try:
                timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            except ValueError:
                LOGGER.warning("Invalid Suricata timestamp '%s'; using current UTC", timestamp_raw)

        src_ip = json_dict.get("src_ip")
        src_port = json_dict.get("src_port")
        dest_ip = json_dict.get("dest_ip")
        dest_port = json_dict.get("dest_port")
        proto = json_dict.get("proto")

        title = f"Suricata IDS Alert: {signature}"
        description = (
            f"Network threat detected from {src_ip}:{src_port} to {dest_ip}:{dest_port} "
            f"over {proto}. Signature ID {signature_id}."
        )

        return ThreatEvent(
            source=ThreatSource.NETWORK_IDS,
            level=self._map_severity(severity_int),
            category=self._map_category(category_raw),
            timestamp=timestamp,
            title=title,
            description=description,
            raw_data={
                "src_ip": src_ip,
                "src_port": src_port,
                "dest_ip": dest_ip,
                "dest_port": dest_port,
                "protocol": proto,
                "signature_id": signature_id,
                "signature": signature,
                "category": category_raw,
                "suricata_event": json_dict,
            },
            confidence=max(0.3, min(1.0, 1.0 - (severity_int - 1) * 0.2)),
            asset_ids=[value for value in [str(dest_ip) if dest_ip else None] if value],
            recommended_action="Isolate destination host and inspect packet capture for hostile indicators.",
        )

    def parse_eve_log(self, filepath: str) -> List[ThreatEvent]:
        """Parse a Suricata EVE log file in JSON-lines format."""
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Suricata EVE log not found: {filepath}")

        events: List[ThreatEvent] = []
        with open(filepath, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    LOGGER.warning("Malformed JSON in Suricata log %s line %d; skipping", filepath, line_number)
                    continue

                try:
                    event = self.parse_event(payload)
                except Exception as exc:  # defensive parser hardening
                    LOGGER.warning("Failed to parse Suricata event on line %d: %s", line_number, exc)
                    continue
                if event:
                    events.append(event)
        return events

    def watch_log(self, filepath: str, callback: Callable[[ThreatEvent], None]) -> None:
        """Tail EVE log and push new alerts into callback.

        This polling tail is chosen intentionally for air-gapped tactical deployments
        where inotify support may be constrained by hardened runtime profiles.
        """
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        if not callable(callback):
            raise ValueError("callback must be callable")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Suricata EVE log not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as handle:
            handle.seek(0, os.SEEK_END)
            while True:
                line = handle.readline()
                if not line:
                    time.sleep(self.poll_interval_seconds)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    event = self.parse_event(payload)
                except json.JSONDecodeError:
                    LOGGER.warning("Malformed JSON while tailing Suricata log; skipping line")
                    continue
                except Exception as exc:
                    LOGGER.warning("Suricata tail parse error: %s", exc)
                    continue
                if event:
                    callback(event)

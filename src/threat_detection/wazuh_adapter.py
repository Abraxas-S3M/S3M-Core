"""Wazuh alert adapter for S3M Layer 02 threat ingestion."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource

LOGGER = logging.getLogger(__name__)


class WazuhAdapter:
    """Parse Wazuh alert logs and convert them into tactical ThreatEvent objects."""

    def __init__(self, poll_interval_seconds: float = 2.0) -> None:
        if not isinstance(poll_interval_seconds, (int, float)) or poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be a positive number")
        self.poll_interval_seconds = float(poll_interval_seconds)

    def _map_rule_level(self, level: int) -> ThreatLevel:
        """Map Wazuh rule level (0-15) to S3M tactical severity."""
        numeric_level = int(level)
        if 0 <= numeric_level <= 3:
            return ThreatLevel.INFO
        if 4 <= numeric_level <= 7:
            return ThreatLevel.LOW
        if 8 <= numeric_level <= 11:
            return ThreatLevel.MEDIUM
        if 12 <= numeric_level <= 14:
            return ThreatLevel.HIGH
        if numeric_level >= 15:
            return ThreatLevel.CRITICAL
        return ThreatLevel.INFO

    def _map_groups(self, groups: List[str]) -> ThreatCategory:
        """Map Wazuh rule groups to high-level threat domain."""
        normalized = {group.lower() for group in groups if isinstance(group, str)}
        cyber_groups = {
            "intrusion_detection",
            "authentication_failure",
            "syscheck",
            "malware",
            "firewall",
            "ids",
            "web",
            "attack",
        }
        if normalized & cyber_groups:
            return ThreatCategory.CYBER
        if "recon" in normalized or "scan" in normalized:
            return ThreatCategory.SURVEILLANCE
        return ThreatCategory.UNKNOWN

    def parse_alert(self, json_dict: Dict[str, Any]) -> Optional[ThreatEvent]:
        """Parse one Wazuh JSON alert into ThreatEvent."""
        if not isinstance(json_dict, dict):
            raise ValueError("json_dict must be a dictionary")

        rule = json_dict.get("rule", {})
        if not isinstance(rule, dict):
            LOGGER.warning("Skipping Wazuh alert with missing rule object")
            return None

        level = int(rule.get("level", 0))
        rule_id = str(rule.get("id", "unknown"))
        description = str(rule.get("description", "Wazuh alert"))
        groups = rule.get("groups") or []
        if not isinstance(groups, list):
            groups = [str(groups)]

        agent = json_dict.get("agent", {})
        if not isinstance(agent, dict):
            agent = {}
        agent_name = str(agent.get("name", "unknown-agent"))
        src_ip = json_dict.get("srcip") or json_dict.get("data", {}).get("srcip")
        full_log = json_dict.get("full_log")

        timestamp_raw = json_dict.get("timestamp")
        timestamp = datetime.now(timezone.utc)
        if isinstance(timestamp_raw, str) and timestamp_raw.strip():
            try:
                timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            except ValueError:
                LOGGER.warning("Invalid Wazuh timestamp '%s'; using current UTC", timestamp_raw)

        return ThreatEvent(
            source=ThreatSource.ENDPOINT_SIEM,
            level=self._map_rule_level(level),
            category=self._map_groups(groups),
            timestamp=timestamp,
            title=f"Wazuh Alert [{rule_id}] on {agent_name}",
            description=description,
            raw_data={
                "agent_name": agent_name,
                "rule_id": rule_id,
                "rule_description": description,
                "rule_groups": groups,
                "source_ip": src_ip,
                "full_log": full_log,
                "wazuh_alert": json_dict,
            },
            confidence=max(0.2, min(1.0, level / 15.0)),
            asset_ids=[agent_name],
            recommended_action="Inspect endpoint telemetry and isolate host if compromise indicators escalate.",
        )

    def parse_alerts_file(self, filepath: str) -> List[ThreatEvent]:
        """Parse Wazuh alerts JSON-lines file."""
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Wazuh alerts file not found: {filepath}")

        events: List[ThreatEvent] = []
        with open(filepath, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    LOGGER.warning("Malformed JSON in Wazuh alerts file %s line %d; skipping", filepath, line_number)
                    continue
                try:
                    event = self.parse_alert(payload)
                except Exception as exc:
                    LOGGER.warning("Failed parsing Wazuh alert on line %d: %s", line_number, exc)
                    continue
                if event:
                    events.append(event)
        return events

    def watch_alerts(self, filepath: str, callback: Callable[[ThreatEvent], None]) -> None:
        """Tail Wazuh alerts file and invoke callback with parsed events."""
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        if not callable(callback):
            raise ValueError("callback must be callable")
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Wazuh alerts file not found: {filepath}")

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
                    event = self.parse_alert(payload)
                except json.JSONDecodeError:
                    LOGGER.warning("Malformed JSON while tailing Wazuh file; skipping line")
                    continue
                except Exception as exc:
                    LOGGER.warning("Wazuh tail parse error: %s", exc)
                    continue
                if event:
                    callback(event)

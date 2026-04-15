"""Capability and partner registry for interoperability components."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List


class InteropRegistry:
    """Stores capability declarations and coalition partner code tables."""

    def __init__(self):
        self.capabilities: Dict[str, Dict[str, object]] = {}
        self.exercise_sessions: Dict[int, dict] = {}
        self.register_capability("cot", "2.0", ["event_xml", "multicast", "tak_server", "dis_crossfeed"])

    def register_capability(self, protocol, version, features: List[str]):
        self.capabilities[str(protocol).lower()] = {
            "protocol": str(protocol),
            "version": str(version),
            "features": list(features),
        }

    def get_capabilities(self) -> dict:
        return dict(self.capabilities)

    def get_gcc_partner_codes(self) -> dict:
        return {
            "Saudi Arabia": 178,
            "UAE": 223,
            "Kuwait": 117,
            "Bahrain": 16,
            "Qatar": 164,
            "Oman": 154,
        }

    def get_nato_partner_codes(self) -> dict:
        return {
            "United States": 225,
            "United Kingdom": 224,
            "France": 71,
            "Germany": 78,
            "Italy": 105,
            "Spain": 198,
            "Turkey": 222,
            "Canada": 39,
            "Netherlands": 145,
            "Norway": 146,
        }

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "capability_count": len(self.capabilities),
            "exercise_sessions": len(self.exercise_sessions),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


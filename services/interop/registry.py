"""Capability and partner registry for interoperability components."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List


class InteropRegistry:
    """Stores capability declarations and coalition partner code tables."""

    def __init__(self):
        self.capabilities: Dict[str, Dict[str, object]] = {}
        self.exercise_sessions: Dict[int, dict] = {}
        self._register_default_capabilities()

    def _register_default_capabilities(self) -> None:
        self.register_capability("dis", "IEEE-1278.1", ["entity_state_pdu", "dead_reckoning"])
        self.register_capability("c2sim", "1.1", ["order_exchange", "report_exchange", "offline_outbox"])
        self.register_capability("msdl", "1.0", ["scenario_import", "scenario_export"])
        self.register_capability(
            "taxii",
            "2.1",
            ["stix_bundle_publish", "stix_bundle_poll", "offline_outbox", "offline_inbox_cache"],
        )

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


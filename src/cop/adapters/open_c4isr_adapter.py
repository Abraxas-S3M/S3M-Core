"""Open C4ISR / COP ingestion adapter seam.

Tactical context:
    S3M-Core positions itself as the sovereign AI integration layer *above* open
    C4ISR/COP systems such as TAK / FreeTAKServer / OpenTAKServer / ODIN and
    C2SIM. This module defines the stable adapter contract for ingesting those
    feeds and normalizing them into the S3M COP schema (:class:`CopTrack`, etc).

    The first functional version intentionally sources *deterministic demo data*
    from :mod:`src.cop.demo_tracks`. A real TAK/ODIN connector can later be
    dropped in behind this same interface without touching the COP API surface,
    the WebSocket layer, or the future quad-engine reasoning bridge. This is the
    "seam first" approach -- no deep TAK integration is performed yet.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.cop.cop_models import CopTrack
from src.cop.demo_tracks import DEMO_TRACKS, build_scenario, is_supported_track


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class OpenC4ISRAdapter:
    """Adapter contract for open C4ISR/COP inputs (TAK / ODIN / C2SIM-style).

    The contract is deliberately small and synchronous so it can be backed by a
    deterministic demo source today and a live broker tomorrow:

        health()                 -> dict
        fetch_tracks(track)      -> list[dict]
        fetch_alerts(track)      -> list[dict]
        fetch_feed(track)        -> list[dict]
        normalize_track(raw)     -> CopTrack
    """

    #: Mapping of common upstream domain labels into the S3M COP domain model.
    DOMAIN_ALIASES: Dict[str, str] = {
        "a-f": "air",
        "a-h": "air",
        "air": "air",
        "aircraft": "air",
        "uav": "air",
        "sea": "maritime",
        "surface": "maritime",
        "vessel": "maritime",
        "maritime": "maritime",
        "ground": "ground",
        "land": "ground",
        "cyber": "cyber",
        "network": "cyber",
        "isr": "isr",
        "sigint": "isr",
        "space": "space",
        "missile": "missile",
        "ballistic": "missile",
        "sensor": "sensor",
        "radar": "sensor",
    }

    #: Mapping of common affiliation labels into the S3M COP identity model.
    AFFILIATION_ALIASES: Dict[str, str] = {
        "f": "friendly",
        "friend": "friendly",
        "friendly": "friendly",
        "blue": "friendly",
        "h": "hostile",
        "hostile": "hostile",
        "red": "hostile",
        "enemy": "hostile",
        "u": "unknown",
        "unknown": "unknown",
        "pending": "unknown",
        "n": "neutral",
        "neutral": "neutral",
        "green": "neutral",
    }

    def __init__(self, *, source_label: str = "open_c4isr_adapter") -> None:
        self._source_label = source_label

    # ── Contract ────────────────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        """Report adapter availability and the mode it is operating in."""
        return {
            "adapter": "open_c4isr_adapter",
            "status": "operational",
            "mode": "deterministic_demo",
            "live_integration": False,
            "supported_inputs": ["tak", "freetakserver", "opentakserver", "odin", "c2sim"],
            "supported_tracks": list(DEMO_TRACKS),
            "timestamp": _now_iso(),
        }

    def fetch_tracks(self, track: str) -> List[Dict[str, Any]]:
        """Return raw track dicts for ``track`` from the upstream source.

        The demo implementation returns the deterministic scenario seed. Each
        row is already COP-shaped, but :meth:`normalize_track` is still applied
        to model the real flow where upstream rows must be normalized.
        """
        if not is_supported_track(track):
            return []
        scenario = build_scenario(track)
        return [_dump(row) for row in scenario.tactical_tracks]

    def fetch_alerts(self, track: str) -> List[Dict[str, Any]]:
        """Return raw alert dicts for ``track`` from the upstream source."""
        if not is_supported_track(track):
            return []
        scenario = build_scenario(track)
        return [_dump(row) for row in scenario.alerts]

    def fetch_feed(self, track: str) -> List[Dict[str, Any]]:
        """Return raw feed item dicts for ``track`` from the upstream source."""
        if not is_supported_track(track):
            return []
        scenario = build_scenario(track)
        return [_dump(row) for row in scenario.feed_messages]

    def normalize_track(self, raw: Dict[str, Any]) -> CopTrack:
        """Normalize a raw upstream track dict into a :class:`CopTrack`.

        Accepts both already-COP-shaped rows and looser TAK/ODIN-style rows
        (e.g. ``lat``/``lon``, ``type``, ``affiliation`` codes) so a live
        connector can hand off minimally-parsed contacts.
        """
        if not isinstance(raw, dict):
            raise ValueError("raw track must be a mapping")

        domain = self._map_domain(str(raw.get("domain", raw.get("type", "unknown"))))
        affiliation = self._map_affiliation(str(raw.get("affiliation", raw.get("identity", "unknown"))))

        track_id = str(raw.get("track_id", raw.get("id", raw.get("uid", "trk-unknown"))))
        callsign = str(raw.get("callsign", raw.get("name", track_id)))

        linked = raw.get("linked_alert_ids", [])
        if not isinstance(linked, list):
            linked = []

        threat_score = raw.get("threat_score")
        try:
            threat_score = float(threat_score) if threat_score is not None else None
        except (TypeError, ValueError):
            threat_score = None

        return CopTrack(
            track_id=track_id,
            callsign=callsign,
            domain=domain,
            affiliation=affiliation,
            status=str(raw.get("status", "monitor")),
            latitude=self._as_float(raw.get("latitude", raw.get("lat")), 24.7136),
            longitude=self._as_float(raw.get("longitude", raw.get("lon")), 46.6753),
            altitude_m=self._as_float(raw.get("altitude_m", raw.get("altitude", raw.get("hae"))), 0.0),
            speed_kts=self._as_float(raw.get("speed_kts", raw.get("speed")), 0.0),
            heading_deg=self._as_float(raw.get("heading_deg", raw.get("heading", raw.get("course"))), 0.0),
            confidence=self._as_float(raw.get("confidence"), 0.5),
            last_update=str(raw.get("last_update", _now_iso())),
            source=str(raw.get("source", self._source_label)),
            classification=raw.get("classification"),
            threat_score=threat_score,
            linked_alert_ids=[str(item) for item in linked],
        )

    # ── Helpers ─────────────────────────────────────────────────

    def _map_domain(self, value: str) -> str:
        key = value.strip().lower()
        return self.DOMAIN_ALIASES.get(key, key if key else "unknown")

    def _map_affiliation(self, value: str) -> str:
        key = value.strip().lower()
        return self.AFFILIATION_ALIASES.get(key, "unknown")

    @staticmethod
    def _as_float(value: Any, default: float) -> float:
        try:
            if value is None:
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

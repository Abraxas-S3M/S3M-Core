"""COP (Common Operating Picture) adapter.

Merges sensor-fused tracks from COPDataProvider and threat events from
ThreatDashProvider into the unified GUIThreatTrack shape.

Internal dependencies:
- src.dashboard.providers.cop_provider.COPDataProvider (get_tracks, get_threats)
- src.dashboard.providers.threat_dash_provider.ThreatDashProvider (get_threat_feed)
"""

from datetime import datetime, timezone
from typing import List

from src.api.gui_bridge.models.gui_schemas import GUIThreatTrack, GUITracksData


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class COPAdapter:
    def __init__(self):
        from src.dashboard.providers.cop_provider import COPDataProvider
        self._cop = COPDataProvider()

    def get_tracks(self) -> GUITracksData:
        raw_tracks = self._cop.get_tracks()
        gui_tracks = []
        for t in raw_tracks:
            gui_tracks.append(GUIThreatTrack(
                id=t.get("id", "UNKNOWN"),
                domain=self._infer_domain(t),
                confidence=self._to_percent(t.get("confidence", 0)),
                severity=self._to_percent(t.get("threat_score", t.get("confidence", 0))),
                correlatedTrackIds=list(t.get("correlated", [])),
                summary=t.get("classification", t.get("type", "Unknown track")),
                lastSeen=t.get("last_update", _now_iso()),
            ))
        return GUITracksData(tracks=gui_tracks, updatedAt=_now_iso())

    def get_threat_tracks(self) -> GUITracksData:
        """Threat-specific tracks from the threat dashboard provider."""
        raw_threats = self._cop.get_threats()
        gui_tracks = []
        for t in raw_threats:
            level = t.get("level", "MEDIUM")
            severity_map = {"CRITICAL": 95, "HIGH": 75, "MEDIUM": 50, "LOW": 25, "INFO": 10}
            gui_tracks.append(GUIThreatTrack(
                id=t.get("id", "UNKNOWN"),
                domain=t.get("category", "kinetic").lower(),
                confidence=self._to_percent(t.get("confidence", 0.5)),
                severity=severity_map.get(level, 50),
                correlatedTrackIds=[],
                summary=t.get("description", t.get("title", "")),
                lastSeen=t.get("timestamp", _now_iso()),
            ))
        return GUITracksData(tracks=gui_tracks, updatedAt=_now_iso())

    @staticmethod
    def _infer_domain(track: dict) -> str:
        track_type = str(track.get("type", "")).lower()
        if any(kw in track_type for kw in ("air", "uav", "aircraft", "missile")):
            return "kinetic"
        if any(kw in track_type for kw in ("cyber", "network", "packet")):
            return "cyber"
        if any(kw in track_type for kw in ("sigint", "elint", "humint")):
            return "intel"
        return "kinetic"

    @staticmethod
    def _to_percent(val) -> int:
        v = float(val) if val else 0
        if v < 0:
            return 0
        if v <= 1.0:
            return int(v * 100)
        return int(min(100, max(0, v)))

"""Deterministic COP demo scenario seeds for the S3M-Core C4ISR layer.

Tactical context:
    This module is the single source of truth for the demonstration Common
    Operational Picture. Every object here is *deterministic and repeatable* so
    that live demonstrations to partners (Saudi RSADF, AFRL, Lockheed Martin)
    render an identical theater on every run. No live sensor feeds, no random
    seeds, no external API calls -- the data is a fixed tactical vignette that
    seeds the future quad-engine AI reasoning layer.

    The primary demonstration track is ``saudi_mod`` (Saudi/Gulf theater). The
    remaining tracks are future-safe identifiers that reuse the same Gulf
    geography with re-labelled theater metadata so partner demos can be wired in
    without changing the COP API surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.cop.cop_models import (
    CopAlert,
    CopDecision,
    CopFeature,
    CopFeedItem,
    CopMapConfig,
    CopPanelState,
    CopTheater,
    CopTrack,
)

# Future-safe demonstration tracks. ``saudi_mod`` is the primary demo track;
# the remaining identifiers are reserved for partner-specific demonstrations.
DEMO_TRACKS: tuple[str, ...] = (
    "saudi_mod",
    "lockheed_demo",
    "afrl_demo",
    "rsadf_demo",
    "golden_dome_demo",
)

# Theater framing shared by every demo track. The bounds intentionally match the
# Saudi/Gulf area of responsibility so WebSocket motion can be clamped uniformly.
THEATER_CENTER: List[float] = [24.7136, 46.6753]
THEATER_BOUNDS: List[List[float]] = [[15.5, 34.0], [32.8, 56.8]]

# Per-track theater metadata. The geography is shared; only the labels differ so
# the demonstration narrative can be re-framed for each partner.
_TRACK_PROFILES: Dict[str, Dict[str, str]] = {
    "saudi_mod": {
        "name": "Saudi MOD Joint Operations Theater",
        "command": "RSADF Joint Force Command",
        "source": "saudi_mod_demo",
    },
    "lockheed_demo": {
        "name": "Lockheed Martin C4ISR Integration Theater",
        "command": "LM Integrated Battlespace Cell",
        "source": "lockheed_demo",
    },
    "afrl_demo": {
        "name": "AFRL Sovereign AI Experimentation Theater",
        "command": "AFRL Autonomy & Reasoning Lab",
        "source": "afrl_demo",
    },
    "rsadf_demo": {
        "name": "RSADF Coalition Air & Maritime Theater",
        "command": "Royal Saudi Air Defense Forces",
        "source": "rsadf_demo",
    },
    "golden_dome_demo": {
        "name": "Golden Dome Integrated Air & Missile Defense Theater",
        "command": "Golden Dome IAMD Watch",
        "source": "golden_dome_demo",
    },
}


@dataclass
class DemoScenario:
    """A fully assembled deterministic COP scenario for one demo track."""

    track: str
    theater: CopTheater
    map_config: CopMapConfig
    geospatial_features: List[CopFeature] = field(default_factory=list)
    tactical_tracks: List[CopTrack] = field(default_factory=list)
    alerts: List[CopAlert] = field(default_factory=list)
    decisions: List[CopDecision] = field(default_factory=list)
    feed_messages: List[CopFeedItem] = field(default_factory=list)
    panel_summaries: List[CopPanelState] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        """Return the scenario as plain dicts for COP state assembly."""

        def dump(model: Any) -> Dict[str, Any]:
            if hasattr(model, "model_dump"):
                return model.model_dump()
            return model.dict()

        return {
            "track": self.track,
            "theater": dump(self.theater),
            "map_config": dump(self.map_config),
            "geospatial_features": [dump(row) for row in self.geospatial_features],
            "tactical_tracks": [dump(row) for row in self.tactical_tracks],
            "alerts": [dump(row) for row in self.alerts],
            "decisions": [dump(row) for row in self.decisions],
            "feed_messages": [dump(row) for row in self.feed_messages],
            "panel_summaries": [dump(row) for row in self.panel_summaries],
        }


def is_supported_track(track: str) -> bool:
    return str(track).strip().lower() in DEMO_TRACKS


def _theater(track: str, profile: Dict[str, str]) -> CopTheater:
    return CopTheater(
        track=track,
        name=profile["name"],
        center=list(THEATER_CENTER),
        bounds=[list(row) for row in THEATER_BOUNDS],
        focus_areas=[
            {"name": "Riyadh", "center": [24.7136, 46.6753], "type": "c2_hub"},
            {"name": "Eastern Province", "center": [26.42, 50.09], "type": "force_concentration"},
            {"name": "Jubail", "center": [27.0174, 49.6225], "type": "industrial_port"},
            {"name": "Arabian Gulf", "center": [26.1, 51.8], "type": "maritime_corridor"},
            {"name": "Red Sea", "center": [22.5, 38.8], "type": "strategic_sea_lane"},
            {"name": "Hormuz", "center": [26.57, 56.25], "type": "chokepoint"},
            {"name": "Bab al-Mandab", "center": [12.64, 43.34], "type": "chokepoint"},
            {"name": "Abu Musa", "center": [25.88, 55.03], "type": "island_outpost"},
            {"name": "Al Dhafra", "center": [24.25, 54.55], "type": "air_base"},
            {"name": "NAVCENT Bahrain", "center": [26.2285, 50.586], "type": "coalition_hq"},
        ],
    )


def _map_config() -> CopMapConfig:
    return CopMapConfig(
        center=list(THEATER_CENTER),
        bounds=[list(row) for row in THEATER_BOUNDS],
        layers=[
            "borders",
            "air_corridors",
            "maritime_routes",
            "critical_infrastructure",
            "threat_heatmap",
            "c2_nodes",
            "sensor_coverage",
            "defended_assets",
        ],
    )


def _features() -> List[CopFeature]:
    return [
        CopFeature(
            feature_id="focus-riyadh",
            feature_type="focus_area",
            name="Riyadh Command Radius",
            geometry_type="Point",
            coordinates=[46.6753, 24.7136],
            properties={"priority": "critical", "domain": "command"},
        ),
        CopFeature(
            feature_id="focus-jubail",
            feature_type="focus_area",
            name="Jubail Energy Corridor",
            geometry_type="Point",
            coordinates=[49.6225, 27.0174],
            properties={"priority": "high", "domain": "logistics"},
        ),
        CopFeature(
            feature_id="route-hormuz-gulf",
            feature_type="sea_lane",
            name="Hormuz to Arabian Gulf Shipping Lane",
            geometry_type="LineString",
            coordinates=[[56.25, 26.57], [52.8, 26.1], [50.2, 26.2]],
            properties={"priority": "high", "domain": "maritime"},
        ),
        CopFeature(
            feature_id="route-red-sea",
            feature_type="sea_lane",
            name="Bab al-Mandab Transit Route",
            geometry_type="LineString",
            coordinates=[[43.34, 12.64], [41.8, 17.2], [39.1, 22.4]],
            properties={"priority": "high", "domain": "maritime"},
        ),
        # Defended-asset and sensor coverage markers (requirement 3).
        CopFeature(
            feature_id="defended-riyadh-c2",
            feature_type="defended_asset",
            name="Riyadh Command & Control Complex",
            geometry_type="Point",
            coordinates=[46.71, 24.69],
            properties={"priority": "critical", "domain": "command", "protection": "iads"},
        ),
        CopFeature(
            feature_id="defended-jubail-port",
            feature_type="defended_asset",
            name="Jubail Strategic Port",
            geometry_type="Point",
            coordinates=[49.66, 27.04],
            properties={"priority": "high", "domain": "logistics"},
        ),
        CopFeature(
            feature_id="sensor-eastern-radar",
            feature_type="sensor_coverage",
            name="Eastern Province Long-Range Radar Arc",
            geometry_type="Point",
            coordinates=[50.09, 26.42],
            properties={"priority": "high", "domain": "air_defense", "range_km": 320},
        ),
    ]


def _tracks(track: str, source: str) -> List[CopTrack]:
    """Deterministic multi-domain track seed (requirement 3).

    Tactical context:
        Provides one friendly + one hostile + one unknown contact across the
        air, maritime, cyber, isr, missile, and sensor domains so the COP
        demonstrates full multi-domain fusion. Coordinates remain inside the
        Saudi/Gulf theater bounds.
    """
    return [
        # Friendly RSAF combat air patrol near Riyadh / Eastern Province.
        CopTrack(
            track_id="trk-rsaf-cap-001",
            callsign="RSAF-EAGLE-11",
            domain="air",
            affiliation="friendly",
            status="on_station",
            latitude=24.92,
            longitude=47.08,
            altitude_m=9700.0,
            speed_kts=420.0,
            heading_deg=102.0,
            confidence=0.96,
            last_update="",
            source=source,
            classification="F-15SA combat air patrol",
            threat_score=0.0,
        ),
        # Friendly RSNF maritime patrol in the Arabian Gulf.
        CopTrack(
            track_id="trk-rsnf-patrol-017",
            callsign="RSNF-FALCON-7",
            domain="maritime",
            affiliation="friendly",
            status="patrolling",
            latitude=26.18,
            longitude=51.34,
            altitude_m=0.0,
            speed_kts=21.0,
            heading_deg=148.0,
            confidence=0.91,
            last_update="",
            source=source,
            classification="RSNF corvette patrol",
            threat_score=0.0,
        ),
        # Friendly ISR UAV near Red Sea / Jubail.
        CopTrack(
            track_id="trk-isr-uav-204",
            callsign="ISR-HAWK-3",
            domain="isr",
            affiliation="friendly",
            status="collecting",
            latitude=26.95,
            longitude=49.40,
            altitude_m=6100.0,
            speed_kts=160.0,
            heading_deg=210.0,
            confidence=0.93,
            last_update="",
            source=source,
            classification="MALE ISR UAV",
            threat_score=0.0,
        ),
        # Hostile UAV / missile-like object near Gulf approach.
        CopTrack(
            track_id="trk-hostile-uav-731",
            callsign="HOSTILE-731",
            domain="missile",
            affiliation="hostile",
            status="inbound",
            latitude=26.62,
            longitude=53.40,
            altitude_m=1800.0,
            speed_kts=480.0,
            heading_deg=255.0,
            confidence=0.74,
            last_update="",
            source=source,
            classification="One-way attack UAV (suspected)",
            threat_score=0.82,
            linked_alert_ids=["alt-air-threat-003"],
        ),
        # Hostile maritime fast attack craft near Hormuz.
        CopTrack(
            track_id="trk-hostile-fac-512",
            callsign="FAC-512",
            domain="maritime",
            affiliation="hostile",
            status="closing",
            latitude=26.55,
            longitude=56.10,
            altitude_m=0.0,
            speed_kts=38.0,
            heading_deg=290.0,
            confidence=0.7,
            last_update="",
            source=source,
            classification="Fast attack craft swarm element",
            threat_score=0.71,
            linked_alert_ids=["alt-hormuz-001"],
        ),
        # Unknown air object near Abu Musa / Gulf.
        CopTrack(
            track_id="trk-unknown-air-404",
            callsign="UNKNOWN-404",
            domain="air",
            affiliation="unknown",
            status="monitor",
            latitude=25.84,
            longitude=54.74,
            altitude_m=10200.0,
            speed_kts=360.0,
            heading_deg=258.0,
            confidence=0.62,
            last_update="",
            source=source,
            classification="Unidentified high-altitude contact",
            threat_score=0.45,
            linked_alert_ids=["alt-unknown-004"],
        ),
        # Unknown cyber / C2 node affecting a protected network segment.
        CopTrack(
            track_id="trk-cyber-c2-909",
            callsign="C2-ANOMALY-909",
            domain="cyber",
            affiliation="unknown",
            status="investigating",
            latitude=24.71,
            longitude=46.71,
            altitude_m=0.0,
            speed_kts=0.0,
            heading_deg=0.0,
            confidence=0.58,
            last_update="",
            source=source,
            classification="Suspected C2 beaconing node",
            threat_score=0.6,
            linked_alert_ids=["alt-cyber-002"],
        ),
        # Friendly sensor node / radar site marker.
        CopTrack(
            track_id="trk-sensor-radar-050",
            callsign="RADAR-EAST-1",
            domain="sensor",
            affiliation="friendly",
            status="active",
            latitude=26.42,
            longitude=50.09,
            altitude_m=45.0,
            speed_kts=0.0,
            heading_deg=0.0,
            confidence=0.99,
            last_update="",
            source=source,
            classification="Long-range air-defense radar",
            threat_score=0.0,
        ),
    ]


def _alerts() -> List[CopAlert]:
    return [
        CopAlert(
            alert_id="alt-hormuz-001",
            category="maritime",
            severity="high",
            title="Hostile fast craft closing near Hormuz",
            summary="Fast attack craft element maneuvering toward the chokepoint; monitor convoy separation.",
            location="Strait of Hormuz",
            recommended_action="Increase ISR revisit rate and hold escort package at readiness level 2.",
            timestamp="",
        ),
        CopAlert(
            alert_id="alt-cyber-002",
            category="cyber",
            severity="medium",
            title="Anomalous scanning against C2 subnet",
            summary="Repeated reconnaissance signatures detected against the command network segment.",
            location="Riyadh C2 enclave",
            recommended_action="Isolate exposed node and enforce packet capture for attribution.",
            timestamp="",
        ),
        CopAlert(
            alert_id="alt-air-threat-003",
            category="air_defense",
            severity="high",
            title="Inbound one-way attack UAV near Gulf approach",
            summary="Low-altitude high-speed contact tracking toward defended assets in the Eastern Province.",
            location="Arabian Gulf approach",
            recommended_action="Cue air-defense sensors and prepare intercept decision package for commander review.",
            timestamp="",
        ),
        CopAlert(
            alert_id="alt-unknown-004",
            category="air",
            severity="low",
            title="Unidentified high-altitude air object",
            summary="Unknown contact loitering near Abu Musa with intermittent transponder behavior.",
            location="Abu Musa / Gulf",
            recommended_action="Maintain track custody and request identification cross-cue.",
            timestamp="",
        ),
    ]


def _decisions() -> List[CopDecision]:
    """Demo decision cards (requirement 7). No autonomous action is taken."""
    return [
        CopDecision(
            decision_id="dec-monitor-unknown-air",
            title="Recommend increased monitoring of unknown air object",
            summary="Increase track custody and sensor dwell on the unidentified contact near Abu Musa.",
            owner="AIR_DEFENSE_CELL",
            status="recommended",
            priority="medium",
            timestamp="",
        ),
        CopDecision(
            decision_id="dec-cue-isr-gulf",
            title="Recommend cueing ISR coverage toward Gulf approach",
            summary="Re-task the ISR UAV to extend persistent coverage over the Gulf ingress vector.",
            owner="ISR_DESK",
            status="recommended",
            priority="high",
            timestamp="",
        ),
        CopDecision(
            decision_id="dec-escort-hormuz",
            title="Recommend maritime escort adjustment near Hormuz",
            summary="Shift one escort vessel to the eastern lane to counter the closing fast attack craft.",
            owner="MARITIME_DESK",
            status="recommended",
            priority="high",
            timestamp="",
        ),
        CopDecision(
            decision_id="dec-cyber-watch",
            title="Recommend cyber watch elevation for C2 subnet anomaly",
            summary="Elevate cyber watch posture and enforce packet capture on the affected command segment.",
            owner="CYBER_CELL",
            status="recommended",
            priority="medium",
            timestamp="",
        ),
        CopDecision(
            decision_id="dec-commander-review",
            title="Recommend commander review before escalation",
            summary="Consolidate the air, maritime, and cyber picture for commander review prior to any escalation.",
            owner="JOINT_OPS",
            status="recommended",
            priority="high",
            timestamp="",
        ),
        CopDecision(
            decision_id="dec-no-autonomous-action",
            title="No autonomous action taken",
            summary="S3M-Core is operating as a decision-support layer only; all kinetic decisions remain with the human commander.",
            owner="JOINT_OPS",
            status="advisory",
            priority="low",
            timestamp="",
        ),
    ]


def _feed() -> List[CopFeedItem]:
    return [
        CopFeedItem(
            item_id="feed-001",
            channel="isr",
            title="ISR update",
            message="Persistent ISR confirms stable friendly posture around Riyadh and Jubail corridors.",
            language="en",
            tags=["isr", "cop"],
            timestamp="",
        ),
        CopFeedItem(
            item_id="feed-002",
            channel="air_defense",
            title="Air defense cue",
            message="Inbound contact near Gulf approach handed to air-defense cell for tracking.",
            language="en",
            tags=["air_defense", "threat"],
            timestamp="",
        ),
        CopFeedItem(
            item_id="feed-003",
            channel="command_chat",
            title="Command sync note",
            message="Joint desk requested consolidated risk and readiness snapshot for next briefing cycle.",
            language="en",
            tags=["command", "chat"],
            timestamp="",
        ),
        CopFeedItem(
            item_id="feed-004",
            channel="bilingual",
            title="ملاحظة قيادة",
            message="تؤكد الاستطلاع المستمر استقرار الوضع الصديق حول الرياض والجبيل.",
            language="ar",
            tags=["command", "arabic"],
            timestamp="",
        ),
    ]


def _panels() -> List[CopPanelState]:
    return [
        CopPanelState(
            panel_id="risk",
            title="Risk Panel",
            status="elevated",
            summary="Risk concentrated in maritime chokepoints and an inbound air threat.",
            metric={"overall_risk": 0.67, "trend_window_minutes": 30},
            trend="up",
            items=[{"zone": "Hormuz", "score": 0.79}, {"zone": "Gulf approach", "score": 0.72}],
        ),
        CopPanelState(
            panel_id="cyber",
            title="Cyber Panel",
            status="guarded",
            summary="Network telemetry indicates low-volume probing with no confirmed breach.",
            metric={"alerts_last_hour": 5, "blocked_attempts": 19},
            trend="stable",
            items=[{"segment": "c2-core", "posture": "hardened"}],
        ),
        CopPanelState(
            panel_id="maritime",
            title="Maritime Panel",
            status="monitoring",
            summary="Escort lanes remain open with increased watch at Hormuz and Bab al-Mandab.",
            metric={"active_contacts": 24, "escort_assets_ready": 4},
            trend="up",
            items=[{"area": "Arabian Gulf", "traffic_level": "high"}],
        ),
        CopPanelState(
            panel_id="air_defense",
            title="Air Defense Panel",
            status="alert",
            summary="One inbound hostile UAV tracked; intercept decision pending commander review.",
            metric={"inbound_threats": 1, "interceptors_ready": 6},
            trend="up",
            items=[{"contact": "HOSTILE-731", "status": "tracking"}],
        ),
        CopPanelState(
            panel_id="readiness",
            title="Readiness Panel",
            status="ready",
            summary="Air and naval readiness remain above baseline with reserve capacity available.",
            metric={"readiness_score": 0.9, "reserve_capacity": 0.24},
            trend="stable",
            items=[{"unit": "RSAF CAP", "status": "ready"}, {"unit": "RSNF Escort", "status": "ready"}],
        ),
        CopPanelState(
            panel_id="command_chat",
            title="Command / Chat Panel",
            status="active",
            summary="Command channel synchronized across mission desks with bilingual briefing queue.",
            metric={"active_threads": 6, "unread_messages": 2},
            trend="stable",
            items=[{"thread": "joint-ops", "priority": "high"}],
        ),
    ]


def build_scenario(track: str) -> DemoScenario:
    """Build the deterministic COP scenario for a supported demo ``track``.

    Timestamps are left blank here; the COP service stamps them at request time
    so the geometry stays deterministic while freshness metadata stays current.
    """
    normalized = str(track).strip().lower()
    profile = _TRACK_PROFILES.get(normalized, _TRACK_PROFILES["saudi_mod"])
    source = profile["source"]
    return DemoScenario(
        track=normalized,
        theater=_theater(normalized, profile),
        map_config=_map_config(),
        geospatial_features=_features(),
        tactical_tracks=_tracks(normalized, source),
        alerts=_alerts(),
        decisions=_decisions(),
        feed_messages=_feed(),
        panel_summaries=_panels(),
    )

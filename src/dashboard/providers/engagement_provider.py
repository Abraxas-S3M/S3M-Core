"""Engagement dashboard provider for HOOL recommendation visibility.

Military/tactical context:
This provider fuses recommendation, track, interlock, and ROE views so command
staff can verify engagement legality and safety posture before kinetic actions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.dashboard.providers.helpers import coerce_float, normalize_position
from src.dashboard.providers.runtime_store import get_runtime_state
from src.platforms.common.messages import ThreatPriority, Track
from src.platforms.fixed.horizon_adapter import TrackStore


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngagementProvider:
    """Provide engagement recommendations and tactical fire-control context."""

    def __init__(self, track_store: TrackStore | None = None) -> None:
        self._runtime = get_runtime_state()
        self._track_store = track_store or TrackStore()

    @staticmethod
    def _priority_from_row(row: Dict[str, Any]) -> ThreatPriority:
        raw = str(row.get("threat_priority", row.get("level", "MEDIUM"))).strip().upper()
        mapping = {
            "LOW": ThreatPriority.LOW,
            "MEDIUM": ThreatPriority.MEDIUM,
            "HIGH": ThreatPriority.HIGH,
            "CRITICAL": ThreatPriority.CRITICAL,
        }
        return mapping.get(raw, ThreatPriority.MEDIUM)

    def _get_hool_missions(self) -> Dict[str, Dict[str, Any]]:
        try:
            from services.autonomy.hool_extension import api_routes

            missions = getattr(api_routes, "_MISSIONS", {})
            return missions if isinstance(missions, dict) else {}
        except Exception:
            return {}

    def _recommendations_from_hool(self) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for mission_id, mission_row in self._get_hool_missions().items():
            if not isinstance(mission_row, dict):
                continue
            agent = mission_row.get("agent")
            history = getattr(agent, "decision_history", [])
            if not isinstance(history, list):
                continue
            for item in history[-30:]:
                if not isinstance(item, dict):
                    continue
                action = item.get("action_taken", {})
                output.append(
                    {
                        "recommendation_id": str(item.get("decision_id", f"{mission_id}-decision")),
                        "mission_id": str(item.get("mission_id", mission_id)),
                        "timestamp": str(item.get("timestamp", _utcnow())),
                        "commanded_action": str(action.get("action", item.get("decision_type", "hold_fire"))),
                        "confidence": coerce_float(item.get("confidence", 0.0), 0.0),
                        "risk_score": coerce_float(item.get("risk_score", 0.0), 0.0),
                        "requires_review": bool(item.get("requires_human_review", False)),
                        "rationale": str(item.get("reasoning", "")),
                    }
                )
        return output

    def _recommendations_from_runtime(self) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for item in self._runtime.get("decisions", []):
            if not isinstance(item, dict):
                continue
            output.append(
                {
                    "recommendation_id": str(item.get("id", "decision-unknown")),
                    "mission_id": str(item.get("mission_id", item.get("context", "unknown"))),
                    "timestamp": str(item.get("timestamp", _utcnow())),
                    "commanded_action": str(item.get("type", "hold_fire")),
                    "confidence": coerce_float(item.get("confidence", 0.0), 0.0),
                    "risk_score": coerce_float(item.get("risk_score", 0.0), 0.0),
                    "requires_review": bool(item.get("requires_review", False)),
                    "rationale": str(item.get("reasoning", item.get("reasoning_snippet", ""))),
                }
            )
        return output

    def _build_track_picture(self) -> List[Dict[str, Any]]:
        for index, row in enumerate(self._runtime.get("threats", [])):
            if not isinstance(row, dict):
                continue
            track_id = str(row.get("track_id", row.get("event_id", f"runtime-track-{index}")))
            position = normalize_position(row.get("position", row.get("location")))
            confidence = max(0.0, min(1.0, coerce_float(row.get("confidence", 0.0), 0.0)))
            classification = str(row.get("classification", row.get("category", "unknown")))
            track = Track(
                track_id=track_id,
                position=position,
                confidence=confidence,
                classification=classification,
                threat_priority=self._priority_from_row(row),
            )
            self._track_store.ingest_track(track)

        self._track_store.age_out()
        output: List[Dict[str, Any]] = []
        for track in self._track_store.get_tracks():
            output.append(
                {
                    "track_id": track.track_id,
                    "position": track.position,
                    "confidence": track.confidence,
                    "classification": track.classification,
                    "threat_priority": track.threat_priority.value,
                    "last_seen": track.last_seen.isoformat(),
                }
            )
        return output

    def _interlock_states(self) -> List[Dict[str, Any]]:
        rows = self._runtime.get("payload_interlocks", self._runtime.get("payloads", []))
        output: List[Dict[str, Any]] = []
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, dict):
                    continue
                output.append(
                    {
                        "payload_id": str(item.get("payload_id", item.get("id", "unknown"))),
                        "interlock_state": str(item.get("interlock_state", item.get("state", "safe"))).lower(),
                        "connected": bool(item.get("connected", True)),
                        "ammo_count": int(item.get("ammo_count", 0)),
                    }
                )
        if output:
            return output
        return [
            {"payload_id": "rcws-127", "interlock_state": "safe", "connected": False, "ammo_count": 0},
            {"payload_id": "rcws-145", "interlock_state": "safe", "connected": False, "ammo_count": 0},
            {"payload_id": "manpads", "interlock_state": "safe", "connected": False, "ammo_count": 0},
        ]

    def _active_roe_profile(self) -> str:
        for mission_row in self._get_hool_missions().values():
            if not isinstance(mission_row, dict):
                continue
            state = mission_row.get("state")
            envelope = getattr(state, "envelope", None)
            roe = getattr(envelope, "roe_level", None)
            if isinstance(roe, str) and roe.strip():
                return roe.strip().lower()

        runtime_roe = self._runtime.get("roe_profile")
        if isinstance(runtime_roe, str) and runtime_roe.strip():
            return runtime_roe.strip().lower()

        for item in reversed(self._runtime.get("decisions", [])):
            if not isinstance(item, dict):
                continue
            context = item.get("context")
            if isinstance(context, dict):
                roe = context.get("rules_of_engagement")
                if isinstance(roe, str) and roe.strip():
                    return roe.strip().lower()

        return "weapons_hold"

    def get_snapshot(self) -> Dict[str, Any]:
        recommendations = self._recommendations_from_hool()
        if not recommendations:
            recommendations = self._recommendations_from_runtime()
        tracks = self._build_track_picture()
        interlocks = self._interlock_states()
        active_roe = self._active_roe_profile()
        return {
            "provider": "engagement",
            "feed": "dashboard.engagement.snapshot",
            "timestamp": _utcnow(),
            "active_roe_profile": active_roe,
            "recommendations": recommendations,
            "track_picture": {"tracks": tracks, "total": len(tracks)},
            "interlock_states": interlocks,
            "summary": {
                "recommendation_count": len(recommendations),
                "track_count": len(tracks),
                "payload_count": len(interlocks),
            },
        }

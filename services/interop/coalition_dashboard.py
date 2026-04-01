"""Coalition dashboard provider for exercise COP and interop metrics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from services.interop.exercise_manager import ExerciseManager


class CoalitionDashboardProvider:
    """Builds coalition-facing exercise overview and COP data."""

    def __init__(self, manager: Optional[ExerciseManager] = None):
        self.manager = manager or ExerciseManager()

    def get_exercise_overview(self, exercise_id: str = None) -> dict:
        session = None
        if exercise_id is not None:
            session = self.manager.get_exercise(int(exercise_id))
        if session is None:
            active = self.manager.get_active_exercises()
            session = active[0] if active else None
        if session is None:
            return {
                "exercise": None,
                "nations": [],
                "entities": {"total": 0, "by_nation": {}, "by_type": {}},
                "events": {"total": 0, "fires": 0, "detonations": 0},
                "c2sim_messages": {"orders": 0, "reports": 0},
                "dis_pdus": {"sent": 0, "received": 0},
                "timeline": [],
            }

        entities = self.manager.get_exercise_entities(session.exercise_id)
        by_nation: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for entity in entities:
            country = str(entity.get("country_code", 178))
            by_nation[country] = by_nation.get(country, 0) + 1
            etype = str(entity.get("entity_type", "unknown"))
            by_type[etype] = by_type.get(etype, 0) + 1

        nation_rows = []
        for nation in session.participating_nations:
            code = str(nation.get("country_code", 0))
            nation_rows.append({**nation, "unit_count": by_nation.get(code, 0)})

        c2_metrics = self.manager.c2sim_engine.health_check().get("metrics", {})
        dis_stats = self.manager.dis_engine.network.get_exercise_stats()
        timeline = self.get_exercise_timeline(session.exercise_id)
        return {
            "exercise": session.to_dict(),
            "nations": nation_rows,
            "entities": {"total": len(entities), "by_nation": by_nation, "by_type": by_type},
            "events": {
                "total": session.events_count,
                "fires": int(sum(1 for event in timeline if event.get("event") == "fire")),
                "detonations": int(sum(1 for event in timeline if event.get("event") == "detonation")),
            },
            "c2sim_messages": {
                "orders": int(c2_metrics.get("orders_sent", 0)),
                "reports": int(c2_metrics.get("reports_sent", 0)),
            },
            "dis_pdus": {"sent": dis_stats.get("pdus_sent", 0), "received": dis_stats.get("pdus_received", 0)},
            "timeline": timeline,
        }

    def get_orbat_view(self, force_id: str = None) -> dict:
        if force_id:
            hierarchy = self.manager.orbat_manager.build_hierarchy(force_id)
            return self._serialize_hierarchy(hierarchy)
        rows = []
        for force in self.manager.orbat_manager.get_all_forces():
            rows.append(self._serialize_hierarchy(self.manager.orbat_manager.build_hierarchy(force.force_id)))
        return {"forces": rows}

    def _serialize_hierarchy(self, hierarchy: dict) -> dict:
        def to_node(row: dict) -> dict:
            unit = row["unit"]
            return {
                "unit": unit.to_dict(),
                "subordinates": [to_node(child) for child in row.get("subordinates", [])],
            }

        return {
            "force": hierarchy["force"].to_dict(),
            "hierarchy": [to_node(row) for row in hierarchy.get("hierarchy", [])],
        }

    def get_coalition_cop(self) -> dict:
        active = self.manager.get_active_exercises()
        entities = []
        reports = []
        for session in active:
            entities.extend(self.manager.get_exercise_entities(session.exercise_id))
            reports.extend(self.manager.receive_coalition_updates(session.exercise_id))
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entities": entities,
            "reports": reports,
            "exercise_count": len(active),
        }

    def get_interop_metrics(self) -> dict:
        dis_stats = self.manager.dis_engine.network.get_exercise_stats()
        c2_health = self.manager.c2sim_engine.health_check()
        return {
            "dis": {
                "pdu_rates": {
                    "sent": dis_stats.get("pdus_sent", 0),
                    "received": dis_stats.get("pdus_received", 0),
                },
                "errors": dis_stats.get("send_errors", 0) + dis_stats.get("recv_errors", 0),
            },
            "c2sim": {
                "message_counts": c2_health.get("metrics", {}),
                "errors": 0,
            },
            "latency_ms": {"dis": 0.0, "c2sim": 0.0},
        }

    def get_exercise_timeline(self, exercise_id) -> List[dict]:
        session = self.manager.get_exercise(int(exercise_id))
        if session is None:
            return []
        timeline = list(self.manager._events.get(session.exercise_id, []))
        return sorted(timeline, key=lambda row: row.get("timestamp", ""))


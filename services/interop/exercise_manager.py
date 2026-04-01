"""Exercise orchestration across DIS, C2SIM, and ORBAT layers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from services.interop.c2sim import C2SIMEngine
from services.interop.dis import DISEngine
from services.interop.models import ExerciseSession
from services.interop.msdl import ORBATManager


class ExerciseManager:
    """Manages coalition exercise lifecycle and protocol synchronization."""

    def __init__(self):
        self.dis_engine = DISEngine()
        self.c2sim_engine = C2SIMEngine()
        self.orbat_manager = ORBATManager()
        self._exercises: Dict[int, ExerciseSession] = {}
        self._events: Dict[int, List[dict]] = {}
        self._next_id = 1

    def create_exercise(
        self, name, description, nations: List[dict], dis_config=None, c2sim_config=None
    ) -> ExerciseSession:
        exercise_id = self._next_id
        self._next_id += 1
        session = ExerciseSession(
            exercise_id=exercise_id,
            exercise_name=str(name),
            description=str(description),
            start_time=datetime.now(timezone.utc),
            end_time=None,
            participating_nations=list(nations),
            status="planned",
            dis_config=dict(
                dis_config
                or {
                    "broadcast_address": "255.255.255.255",
                    "port": 3000,
                    "site_id": 1,
                    "app_id": 1,
                }
            ),
            c2sim_config=dict(
                c2sim_config
                or {
                    "server_url": None,
                    "namespace": "http://www.sisostds.org/schemas/C2SIM/1.1",
                }
            ),
            entities_count=0,
            events_count=0,
        )
        self._exercises[exercise_id] = session
        self._events[exercise_id] = [
            {"event": "created", "timestamp": datetime.now(timezone.utc).isoformat(), "details": {"name": name}}
        ]
        return session

    def start_exercise(self, exercise_id) -> bool:
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return False
        ok = self.dis_engine.start(
            exercise_id=session.exercise_id,
            broadcast=session.dis_config.get("broadcast_address", "255.255.255.255"),
            port=int(session.dis_config.get("port", 3000)),
        )
        self.c2sim_engine.server.connect(session.c2sim_config.get("server_url"))
        self.dis_engine.network.send_pdu(
            self.dis_engine.factory.encode_start_resume(
                exercise_id=session.exercise_id,
                real_world_time=int(datetime.now(timezone.utc).timestamp()),
                sim_time=0,
            )
        )
        session.status = "active"
        self._events[session.exercise_id].append(
            {"event": "started", "timestamp": datetime.now(timezone.utc).isoformat(), "details": {"dis_started": ok}}
        )
        return True

    def pause_exercise(self, exercise_id):
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return
        self.dis_engine.network.send_pdu(
            self.dis_engine.factory.encode_stop_freeze(session.exercise_id, reason=1)
        )
        session.status = "paused"
        self._events[session.exercise_id].append(
            {"event": "paused", "timestamp": datetime.now(timezone.utc).isoformat(), "details": {}}
        )

    def resume_exercise(self, exercise_id):
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return
        self.dis_engine.network.send_pdu(
            self.dis_engine.factory.encode_start_resume(
                exercise_id=session.exercise_id,
                real_world_time=int(datetime.now(timezone.utc).timestamp()),
                sim_time=int(session.duration_seconds() or 0),
            )
        )
        session.status = "active"
        self._events[session.exercise_id].append(
            {"event": "resumed", "timestamp": datetime.now(timezone.utc).isoformat(), "details": {}}
        )

    def end_exercise(self, exercise_id) -> dict:
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return {}
        self.dis_engine.network.send_pdu(
            self.dis_engine.factory.encode_stop_freeze(session.exercise_id, reason=2)
        )
        self.dis_engine.stop()
        self.c2sim_engine.server.disconnect()
        session.status = "completed"
        session.end_time = datetime.now(timezone.utc)
        report = {
            "exercise_id": session.exercise_id,
            "name": session.exercise_name,
            "duration_seconds": session.duration_seconds(),
            "entities_count": session.entities_count,
            "events_count": session.events_count,
            "status": session.status,
        }
        self._events[session.exercise_id].append(
            {"event": "ended", "timestamp": datetime.now(timezone.utc).isoformat(), "details": report}
        )
        return report

    def get_exercise(self, exercise_id) -> Optional[ExerciseSession]:
        return self._exercises.get(int(exercise_id))

    def get_active_exercises(self) -> List[ExerciseSession]:
        return [session for session in self._exercises.values() if session.status in {"active", "paused"}]

    def inject_scenario(self, exercise_id, scenario: dict):
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return
        self.c2sim_engine.send_initialization(scenario)
        injected_entities = 0
        for force in scenario.get("forces", []):
            for unit in force.get("units", []):
                ok = self.publish_entity(
                    exercise_id=session.exercise_id,
                    entity={
                        "entity_id": unit.get("unit_id"),
                        "name": unit.get("name"),
                        "affiliation": force.get("affiliation", "friendly"),
                        "entity_type": {
                            "kind": 1,
                            "domain": 1,
                            "country": int(unit.get("country_code", force.get("country_code", 178))),
                            "category": 1,
                            "subcategory": 0,
                            "specific": 0,
                            "extra": 0,
                        },
                        "position": {
                            "lat": (unit.get("position") or (0.0, 0.0))[0],
                            "lon": (unit.get("position") or (0.0, 0.0))[1],
                            "alt": 0.0,
                        },
                        "marking": unit.get("designation", ""),
                    },
                )
                if ok:
                    injected_entities += 1
        # Tactical exercise accounting: scenario injection is a control event and
        # should always increment event tracking even when live DIS transport is unavailable.
        session.events_count += 1
        self._events[session.exercise_id].append(
            {
                "event": "scenario_injected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": {"forces": len(scenario.get("forces", [])), "entities_injected": injected_entities},
            }
        )

    def get_exercise_entities(self, exercise_id) -> List[dict]:
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return []
        _ = session
        return self.dis_engine.receive_entities()

    def publish_entity(self, exercise_id, entity) -> bool:
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return False
        ok = self.dis_engine.publish_entity(dict(entity))
        if ok:
            session.entities_count += 1
            session.events_count += 1
            self._events[session.exercise_id].append(
                {
                    "event": "entity_published",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "details": {"entity_id": entity.get("entity_id")},
                }
            )
        return ok

    def receive_coalition_updates(self, exercise_id) -> List[dict]:
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return []
        entities = self.dis_engine.receive_entities()
        c2_msgs = self.c2sim_engine.receive_messages()
        updates = [{"protocol": "dis", "data": ent} for ent in entities] + [
            {"protocol": "c2sim", "data": msg} for msg in c2_msgs
        ]
        session.events_count += len(updates)
        return updates

    def generate_exercise_report(self, exercise_id) -> str:
        session = self._exercises.get(int(exercise_id))
        if session is None:
            return "Exercise not found"
        # Tactical context: in air-gapped mode this is deterministic text in place
        # of remote generation while preserving command-level briefing structure.
        return (
            f"Exercise Report: {session.exercise_name}\n"
            f"Status: {session.status}\n"
            f"Nations: {', '.join(n.get('name', 'Unknown') for n in session.participating_nations)}\n"
            f"Entities Published: {session.entities_count}\n"
            f"Events Logged: {session.events_count}\n"
        )

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "exercise_count": len(self._exercises),
            "active_count": len(self.get_active_exercises()),
            "dis": self.dis_engine.health_check(),
            "c2sim": self.c2sim_engine.health_check(),
            "orbat_stats": self.orbat_manager.get_statistics(),
        }

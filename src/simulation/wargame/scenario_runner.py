"""Scenario runner orchestrating adapter stepping, replay capture, and AAR output."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.simulation.adapters import BuiltinPhysicsEngine, GenericSimAdapter, ReplayRecorder
from src.simulation.models import (
    AARReport,
    EntityType,
    ScenarioDefinition,
    ScenarioStatus,
    SimConfig,
    SimulationState,
)
from src.simulation.wargame.aar_generator import AARGenerator
from src.simulation.wargame.opfor_generator import OpForGenerator


class ScenarioRunner:
    """Executes tactical scenarios and captures replay + AAR artifacts."""

    def __init__(self, adapter: GenericSimAdapter = None):
        if adapter is None:
            adapter = BuiltinPhysicsEngine(SimConfig(simulator_name="builtin"))
            adapter.connect()
        self.adapter = adapter
        self.replay_recorder = ReplayRecorder()
        self.aar_generator = AARGenerator()
        self.scenario: Optional[ScenarioDefinition] = None
        self.status = ScenarioStatus.DRAFT
        self._current_tick = 0
        self._running = False
        self._last_state: Optional[SimulationState] = None
        self._last_replay = None
        self._last_aar: Optional[AARReport] = None
        self._timeline: List[Dict[str, Any]] = []
        self._known_entities: set[str] = set()
        self._thread: Optional[Thread] = None
        self._lock = Lock()
        self._stop_requested = False

    def load(self, scenario: ScenarioDefinition) -> bool:
        """Load scenario into adapter and prepare status for execution."""
        if not isinstance(scenario, ScenarioDefinition):
            raise ValueError("scenario must be ScenarioDefinition")
        if not self.adapter.is_connected():
            self.adapter.connect()
        loaded = self.adapter.load_scenario(scenario)
        if loaded:
            self.scenario = scenario
            self.status = ScenarioStatus.LOADED
        return loaded

    def _check_objective_condition(self, condition: str, state: SimulationState) -> bool:
        friendlies = state.friendly_entities()
        enemies = state.enemy_entities()
        env = {
            "all_waypoints_visited": bool(state.metadata.get("all_waypoints_visited", False)),
            "friendly_losses": max(0, self._initial_friendly_count() - len(friendlies)),
            "enemy_losses": max(0, self._initial_enemy_count() - len(enemies)),
            "enemies_detected": int(state.metadata.get("enemies_detected", len(enemies))),
            "convoy_arrived": bool(state.metadata.get("convoy_arrived", False)),
            "installation_intact": bool(state.metadata.get("installation_intact", True)),
        }
        try:
            return bool(eval(condition, {"__builtins__": {}}, env))
        except Exception:
            return False

    def _initial_friendly_count(self) -> int:
        if self.scenario is None:
            return 0
        count = 0
        for force in self.scenario.forces:
            if force.allegiance == "friendly":
                count += sum(unit["count"] for unit in force.units)
        return count

    def _initial_enemy_count(self) -> int:
        if self.scenario is None:
            return 0
        count = 0
        for force in self.scenario.forces:
            if force.allegiance == "enemy":
                count += sum(unit["count"] for unit in force.units)
        return count

    def _detect_events(self, state: SimulationState) -> None:
        current_ids = {entity.entity_id for entity in state.entities}
        if not self._known_entities:
            self._known_entities = set(current_ids)
        else:
            new_entities = current_ids - self._known_entities
            removed_entities = self._known_entities - current_ids
            for entity_id in sorted(new_entities):
                self._timeline.append(
                    {
                        "type": "new_entity_detected",
                        "sim_time_seconds": state.sim_time_seconds,
                        "entity_id": entity_id,
                    }
                )
            for entity_id in sorted(removed_entities):
                self._timeline.append(
                    {
                        "type": "entity_killed",
                        "sim_time_seconds": state.sim_time_seconds,
                        "entity_id": entity_id,
                    }
                )
            self._known_entities = set(current_ids)

        for event in state.active_events:
            if event.get("type") == "engagement_started":
                self._timeline.append(
                    {
                        "type": "engagement_started",
                        "sim_time_seconds": state.sim_time_seconds,
                        "details": event,
                    }
                )

    def run(
        self,
        max_ticks: int = 6000,
        tick_dt: float = 0.1,
        opfor_controller=None,
    ) -> AARReport:
        """Run loaded scenario synchronously and return generated AAR."""
        if self.scenario is None:
            raise RuntimeError("no scenario loaded")
        if max_ticks <= 0:
            raise ValueError("max_ticks must be > 0")
        if tick_dt <= 0:
            raise ValueError("tick_dt must be > 0")

        self.status = ScenarioStatus.RUNNING
        self._running = True
        self._stop_requested = False
        self._current_tick = 0
        self._timeline = []
        self._known_entities = set()
        replay_id = self.replay_recorder.start_recording(
            simulator_name=self.adapter.config.simulator_name,
            scenario_id=self.scenario.scenario_id,
        )
        self.adapter.start_simulation()

        objectives_met: set[str] = set()
        objectives_failed: set[str] = set()

        for tick in range(max_ticks):
            if self._stop_requested:
                self.status = ScenarioStatus.ABORTED
                break
            self._current_tick = tick + 1
            state = self.adapter.step(tick_dt)
            self._last_state = state
            self.replay_recorder.record_tick(state)
            self._detect_events(state)

            if opfor_controller is not None:
                behaviors = opfor_controller.generate_behavior(state)
                opfor_controller.apply_behavior(self.adapter, behaviors)

            for objective in self.scenario.objectives:
                description = str(objective.get("description", "unnamed objective"))
                condition = str(objective.get("success_condition", "False"))
                if self._check_objective_condition(condition, state):
                    if description not in objectives_met:
                        objectives_met.add(description)
                        self._timeline.append(
                            {
                                "type": "objective_completed",
                                "sim_time_seconds": state.sim_time_seconds,
                                "objective": description,
                            }
                        )

            friendlies_alive = len(state.friendly_entities())
            enemies_alive = len(state.enemy_entities())
            if enemies_alive == 0:
                self._timeline.append(
                    {
                        "type": "termination",
                        "sim_time_seconds": state.sim_time_seconds,
                        "reason": "all_enemies_defeated",
                    }
                )
                self.status = ScenarioStatus.COMPLETED
                break
            if friendlies_alive == 0:
                self._timeline.append(
                    {
                        "type": "termination",
                        "sim_time_seconds": state.sim_time_seconds,
                        "reason": "all_friendlies_lost",
                    }
                )
                self.status = ScenarioStatus.COMPLETED
                break
            if state.sim_time_seconds >= self.scenario.duration_seconds:
                self._timeline.append(
                    {
                        "type": "termination",
                        "sim_time_seconds": state.sim_time_seconds,
                        "reason": "duration_exceeded",
                    }
                )
                self.status = ScenarioStatus.COMPLETED
                break
        else:
            self.status = ScenarioStatus.COMPLETED

        if self._last_state is None:
            self._last_state = self.adapter.get_state()

        for objective in self.scenario.objectives:
            description = str(objective.get("description", "unnamed objective"))
            if description not in objectives_met:
                objectives_failed.add(description)

        self.adapter.stop_simulation()
        self._last_replay = self.replay_recorder.stop_recording()
        aar = self.aar_generator.generate(
            scenario=self.scenario,
            final_state=self._last_state,
            timeline=self._timeline,
            replay=self._last_replay,
        )
        aar.objectives_met = sorted(objectives_met)
        aar.objectives_failed = sorted(objectives_failed)
        self._last_aar = aar
        self._running = False
        return aar

    def run_async(
        self,
        max_ticks: int = 6000,
        tick_dt: float = 0.1,
        opfor_controller: Optional[OpForGenerator] = None,
    ) -> bool:
        """Run scenario in background thread for non-blocking control loops."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            def _worker() -> None:
                try:
                    self.run(max_ticks=max_ticks, tick_dt=tick_dt, opfor_controller=opfor_controller)
                except Exception:
                    self.status = ScenarioStatus.FAILED
                finally:
                    self._running = False

            self._thread = Thread(target=_worker, daemon=True)
            self._thread.start()
        return True

    def get_status(self) -> dict:
        """Return live runner status for operational dashboards."""
        state = self._last_state or self.adapter.get_state()
        return {
            "scenario_id": self.scenario.scenario_id if self.scenario else None,
            "status": self.status.value,
            "running": self._running,
            "tick": self._current_tick,
            "sim_time_seconds": state.sim_time_seconds,
            "entities_alive": len(state.entities),
            "friendlies_alive": len(state.friendly_entities()),
            "enemies_alive": len(state.enemy_entities()),
        }

    def stop(self) -> None:
        """Stop a currently running scenario execution."""
        self._stop_requested = True
        self._running = False

    def get_replay(self):
        """Return replay artifact from last completed run."""
        return self._last_replay

    def get_aar(self) -> Optional[AARReport]:
        """Return AAR report from last completed run."""
        return self._last_aar

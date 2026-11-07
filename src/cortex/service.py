"""Cortex COP integration — mission bindings and quarantine recommendations."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

from src.cop.event_bus import CopEvent, CopEventBus, build_event, get_event_bus
from src.cortex.mission_config import load_mission_cortex_settings
from src.cortex.minimal_profile import plan_minimal_profile
from src.cortex.models import BindingSource, MissionBinding, MinimalProfilePlan
from src.cortex.twin import NetworkTwin

_Handler = Callable[[CopEvent], None]

# Trusted COP payload keys for mission lifecycle (not free-form operator text).
_MISSION_ACTIVATE = "mission_activate"
_MISSION_END = "mission_end"
_CORTEX_RECOMMENDATION = "cortex_recommendation"


class CortexMissionService:
    """Subscribe to :class:`CopEventBus` and keep the twin mission-aware."""

    def __init__(
        self,
        twin: Optional[NetworkTwin] = None,
        event_bus: Optional[CopEventBus] = None,
        *,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._config = config or load_mission_cortex_settings()
        self.twin = twin or NetworkTwin()
        self._bus = event_bus or get_event_bus()
        self._track = str(self._config.get("event_track", "cyber_cortex"))
        self._lock = threading.Lock()
        self._bus.subscribe(self._on_cop_event)

    def register_binding(self, binding: MissionBinding) -> MissionBinding:
        if binding.source not in (BindingSource.OPERATOR, BindingSource.MISSION_PLANNER):
            raise ValueError("mission bindings must originate from trusted sources")
        with self._lock:
            self.twin.store_binding(binding)
        return binding

    def activate_mission(self, mission_id: str) -> MissionBinding:
        with self._lock:
            binding = self.twin.activate_binding(mission_id)
        self._publish_lifecycle(_MISSION_ACTIVATE, binding)
        return binding

    def end_mission(self, mission_id: str) -> MissionBinding:
        with self._lock:
            binding = self.twin.deactivate_binding(mission_id)
        self._publish_lifecycle(_MISSION_END, binding)
        return binding

    def handle_cop_mission_event(self, event: CopEvent) -> None:
        """Apply operator/planner mission lifecycle events from the COP bus."""
        payload = event.payload or {}
        if event.event_type not in (_MISSION_ACTIVATE, _MISSION_END):
            return
        binding_payload = payload.get("binding")
        if not isinstance(binding_payload, dict):
            return
        source_raw = str(payload.get("binding_source", binding_payload.get("source", "")))
        try:
            source = BindingSource(source_raw)
        except ValueError:
            return
        binding_payload = dict(binding_payload)
        binding_payload["source"] = source
        try:
            binding = MissionBinding.model_validate(binding_payload)
        except Exception:
            return
        if source not in (BindingSource.OPERATOR, BindingSource.MISSION_PLANNER):
            return
        with self._lock:
            self.twin.store_binding(binding)
            if event.event_type == _MISSION_ACTIVATE:
                self.twin.activate_binding(binding.mission_id)
            else:
                self.twin.deactivate_binding(binding.mission_id)

    def propose_minimal_profile(self, node: str) -> MinimalProfilePlan:
        with self._lock:
            plan = plan_minimal_profile(self.twin, node)
        self._publish_recommendation(plan)
        return plan

    def _on_cop_event(self, event: CopEvent) -> None:
        if event.event_type in (_MISSION_ACTIVATE, _MISSION_END):
            self.handle_cop_mission_event(event)

    def _publish_lifecycle(self, event_type: str, binding: MissionBinding) -> None:
        self._bus.emit(
            track=self._track,
            event_type=event_type,
            payload={
                "mission_id": binding.mission_id,
                "binding": binding.model_dump(mode="json"),
                "binding_source": binding.source.value,
                "required_flows": [
                    {"source": s, "destination": d, "purpose": p}
                    for s, d, p in sorted(self.twin.required_flows)
                ],
            },
            route_hint="tactical",
            confidence=1.0,
            requires_human_review=False,
        )

    def _publish_recommendation(self, plan: MinimalProfilePlan) -> None:
        self._bus.emit(
            track=self._track,
            event_type=_CORTEX_RECOMMENDATION,
            payload={
                "node": plan.node,
                "keep_edges": plan.keep_edges,
                "narrow_edges": [c.model_dump() for c in plan.narrow_edges],
                "escalates_to_human": plan.escalates_to_human,
                "reason": plan.reason,
            },
            route_hint="planning",
            confidence=0.85 if not plan.escalates_to_human else 0.4,
            requires_human_review=plan.escalates_to_human,
        )


def binding_from_planner_payload(payload: Dict[str, Any]) -> MissionBinding:
    """Validate structured planner output — never accept raw NL text as binding."""
    data = dict(payload)
    data["source"] = BindingSource.MISSION_PLANNER
    return MissionBinding.model_validate(data)

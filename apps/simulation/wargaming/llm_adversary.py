"""LLM-assisted red-force adversary behavior generator."""

from __future__ import annotations

import json
from random import Random
from typing import List, Optional
from uuid import uuid4

from apps.simulation.models import AdversaryProfile
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class LLMAdversary:
    """Red-force commander with LLM reasoning and doctrinal scripted fallback."""

    def __init__(self, profile: AdversaryProfile = None):
        self._profiles = self._build_profiles()
        self.profile = profile or self._profiles[0]
        self._orchestrator = Orchestrator()
        self._rng = Random(73)

    def _build_profiles(self) -> List[AdversaryProfile]:
        return [
            AdversaryProfile(
                profile_id="profile-competent",
                name="Competent Adversary",
                difficulty="competent",
                doctrine="Balanced offense-defense with measured pressure on enemy flanks.",
                personality_traits=["adaptive", "disciplined"],
                preferred_tactics=["recon", "flanking", "attrition"],
                llm_system_prompt="You are a competent operational commander balancing risk and opportunity.",
            ),
            AdversaryProfile(
                profile_id="profile-insurgent",
                name="Insurgent Commander",
                difficulty="expert",
                doctrine="Harass logistics and execute deceptive ambush cycles.",
                personality_traits=["aggressive", "deceptive", "adaptive"],
                preferred_tactics=["ambush", "hit_and_run", "dispersion"],
                llm_system_prompt="You command insurgent cells. Favor ambush, deception, and survivability.",
            ),
            AdversaryProfile(
                profile_id="profile-navy",
                name="Peer Navy Admiral",
                difficulty="grandmaster",
                doctrine="Methodical combined-arms sequencing with maritime fires.",
                personality_traits=["methodical", "patient"],
                preferred_tactics=["screening", "concentrated_fire", "maneuver"],
                llm_system_prompt="You command a peer naval force; maintain formation discipline and decisive fires.",
            ),
            AdversaryProfile(
                profile_id="profile-apt",
                name="Cyber APT Group",
                difficulty="expert",
                doctrine="Stealthy escalation with reconnaissance before exploitation.",
                personality_traits=["stealthy", "patient", "calculating"],
                preferred_tactics=["recon", "deception", "escalation"],
                llm_system_prompt="You are an advanced persistent threat operator with stealth-first doctrine.",
            ),
            AdversaryProfile(
                profile_id="profile-swarm",
                name="Swarm Tactician",
                difficulty="grandmaster",
                doctrine="Overwhelm weak sectors using mass and sacrificial probes.",
                personality_traits=["relentless", "adaptive"],
                preferred_tactics=["swarm", "feint", "concentrated_force"],
                llm_system_prompt="You employ swarm doctrine: probe, feint, then mass against weak points.",
            ),
        ]

    def _extract_units(self, force_composition: dict, state: dict, allegiance: str) -> List[dict]:
        key = f"{allegiance}_units"
        if isinstance(force_composition.get(key), list):
            return list(force_composition[key])
        units = []
        for unit in state.get("units", []):
            if unit.get("allegiance") == allegiance:
                units.append(unit)
        return units

    def _nearest_enemy(self, unit: dict, enemies: List[dict]) -> Optional[dict]:
        if not enemies:
            return None
        ux, uy = unit.get("position", (0.0, 0.0))
        return min(enemies, key=lambda e: (e.get("position", (0.0, 0.0))[0] - ux) ** 2 + (e.get("position", (0.0, 0.0))[1] - uy) ** 2)

    def _scripted_fallback(self, state: dict, force_composition: dict, difficulty: str) -> List[dict]:
        red_units = self._extract_units(force_composition, state, "red")
        blue_units = self._extract_units(force_composition, state, "blue")
        orders: List[dict] = []
        for idx, unit in enumerate(red_units):
            nearest = self._nearest_enemy(unit, blue_units)
            x, y = unit.get("position", (0.0, 0.0))
            target = (x + self._rng.uniform(-10, 10), y + self._rng.uniform(-10, 10))
            action = "move"
            reasoning = "Default doctrinal movement."

            if difficulty == "novice":
                action = "move"
                reasoning = "Novice doctrine: random repositioning and opportunistic contact only."
                if nearest and len(red_units) >= len(blue_units):
                    action = "defend"
            elif difficulty == "competent":
                if nearest:
                    target = tuple(nearest.get("position", (x, y)))
                    action = "attack" if unit.get("health", 1.0) > 0.6 else "move"
                reasoning = "Competent doctrine: close distance and engage when advantage is favorable."
            elif difficulty == "expert":
                if nearest:
                    nx, ny = nearest.get("position", (x, y))
                    flank = 15.0 if idx % 2 == 0 else -15.0
                    target = (nx + flank, ny - flank)
                    action = "attack" if unit.get("health", 1.0) >= 0.45 else "retreat"
                reasoning = "Expert doctrine: flanking maneuvers, coordinated fire, and tactical withdrawal."
            else:
                if nearest:
                    nx, ny = nearest.get("position", (x, y))
                    weak_shift = 25.0 if idx % 3 == 0 else -20.0
                    target = (nx + weak_shift, ny)
                action = "ambush" if idx % 2 == 0 else "attack"
                reasoning = "Grandmaster doctrine: deception, feints, and concentrated strike on weak sectors."

            orders.append(
                {
                    "unit_id": str(unit.get("unit_id", f"red-{idx}")),
                    "action": action,
                    "target": (float(target[0]), float(target[1])),
                    "reasoning": reasoning,
                }
            )
        return orders

    def decide(self, state: dict, force_composition: dict, turn_number: int) -> List[dict]:
        red_units = self._extract_units(force_composition, state, "red")
        blue_units = self._extract_units(force_composition, state, "blue")
        system_prompt = (
            f"You are {self.profile.name}. Your doctrine: {self.profile.doctrine}. "
            f"Traits: {', '.join(self.profile.personality_traits)}. "
            f"Preferred tactics: {', '.join(self.profile.preferred_tactics)}."
        )
        situation_prompt = (
            f"Turn {turn_number}. Your forces: {red_units}. Enemy forces (known): {blue_units}. "
            f"Terrain: {state.get('terrain', 'desert')}. Previous events: {state.get('last_turn_events', [])}."
        )
        ask = (
            "Issue orders for each of your units. Respond with JSON: "
            "[{unit_id, action: move|attack|defend|retreat|recon|ambush, target_position, reasoning}]. "
            "Think step by step about your tactical approach."
        )
        prompt = f"{system_prompt}\n{situation_prompt}\n{ask}"
        try:
            response = self._orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
            text = getattr(response, "text", "") or ""
            parsed = json.loads(text)
            if isinstance(parsed, list):
                orders: List[dict] = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    uid = str(item.get("unit_id", "")).strip()
                    action = str(item.get("action", "move")).lower().strip()
                    target = item.get("target_position", item.get("target", (0.0, 0.0)))
                    if isinstance(target, list):
                        target = tuple(target)
                    if not uid or not isinstance(target, tuple) or len(target) < 2:
                        continue
                    if action not in {"move", "attack", "defend", "retreat", "recon", "ambush"}:
                        action = "move"
                    orders.append(
                        {
                            "unit_id": uid,
                            "action": action,
                            "target": (float(target[0]), float(target[1])),
                            "reasoning": str(item.get("reasoning", "LLM-directed tactical action.")),
                        }
                    )
                if orders:
                    return orders
        except Exception:
            pass
        return self._scripted_fallback(state, force_composition, self.profile.difficulty)

    def get_profiles(self) -> List[AdversaryProfile]:
        return list(self._profiles)

    def create_profile(self, name, difficulty, doctrine, traits, tactics) -> AdversaryProfile:
        profile = AdversaryProfile(
            profile_id=f"profile-{uuid4().hex[:8]}",
            name=str(name),
            difficulty=str(difficulty),
            doctrine=str(doctrine),
            personality_traits=[str(t) for t in traits],
            preferred_tactics=[str(t) for t in tactics],
            llm_system_prompt=(
                f"You are {name}. Doctrine: {doctrine}. Traits: {', '.join(traits)}. "
                f"Tactics: {', '.join(tactics)}."
            ),
        )
        self._profiles.append(profile)
        return profile

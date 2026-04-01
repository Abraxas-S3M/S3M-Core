"""Turn-level tactical resolution engine for Layer 12 wargames."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from random import Random
from typing import List, Optional

from apps.simulation.models import WargameConfig, WargameTurn


class TurnResolver:
    """Processes movement, combat, recon, and victory checks per turn."""

    def __init__(self):
        self._rng = Random(101)
        self._terrain_modifiers = {
            "desert": {"attack": 1.0, "defend": 0.8},
            "urban": {"attack": 0.7, "defend": 1.3},
            "forest": {"attack": 0.8, "defend": 1.1},
            "mountain": {"attack": 0.6, "defend": 1.4},
            "open": {"attack": 1.1, "defend": 0.7},
        }

    def _get_unit(self, state: dict, unit_id: str) -> Optional[dict]:
        for unit in state.get("units", []):
            if unit.get("unit_id") == unit_id:
                return unit
        return None

    def _unit_alive(self, unit: dict) -> bool:
        return unit.get("health", 0.0) > 0.0 and unit.get("size", 0) > 0

    def _apply_damage(self, unit: dict, losses: int) -> int:
        losses = max(0, int(losses))
        size = int(unit.get("size", 0))
        if size <= 0:
            unit["health"] = 0.0
            return 0
        actual = min(size, losses)
        unit["size"] = size - actual
        unit["health"] = 0.0 if unit["size"] <= 0 else max(0.1, unit.get("health", 1.0) * (unit["size"] / size))
        return actual

    def _move_toward(self, pos: tuple, target: tuple, step: float = 10.0) -> tuple:
        x, y = float(pos[0]), float(pos[1])
        tx, ty = float(target[0]), float(target[1])
        dx, dy = tx - x, ty - y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= step or dist == 0:
            return (tx, ty)
        scale = step / dist
        return (x + dx * scale, y + dy * scale)

    def resolve(self, blue_orders: List[dict], red_orders: List[dict], current_state: dict, config: WargameConfig) -> WargameTurn:
        state = deepcopy(current_state)
        state.setdefault("units", [])
        state.setdefault("turn", 0)
        events: List[dict] = []
        blue_losses = 0
        red_losses = 0

        combined_orders = [("blue", order) for order in blue_orders] + [("red", order) for order in red_orders]

        # Tactical context: movement is resolved first to emulate maneuver phase before fires.
        for _, order in combined_orders:
            unit = self._get_unit(state, str(order.get("unit_id", "")))
            if not unit or not self._unit_alive(unit):
                continue
            action = str(order.get("action", "move")).lower()
            if action not in {"move", "retreat"}:
                continue
            target = order.get("target", order.get("target_position", unit.get("position", (0.0, 0.0))))
            if isinstance(target, list):
                target = tuple(target)
            if not isinstance(target, tuple) or len(target) < 2:
                continue
            start = tuple(unit.get("position", (0.0, 0.0)))
            if action == "retreat":
                sx, sy = start
                tx, ty = target[:2]
                target = (sx - (tx - sx), sy - (ty - sy))
            unit["position"] = self._move_toward(start, target)
            events.append({"type": "movement", "unit_id": unit["unit_id"], "from": start, "to": unit["position"]})

        # Recon updates visibility graph for fog-of-war approximations.
        for _, order in combined_orders:
            if str(order.get("action", "")).lower() != "recon":
                continue
            unit = self._get_unit(state, str(order.get("unit_id", "")))
            if not unit or not self._unit_alive(unit):
                continue
            range_m = float(unit.get("recon_range", 40.0))
            ux, uy = unit.get("position", (0.0, 0.0))
            for target in state.get("units", []):
                if target.get("allegiance") == unit.get("allegiance") or not self._unit_alive(target):
                    continue
                tx, ty = target.get("position", (0.0, 0.0))
                d2 = (tx - ux) ** 2 + (ty - uy) ** 2
                if d2 <= range_m ** 2:
                    events.append(
                        {
                            "type": "detection",
                            "detector": unit.get("unit_id"),
                            "target": target.get("unit_id"),
                            "confidence": round(max(0.5, 1.0 - (d2 ** 0.5) / (range_m + 1e-6)), 2),
                        }
                    )

        for _, order in combined_orders:
            action = str(order.get("action", "")).lower()
            unit = self._get_unit(state, str(order.get("unit_id", "")))
            if not unit or not self._unit_alive(unit):
                continue
            if action == "defend":
                unit["fortified"] = True
                events.append({"type": "fortify", "unit_id": unit["unit_id"], "bonus": 1.5})
            if action == "ambush":
                zone = order.get("target", order.get("target_position", unit.get("position", (0.0, 0.0))))
                if isinstance(zone, list):
                    zone = tuple(zone)
                unit["ambush_zone"] = (float(zone[0]), float(zone[1])) if isinstance(zone, tuple) and len(zone) >= 2 else tuple(unit.get("position", (0.0, 0.0)))
                unit["ambush_ready"] = True
                events.append({"type": "ambush_prepared", "unit_id": unit["unit_id"], "zone": unit["ambush_zone"]})

        for side, order in combined_orders:
            action = str(order.get("action", "")).lower()
            if action != "attack":
                continue
            attacker = self._get_unit(state, str(order.get("unit_id", "")))
            if not attacker or not self._unit_alive(attacker):
                continue

            target_id = str(order.get("target_unit_id", "")).strip()
            defender = self._get_unit(state, target_id) if target_id else None
            if defender is None:
                enemies = [u for u in state.get("units", []) if u.get("allegiance") != attacker.get("allegiance") and self._unit_alive(u)]
                if not enemies:
                    continue
                ax, ay = attacker.get("position", (0.0, 0.0))
                defender = min(enemies, key=lambda e: (e.get("position", (0.0, 0.0))[0] - ax) ** 2 + (e.get("position", (0.0, 0.0))[1] - ay) ** 2)

            terrain = str(state.get("terrain", config.parameters.get("terrain", "desert")))
            outcome = self.compute_engagement(attacker, defender, terrain)

            a_loss = self._apply_damage(attacker, int(outcome["attacker_losses"]))
            d_loss = self._apply_damage(defender, int(outcome["defender_losses"]))
            if side == "blue":
                blue_losses += a_loss
                red_losses += d_loss
            else:
                red_losses += a_loss
                blue_losses += d_loss

            events.append(
                {
                    "type": "engagement",
                    "attacker": attacker.get("unit_id"),
                    "defender": defender.get("unit_id"),
                    "position": tuple(defender.get("position", (0.0, 0.0))),
                    "result": outcome["outcome"],
                    "detail": outcome["detail"],
                    "attacker_losses": a_loss,
                    "defender_losses": d_loss,
                }
            )

        state["units"] = [u for u in state.get("units", []) if self._unit_alive(u)]
        state["turn"] = int(state.get("turn", 0)) + 1
        state["last_turn_events"] = list(events)
        victory = self.check_victory(state, config.victory_conditions)
        if victory:
            events.append({"type": "victory", "outcome": victory})

        return WargameTurn(
            turn_number=state["turn"],
            timestamp=datetime.now(timezone.utc),
            blue_orders=blue_orders,
            red_orders=red_orders,
            events=events,
            state_snapshot=state,
            blue_losses=blue_losses,
            red_losses=red_losses,
        )

    def compute_engagement(self, attacker: dict, defender: dict, terrain: str) -> dict:
        terrain_mod = self._terrain_modifiers.get(terrain, self._terrain_modifiers["desert"])
        a_size = float(attacker.get("size", 1))
        d_size = float(defender.get("size", 1))
        a_cond = float(attacker.get("condition", attacker.get("health", 1.0)))
        d_cond = float(defender.get("condition", defender.get("health", 1.0)))

        ambush_bonus = 2.0 if attacker.get("ambush_ready") else 1.0
        if attacker.get("ambush_ready"):
            attacker["ambush_ready"] = False

        fort_bonus = 1.5 if defender.get("fortified") else 1.0

        attacker_strength = a_size * a_cond * terrain_mod["attack"] * ambush_bonus
        defender_strength = d_size * d_cond * terrain_mod["defend"] * fort_bonus
        randomness = 1.0 + self._rng.uniform(-0.2, 0.2)
        ratio = (attacker_strength / max(defender_strength, 0.1)) * randomness

        attacker_losses = 0
        defender_losses = 0
        outcome = "draw"
        detail = f"ratio={ratio:.2f}"

        if ratio > 3.0:
            defender_losses = int(max(1, round(d_size)))
            outcome = "attacker_wins"
            detail += "; defender overrun"
        elif 2.0 <= ratio <= 3.0:
            defender_losses = int(max(1, round(d_size * 0.5)))
            attacker_losses = int(max(0, round(a_size * 0.1)))
            outcome = "attacker_wins"
            detail += "; defender heavily damaged"
        elif 1.0 <= ratio < 2.0:
            defender_losses = int(max(1, round(d_size * 0.3)))
            attacker_losses = int(max(1, round(a_size * 0.3)))
            outcome = "draw"
            detail += "; both sides damaged"
        else:
            attacker_losses = int(max(1, round(a_size * 0.4)))
            defender_losses = int(max(0, round(d_size * 0.1)))
            outcome = "defender_wins"
            detail += "; attack repelled"

        return {
            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
            "outcome": outcome,
            "detail": detail,
        }

    def check_victory(self, state: dict, conditions: List[dict]) -> Optional[str]:
        blue_units = [u for u in state.get("units", []) if u.get("allegiance") == "blue"]
        red_units = [u for u in state.get("units", []) if u.get("allegiance") == "red"]

        if not red_units and blue_units:
            return "blue_victory"
        if not blue_units and red_units:
            return "red_victory"

        initial = state.get("initial_counts", {"blue": max(1, len(blue_units)), "red": max(1, len(red_units))})
        blue_losses_pct = 100.0 * max(0, (initial.get("blue", 1) - len(blue_units))) / max(1, initial.get("blue", 1))
        red_losses_pct = 100.0 * max(0, (initial.get("red", 1) - len(red_units))) / max(1, initial.get("red", 1))

        for condition in conditions:
            ctype = str(condition.get("type", "")).lower()
            target = str(condition.get("target", "")).lower()
            threshold = float(condition.get("threshold_pct", 100.0))
            if ctype == "eliminate" and target == "red" and red_losses_pct >= threshold:
                return "blue_victory"
            if ctype == "eliminate" and target == "blue" and blue_losses_pct >= threshold:
                return "red_victory"

        return None

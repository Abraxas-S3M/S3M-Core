"""Normalization helpers for simulation-only HLA interoperability."""

from __future__ import annotations

from typing import Any

from packages.providers.sim_hla.coordinates import Phase16CoordinateConverter


class HLANormalizer:
    """Convert HLA object/interaction payloads into S3M-compatible structures."""

    def __init__(self) -> None:
        self._converter = Phase16CoordinateConverter()

    @staticmethod
    def _force_label(force_id: int) -> str:
        if int(force_id) == 1:
            return "friendly"
        if int(force_id) == 2:
            return "hostile"
        return "neutral"

    @staticmethod
    def _damage_label(damage_state: int) -> str:
        if int(damage_state) <= 0:
            return "undamaged"
        if int(damage_state) < 3:
            return "damaged"
        return "destroyed"

    def normalize_object_update(self, update: dict[str, Any]) -> dict[str, Any]:
        world = update.get("world_location") or update.get("position_ecef") or {}
        if isinstance(world, (tuple, list)) and len(world) >= 3:
            x, y, z = float(world[0]), float(world[1]), float(world[2])
        else:
            x = float(world.get("x", 0.0))
            y = float(world.get("y", 0.0))
            z = float(world.get("z", 0.0))
        lat, lon, alt = self._converter.ecef_to_lla(x, y, z)

        velocity_raw = update.get("velocity") or {}
        if isinstance(velocity_raw, (tuple, list)) and len(velocity_raw) >= 3:
            velocity = (float(velocity_raw[0]), float(velocity_raw[1]), float(velocity_raw[2]))
        else:
            velocity = (
                float(velocity_raw.get("x", 0.0)),
                float(velocity_raw.get("y", 0.0)),
                float(velocity_raw.get("z", 0.0)),
            )

        return {
            "entity_id": str(update.get("object_id", "")),
            "entity_type": str(update.get("entity_type", "Unknown")),
            "position": (lat, lon, alt),
            "velocity": velocity,
            "force": self._force_label(int(update.get("force_id", 3))),
            "name": str(update.get("name", update.get("marking", ""))),
            "damage": self._damage_label(int(update.get("damage_state", 0))),
            "source": "hla",
        }

    def normalize_interaction(self, interaction: dict[str, Any]) -> dict[str, Any]:
        interaction_type = str(interaction.get("interaction_type", "")).strip()
        mapping = {
            "weaponfire": "fire",
            "detonation": "detonation",
            "radiotransmit": "radio",
        }
        event_type = mapping.get(interaction_type.lower(), interaction_type.lower() or "unknown")
        return {
            "event_type": event_type,
            "parameters": dict(interaction.get("parameters", {})),
            "source": "hla",
        }

    def hla_to_dis_entity(self, hla_entity: dict[str, Any]) -> dict[str, Any]:
        position = hla_entity.get("position")
        if isinstance(position, (tuple, list)) and len(position) >= 3:
            lat, lon, alt = float(position[0]), float(position[1]), float(position[2])
        else:
            world = hla_entity.get("world_location") or hla_entity.get("position_ecef") or {}
            x = float(world.get("x", 0.0))
            y = float(world.get("y", 0.0))
            z = float(world.get("z", 0.0))
            lat, lon, alt = self._converter.ecef_to_lla(x, y, z)

        velocity = hla_entity.get("velocity") or {}
        return {
            "entity_id": str(hla_entity.get("object_id", hla_entity.get("entity_id", ""))),
            "position": {"lat": lat, "lon": lon, "alt": alt},
            "velocity": {
                "x": float(velocity.get("x", 0.0)),
                "y": float(velocity.get("y", 0.0)),
                "z": float(velocity.get("z", 0.0)),
            },
            "affiliation": self._force_label(int(hla_entity.get("force_id", 3))),
            "marking": str(hla_entity.get("name", hla_entity.get("marking", ""))),
            "source": "hla",
        }

    def dis_to_hla_entity(self, dis_entity: dict[str, Any]) -> dict[str, Any]:
        position = dis_entity.get("position", {})
        if isinstance(position, (tuple, list)) and len(position) >= 3:
            lat, lon, alt = float(position[0]), float(position[1]), float(position[2])
        else:
            lat = float(position.get("lat", 0.0))
            lon = float(position.get("lon", 0.0))
            alt = float(position.get("alt", 0.0))
        x, y, z = self._converter.lla_to_ecef(lat, lon, alt)
        affiliation = str(dis_entity.get("affiliation", "neutral")).lower()
        force_id = 1 if affiliation in {"friendly", "blue", "allied"} else 2 if affiliation in {"hostile", "enemy", "red"} else 3
        return {
            "object_id": str(dis_entity.get("entity_id", "")),
            "entity_type": str(dis_entity.get("entity_type", "Aircraft")),
            "world_location": {"x": x, "y": y, "z": z},
            "velocity": dict(dis_entity.get("velocity", {"x": 0.0, "y": 0.0, "z": 0.0})),
            "force_id": force_id,
            "name": str(dis_entity.get("marking", dis_entity.get("name", ""))),
            "source": "dis",
        }

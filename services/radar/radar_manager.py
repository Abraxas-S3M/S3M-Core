"""Lifecycle manager for radar configuration registration.

Military context:
This registry provides deterministic in-memory radar bookkeeping so tactical
simulation runs can reproduce the same reconnaissance order of battle offline.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from services.radar.models import RadarConfig


class RadarManager:
    """Manage radar configurations for simulation and planning services."""

    def __init__(self) -> None:
        self._radars_by_id: Dict[str, RadarConfig] = {}
        self._ordered_ids: List[str] = []

    def register_radar(self, config: RadarConfig) -> RadarConfig:
        """Register one radar configuration and return the stored config."""
        if not isinstance(config, RadarConfig):
            raise TypeError("config must be a RadarConfig instance")
        if config.radar_id in self._radars_by_id:
            raise ValueError(f"radar_id already registered: {config.radar_id}")
        self._radars_by_id[config.radar_id] = config
        self._ordered_ids.append(config.radar_id)
        return config

    def list_radars(self) -> List[RadarConfig]:
        """Return radar configs in registration order."""
        return [self._radars_by_id[radar_id] for radar_id in self._ordered_ids]

    def get_radar(self, radar_id: str) -> Optional[RadarConfig]:
        """Return one radar config by ID if present."""
        return self._radars_by_id.get(radar_id)

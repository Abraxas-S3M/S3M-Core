"""Preset radar suite builders for tactical deployment templates.

Military context:
The Krechet suite places multiple radars around a defended center to provide
layered, overlapping surveillance in a deterministic offline simulation.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from services.radar.models import RadarBand, RadarConfig, RadarType, RadarUnit
from services.radar.radar_manager import RadarManager


def _parse_center(raw_center: Sequence[float]) -> Tuple[float, float, float]:
    if len(raw_center) != 3:
        raise ValueError("center must be [x_m, y_m, z_m]")
    try:
        return (float(raw_center[0]), float(raw_center[1]), float(raw_center[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError("center must contain numeric coordinates") from exc


def create_krechet_radar_suite(manager: RadarManager, center: Sequence[float]) -> List[RadarUnit]:
    x, y, z = _parse_center(center)
    templates = [
        ("Krechet North", "كريتشيت شمال", (0.0, 15000.0, 30.0), RadarType.AESA, RadarBand.S, 120000.0),
        ("Krechet East", "كريتشيت شرق", (15000.0, 0.0, 25.0), RadarType.GENERIC_3D, RadarBand.X, 90000.0),
        ("Krechet South", "كريتشيت جنوب", (0.0, -15000.0, 20.0), RadarType.COUNTER_BATTERY, RadarBand.C, 70000.0),
        ("Krechet West", "كريتشيت غرب", (-15000.0, 0.0, 25.0), RadarType.FIRE_CONTROL, RadarBand.KU, 60000.0),
    ]
    units: List[RadarUnit] = []
    for name_en, name_ar, (dx, dy, dz), radar_type, band, max_range_m in templates:
        config = RadarConfig(
            name_en=name_en,
            name_ar=name_ar,
            radar_type=radar_type,
            band=band,
            position=(x + dx, y + dy, z + dz),
            max_range_m=max_range_m,
        )
        units.append(manager.register_radar(config))
    return units


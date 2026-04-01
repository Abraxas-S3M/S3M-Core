"""Shared tactical AOIs for GEOINT providers."""

from __future__ import annotations

GEOINT_SAUDI_AOIS: dict[str, list[float]] = {
    "full_saudi": [34.0, 16.0, 56.0, 33.0],
    "persian_gulf": [46.0, 24.0, 56.5, 30.5],
    "red_sea": [32.0, 16.0, 44.0, 29.5],
    "riyadh_corridor": [45.5, 23.0, 48.5, 26.5],
    "eastern_province": [47.0, 23.5, 52.5, 29.5],
    "yemen_border": [42.0, 16.0, 47.0, 19.0],
}

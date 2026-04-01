"""Reusable Sentinel Hub evalscripts used by S3M tactical GEOINT workflows."""

from __future__ import annotations

SAR_SHIP_ENHANCEMENT = """//VERSION=3
function setup() { return { input: ["VV", "VH"], output: { bands: 3 } }; }
function evaluatePixel(s) {
  let ratio = s.VV / (s.VH + 0.0001);
  return [s.VV * 3.0, s.VH * 3.0, ratio > 5 ? 1 : 0];
}
"""

TRUE_COLOR_S2 = """//VERSION=3
function setup() { return { input: ["B04", "B03", "B02"], output: { bands: 3 } }; }
function evaluatePixel(s) { return [2.5 * s.B04, 2.5 * s.B03, 2.5 * s.B02]; }
"""

NDVI = """//VERSION=3
function setup() { return { input: ["B04", "B08"], output: { bands: 1 } }; }
function evaluatePixel(s) { return [(s.B08 - s.B04) / (s.B08 + s.B04 + 0.0001)]; }
"""

NDWI = """//VERSION=3
function setup() { return { input: ["B03", "B08"], output: { bands: 1 } }; }
function evaluatePixel(s) { return [(s.B03 - s.B08) / (s.B03 + s.B08 + 0.0001)]; }
"""

DUST_AEROSOL = """//VERSION=3
function setup() { return { input: ["AER_AI_340_380"], output: { bands: 1 } }; }
function evaluatePixel(s) { return [s.AER_AI_340_380]; }
"""

THERMAL_HOTSPOT = """//VERSION=3
function setup() { return { input: ["S8"], output: { bands: 1 } }; }
function evaluatePixel(s) { return [s.S8]; }
"""

# NASA SRTM Provider Runbook

## Data Sources
- OpenTopography Global DEM API (SRTMGL1 GeoTIFF requests).
- Pre-downloaded HGT tiles for full disconnected operations.

## HGT Tile Format
- Grid size: `3601 x 3601` (1 arc-second).
- Value type: signed 16-bit big-endian integer.
- Void/no-data marker: `-32768`.
- Tile naming: `N24E046.hgt`, `S34W071.hgt`, etc.

## Saudi Coverage Planning
- Latitude range: `N15` to `N32`
- Longitude range: `E034` to `E056`
- Approximate size: ~50 tiles (~1.2 GB)

## Offline Strategy
1. Download required tiles while connected.
2. Verify tile names against AOI grid.
3. Transfer to Jetson cache at `data/integrations/gis-srtm/hgt/`.
4. Run smoke profile/LOS checks before field deployment.

## Tactical Analytics
- Point elevation lookup for route constraints.
- Elevation profile for convoy planning.
- Slope/aspect for maneuver feasibility.
- Viewshed for observation and comms placement.
- Line-of-sight for engagement and sensor geometry checks.

## S3M Integration
- Phase 8 PathPlanner and TrajectoryOptimizer terrain awareness.
- Phase 16 DIS coordinate consumers gain improved altitude realism.
- Kill-chain assessment can include LOS obstruction metrics.

## Air-Gapped Behavior
- Adapter uses only cached HGT tiles or deterministic fallback profile.
- No network egress in disconnected mode.

## Smoke Test
```bash
python3 -m pytest packages/providers/gis-srtm/tests -v
```

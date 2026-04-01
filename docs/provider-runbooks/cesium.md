# Cesium ion Provider Runbook

## Registration and Credential
1. Register at `https://cesium.com/ion/`.
2. Generate an ion token with assets read scope.
3. Set `S3M_CESIUM_ION_TOKEN` on connected staging systems.

## Core Assets and APIs
- World Terrain asset ID: `1`
- OSM Buildings asset ID: `3`
- Terrain tile endpoint: `https://assets.ion.cesium.com/1/{z}/{x}/{y}.terrain?v=1.2.0`
- Asset list endpoint: `https://api.cesium.com/v1/assets`

## 3D Tiles Notes
- Root descriptor is `tileset.json`.
- Bounding volumes may be `box`, `sphere`, or `region`.
- Adapter normalizer handles all three for map-layer bounds.

## World Terrain vs SRTM
- Cesium terrain can be finer than 30 m in select areas.
- SRTM remains the deterministic fallback for full offline continuity.

## Offline Caching Strategy
1. Pre-fetch terrain tiles by AOI and zoom.
2. Cache required 3D tileset roots and descendants.
3. Transfer `terrain/` and `3dtiles/` directories to Jetson.
4. Serve from local file server or direct file paths.

## S3M Integration
- Phase 6 optional 3D tactical scene augmentation.
- Phase 8 can consume higher-detail terrain where cached.
- Phase 16 3D entity placement can align with terrain mesh context.

## Air-Gapped Behavior
- Adapter reads cached terrain tiles and cached/fixture tilesets only.
- Falls back to SRTM elevation when Cesium online services are absent.

## Smoke Test
```bash
python3 -m pytest packages/providers/gis-cesium/tests -v
```

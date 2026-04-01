# Maxar Provider Runbook

## Contract Procurement and Access
- Platform: Maxar SecureWatch / eAPI.
- Access requires defense procurement contract credentials.
- Environment variables:
  - `S3M_MAXAR_API_KEY`
  - `S3M_MAXAR_SECRET_KEY`

## SecureWatch vs eAPI
- SecureWatch focuses on mission imagery access and WMTS consumption.
- eAPI supports automated catalog search, tasking, and data workflows.

## Satellite Specs Used in S3M
- WorldView-3: 0.31m PAN, multispectral + SWIR, rapid revisit.
- WorldView-2: 0.46m PAN, 8-band multispectral.
- GeoEye-1: 0.41m PAN.
- WorldView-1: 0.50m PAN.

## STAC Catalog and WMTS Streaming
- STAC archive search is used for scene discovery and filtering.
- WMTS tile fetch is used for COP overlays and BDA panels.

## Tasking Workflow
1. Submit request with AOI and time window.
2. Await schedule confirmation.
3. Collection executes on selected sensor.
4. Delivery ingested and cached for offline mission reuse.

## 3D Terrain
- Maxar 3D terrain tiles are normalized as map layers.
- Use in elevation-aware route and line-of-sight overlays.

## Saudi Coverage and S3M Integration
- Saudi AOIs include Persian Gulf and other tactical zones.
- Phase 15: highest-resolution imagery ingestion.
- Feature 2 kill chain: BDA imagery confirmation.
- Phase 19: baseline support for change detection.

## Air-Gapped Operations
- Cache imagery tiles and terrain tiles on connected enclave.
- Transfer approved cache bundle into offline deployment.
- Adapter serves fixtures/cache in `airgapped` mode.

## Smoke Test
```bash
python3 -m pytest packages/providers/geoint-maxar/tests/ -v
```

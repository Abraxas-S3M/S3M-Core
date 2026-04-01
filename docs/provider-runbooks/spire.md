# Spire Maritime Provider Runbook

## Registration and Credentials
1. Enroll in Spire Maritime data services.
2. Configure `S3M_SPIRE_API_TOKEN` as bearer token.

## Authentication
- Header: `Authorization: Bearer <token>`.

## Satellite vs Terrestrial AIS
- `collection_type=terrestrial`: coastal/ground receiver-based observations.
- `collection_type=satellite`: Spire nanosatellite observation.
- Mixed history indicates both channels in recent track.

## Radius-Based Zone Queries
- S3M uses center/radius queries aligned to Saudi operational zones:
  - persian_gulf
  - red_sea_south
  - strait_of_hormuz
  - bab_el_mandeb
  - gulf_of_aden
  - red_sea_full

## Dark Vessel Inference Logic
- Satellite-only observations with no recent terrestrial confirmation are flagged as potential dark behavior.
- This helps close open-ocean visibility gaps beyond coastal receiver range.

## S3M Integration Value
- Phase 15 open-ocean coverage gap filler.
- Improves dark-vessel confirmation in maritime fusion by cross-referencing terrestrial feeds and AIS gap events.

## Air-Gapped Notes
- Transfer periodic bulk exports from connected staging systems.
- Run in AIRGAPPED mode for disconnected deployments.

## Smoke Test
```bash
python3 -m pytest packages/providers/maritime-spire/tests/ -v
```

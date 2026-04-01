# VesselFinder Provider Runbook

## Registration and Credentials
1. Register for VesselFinder API access.
2. Configure `S3M_VESSELFINDER_API_KEY`.

## Authentication
- API key is sent via `userkey` query parameter.

## Endpoints Used
- `/vessels?userkey=...&mmsi=...` (single vessel)
- `/vessels?userkey=...&latmin=...&latmax=...&lonmin=...&lonmax=...` (zone vessels)
- `/vessels?userkey=...&mmsi=...&interval=0` (particulars)
- `/expectedArrivals?userkey=...&portname=...` (Saudi port arrivals)

## Tactical Mapping Notes
- VesselFinder speed is already in knots (no `/10` conversion).
- AIS ITU ranges are mapped to mission classes:
  - `60-69 Passenger`
  - `70-79 Cargo`
  - `80-89 Tanker`
- Dimensions are derived from A/B/C/D (`length=A+B`, `beam=C+D`).

## Saudi Monitoring Coverage
- Same six maritime zones as MarineTraffic for cross-source validation.
- Port monitoring list includes JUBAIL, JEDDAH, DAMMAM, RAS TANURA, YANBU, KING ABDULLAH PORT.

## S3M Integration
- Provides secondary terrestrial AIS feed for data cross-check and gap fill.
- Maritime fusion pipeline merges by MMSI and prefers freshest kinematics.

## Air-Gapped Notes
- Keep rolling vessel and arrival snapshots from approved connected systems.
- Air-gapped execution consumes local JSON exports only.

## Smoke Test
```bash
python3 -m pytest packages/providers/maritime-vesselfinder/tests/ -v
```

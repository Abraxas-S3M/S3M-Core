# HLA Provider Runbook (Simulation-Only)

## Scope and Safety
- Provider: `sim-hla`
- Standard: IEEE-1516 HLA with RPR-FOM 2.0 alignment
- **Critical**: this adapter is **simulation only** and does not issue live C2 commands.
- Tactical context: used for coalition rehearsal federations where S3M is one federate among partner simulators.

## Core Concepts
- **Federation**: shared synthetic battlespace across multiple simulators.
- **Federate**: one participant (S3M is a federate).
- **RTI**: runtime middleware (CERTI open-source, Pitch/MAK commercial).
- **FOM**: object/interaction schema contract exchanged across federation.
- **Time Management**: supported as time-stepped (`0.1s` default).

## S3M Integration Design
- Phase 7 simulation state -> HLA object publication (`sync_from_phase7`).
- Phase 16 DIS entities -> HLA bridge (`sync_from_phase16_dis`).
- Coordinate conversion reuses Phase 16 DIS WGS-84 ECEF converter for consistency.

## RTI Modes
- `certi` (default target if available)
- `pitch`, `mak` (interface placeholder modes)
- `stub` (fully offline deterministic test mode)

If RTI is unavailable, adapter safely falls back to stub mode and remains functional.

## FOM Notes
- FOM generator writes `configs/interop/s3m_fom.xml`.
- Includes object classes:
  - Aircraft, GroundVehicle, SurfaceVessel, Munition, Sensor
- Includes interactions:
  - WeaponFire, Detonation, RadioTransmit

## Environment Variables
- `S3M_HLA_RTI_HOST=localhost`
- `S3M_HLA_RTI_PORT=11000`
- Optional: `S3M_HLA_RTI_TYPE=certi|pitch|mak|stub`

## Smoke Test
```bash
python3 -m pytest packages/providers/sim-hla/tests/test_hla_adapter.py -v
```

## Troubleshooting
- If federation creation succeeds but no traffic is visible, verify shared FOM path and class publication/subscription lists.
- For air-gapped validation, set mode to `airgapped` and confirm `mode=stub` in `get_federation_status()`.

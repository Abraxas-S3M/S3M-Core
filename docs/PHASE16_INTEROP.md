# S3M Phase 16 — Expanded Interoperability (Layer 10)

## Overview

Phase 16 extends the Phase 10 interoperability API surface (`src/security/interop/`) with a deep implementation stack under `services/interop/`.

- **Phase 10 remains authoritative API surface**: `DISAdapter`, `C2SIMAdapter`, `BMLAdapter`, `InteropManager`
- **Phase 16 provides depth**: full DIS/C2SIM/MSDL/ORBAT engines, verification, exercise orchestration, coalition dashboarding, and edge mesh adapter
- **Air-gapped design**: offline-safe operation on Jetson AGX Orin with stdlib-first protocol handling

## Architecture

```
Phase 7 Simulation / Phase 6 Mission / Phase 14 Comms
            |
            v
src/security/interop (Phase 10 API adapters)
            |
            v
services/interop (Phase 16 deep implementation)
  ├─ DIS engine (PDU factory, coordinates, dead reckoning, UDP manager)
  ├─ C2SIM engine (XML message factory + server/offline adapter)
  ├─ MSDL parser/generator
  ├─ ORBAT force manager
  ├─ Exercise lifecycle manager
  ├─ Coalition dashboard provider
  ├─ Interop verifier (DIS/C2SIM/MSDL/coordinates)
  ├─ Tactical mesh edge adapter
  └─ Capability/partner registry
```

## DIS Protocol Support

Implemented in `services/interop/dis/`:

- **PDU support**: Entity State, Fire, Detonation, Start/Resume, Stop/Freeze, Signal, Comment, plus type identification/auto decode
- **Entity State format**: fixed 144-byte payload target for baseline interoperability test
- **Coordinate transforms**: WGS-84 LLA↔ECEF, ENU local↔ECEF, orientation conversion helpers
- **Dead reckoning algorithms**:
  - Algorithm 1: static
  - Algorithm 2: FPW
  - Algorithm 3: RPW (orientation rates)
  - Algorithm 5: FVW (acceleration)
- **Network manager**: UDP broadcast send/receive, entity cache, stale extrapolation, protocol health stats

## C2SIM Protocol Support

Implemented in `services/interop/c2sim/`:

- `C2SIMMessageFactory`:
  - Order XML generation/parsing
  - Report XML generation/parsing
  - Initialization XML generation/parsing
  - Plan XML generation
  - Auto message type parsing and structural validation
- `C2SIMServerAdapter`:
  - REST push/pull when connected
  - Offline inbox/outbox fallback under `data/interop/c2sim_{inbox,outbox}/`
- `C2SIMEngine`:
  - High-level send/receive and conversion helpers
  - Delegation to Phase 10 adapter for mission/AAR conversions

## MSDL and ORBAT

Implemented in `services/interop/msdl/`:

- `MSDLParser`:
  - Parses military scenario root, forces, unit hierarchy, environment, and overlay
  - Maps unit type strings to S3M categories
- `MSDLGenerator`:
  - Generates complete `MilitaryScenario` XML
  - Converts S3M scenario-like dicts and ORBAT force structures to MSDL
- `ORBATManager`:
  - Force and unit creation
  - Parent/subordinate linkage and hierarchy generation
  - Saudi prebuilt template (country code 178, APP-6 style symbols)
  - Export/import via MSDL

## Exercise Lifecycle

Implemented in `services/interop/exercise_manager.py`:

1. Create exercise session
2. Start exercise (DIS + C2SIM + Start/Resume PDU)
3. Inject scenario (C2SIM Initialization + DIS entity publication)
4. Pause/resume (Stop/Freeze + Start/Resume)
5. End exercise (Stop/Freeze + disconnect + summary)

The manager tracks session metadata, event timeline, and published entity/event counts.

## Coalition Dashboard

Implemented in `services/interop/coalition_dashboard.py`:

- Exercise overview with nation/entity/event/C2/DIS summaries
- ORBAT hierarchical view
- Coalition COP merge of DIS and C2SIM updates
- Interop metrics (PDU rates, message counters, error indicators)
- Exercise timeline feed

## Verification Framework

Implemented in `services/interop/verification.py`:

- DIS conformance:
  - Entity State encode/decode round-trip
  - Coordinate conversion and dead reckoning checks
  - Header/PDU type checks
- C2SIM conformance:
  - Order/report/initialization round-trips
  - Namespace correctness
- MSDL conformance:
  - Generate/parse round-trip
- Coordinate accuracy checks:
  - Riyadh and Mecca LLA↔ECEF↔LLA under 1m tolerance

## Registry and Partner Codes

Implemented in `services/interop/registry.py`:

- Capability registration for protocol/version/features
- GCC partner DIS country codes:
  - Saudi Arabia: 178
  - UAE: 223
  - Kuwait: 117
  - Bahrain: 16
  - Qatar: 164
  - Oman: 154
- NATO partner code table

## API Endpoints (26)

Implemented in `src/api/interop_ext_routes.py` and included in `src/api/server.py`.

### Exercises
- `POST /interop/exercises`
- `GET /interop/exercises`
- `POST /interop/exercises/{id}/start`
- `POST /interop/exercises/{id}/pause`
- `POST /interop/exercises/{id}/resume`
- `POST /interop/exercises/{id}/end`
- `POST /interop/exercises/{id}/inject`
- `GET /interop/exercises/{id}/entities`
- `GET /interop/exercises/{id}/overview`

### DIS
- `POST /interop/dis/publish`
- `GET /interop/dis/entities`
- `GET /interop/dis/stats`

### C2SIM
- `POST /interop/c2sim/order`
- `POST /interop/c2sim/report`
- `GET /interop/c2sim/messages`

### ORBAT
- `POST /interop/orbat/forces`
- `POST /interop/orbat/forces/{id}/units`
- `GET /interop/orbat/forces`
- `GET /interop/orbat/forces/{id}/hierarchy`
- `POST /interop/orbat/template/saudi`

### MSDL
- `POST /interop/msdl/import`
- `POST /interop/msdl/export`

### Verification & Coalition
- `POST /interop/verify`
- `GET /interop/coalition/cop`
- `GET /interop/metrics`
- `GET /interop/status`
- `GET /interop/partners`

## Configuration

`configs/interop-extended.yaml` provides defaults for:

- DIS networking and dead reckoning thresholds
- C2SIM server/offline directories
- MSDL and ORBAT defaults
- Exercise lifecycle controls
- GCC partner metadata and callsigns
- Verification thresholds

## Scripts

- `scripts/demo_dis_protocol.py`: DIS PDU, coordinate, and dead reckoning walkthrough
- `scripts/run_interop_demo.py`: full exercise lifecycle demonstration from ORBAT template through verification

## Integration Notes

- Phase 10 adapters are untouched and continue functioning.
- Phase 16 services are additive and can be delegated to by Phase 10 surface adapters.
- No external protocol libraries are bundled; implementation uses Python stdlib and lightweight project dependencies.

## Forward Look (Phase 17)

Phase 17 can extend this base with procurement-maintenance digital thread integration:

- maintenance ORBAT readiness overlays
- spare part/logistics synchronization into C2SIM reports
- lifecycle telemetry verification against coalition readiness standards

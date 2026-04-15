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

## New Adapter Integration (Phase 16.1)

### CoT / TAK Gateway (`services/interop/cot/`)
- **Purpose**: Exchange coalition track updates with TAK-compatible clients and gateways.
- **API endpoints**:
  - `POST /interop/cot/connect`
  - `POST /interop/cot/disconnect`
  - `POST /interop/cot/publish`
  - `GET /interop/cot/tracks`
  - `GET /interop/cot/stats`
  - `GET /interop/cot/status`
- **Config keys**: `cot.multicast_address`, `cot.multicast_port`, `cot.tak_server_url`, `cot.stale_seconds`.
- **Usage**: Enable CoT in `InteropManager`, then send coalition tracks via `send_cot_tracks()`.

### NFFI Blue Force Tracking (`services/interop/nffi/`)
- **Purpose**: Share friendly-force track positions with coalition BFT consumers (STANAG 5527 profile).
- **API endpoints**:
  - `POST /interop/nffi/connect`
  - `POST /interop/nffi/disconnect`
  - `POST /interop/nffi/publish`
  - `GET /interop/nffi/tracks`
  - `GET /interop/nffi/status`
- **Config keys**: `nffi.transport_profile`, `nffi.gateway_url`, `nffi.track_source_country`, `nffi.system_id`.
- **Usage**: Enable NFFI and publish validated blue-force tracks via `send_nffi_tracks()`.

### APP-6D / 2525D Symbology (`services/interop/symbology/`)
- **Purpose**: Normalize all coalition tracks to valid SIDC values for COP rendering and protocol mapping.
- **Integration points**:
  - `SymbologyMapper.map_track_symbology()`
  - `SIDCGenerator.from_dis_entity_type()`
- **Usage**: COP adapter applies `SymbologyMapper` before returning `GUIThreatTrack` objects.

### APP-11 Message Text Format (`services/interop/mtf/`)
- **Purpose**: Generate and parse APP-11 XML-MTF operational/intelligence reports (e.g., INTSUM).
- **API endpoints**:
  - `POST /interop/mtf/send`
  - `GET /interop/mtf/outbox`
  - `GET /interop/mtf/status`
- **Config keys**: `mtf.namespace`, `mtf.originator`, `mtf.start_serial`, `mtf.gateway_url`.
- **Usage**: Use `InteropManager.send_mtf_message()` for unified message generation + delivery queueing.

### STIX / TAXII Transport (`services/interop/stix/`)
- **Purpose**: Exchange cyber threat intelligence bundles with coalition TAXII 2.1 sources.
- **API endpoints**:
  - `POST /interop/taxii/connect`
  - `POST /interop/taxii/poll`
  - `POST /interop/taxii/contribute`
  - `GET /interop/taxii/status`
  - `GET /interop/taxii/collections`
- **Config keys**: `taxii.servers`, `taxii.poll_interval_seconds`, `taxii.outbox_dir`, `taxii.inbox_dir`.
- **Usage**: Enable TAXII transport in `InteropManager`, then submit STIX bundles via `send_taxii_bundle()`.

### JREAP-C Link 16 Bridge (`services/interop/jreap/`)
- **Purpose**: Ingest J-series tactical tracks and bridge them to S3M COP / interop gateways.
- **API endpoints**:
  - `POST /interop/jreap/start`
  - `POST /interop/jreap/stop`
  - `GET /interop/jreap/tracks`
  - `GET /interop/jreap/stats`
  - `GET /interop/jreap/status`
- **Config keys**: `jreap.listen_port`, `jreap.supported_j_series`, `jreap.crossfeed_to_cot`, `jreap.crossfeed_to_dis`.
- **Usage**: Enable JREAP and pull decoded tracks through `receive_all()` or `send_jreap_tracks()`.

### OTH-Gold Maritime (`services/interop/oth/`)
- **Purpose**: Exchange maritime tracks over OTH-Gold transport for coalition naval COP alignment.
- **API endpoints**:
  - `POST /interop/oth/connect`
  - `POST /interop/oth/publish`
  - `GET /interop/oth/tracks`
  - `GET /interop/oth/status`
- **Config keys**: `oth_gold.gateway_url`, `oth_gold.publish_interval_seconds`, `oth_gold.enforce_maritime_only`.
- **Usage**: Enable OTH-Gold and publish maritime-only tracks via `send_oth_gold_tracks()`.

## CENTCOM / KSA / NATO Compliance Matrix

| Adapter | CENTCOM Ops Alignment | KSA/GCC Interop Requirement | NATO/Coalition Standard |
|---|---|---|---|
| CoT/TAK | Forward observer and COP relay over constrained links | TAK-compatible C2 picture sharing | CoT 2.0 profile |
| NFFI | Blue-force deconfliction and coalition maneuver safety | GCC partner country code + ISO3 mapping | STANAG 5527 (NFFI 1.4) |
| Symbology | Common tactical iconography under mixed feeds | KSA force structures mapped to valid SIDC | APP-6D / MIL-STD-2525D |
| MTF | Structured operational intelligence reporting | KSA command reporting workflows | APP-11(D) XML-MTF |
| STIX/TAXII | CTI fusion for cyber defense in theater | Offline queueing for sovereign deployments | STIX 2.1 / TAXII 2.1 |
| JREAP-C | Link 16 situational awareness ingestion | Coalition air/surface data ingest | JREAP-C + J-series |
| OTH-Gold | Maritime over-the-horizon track coordination | Gulf maritime COP interoperability | OTH-Gold 3.0 |

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

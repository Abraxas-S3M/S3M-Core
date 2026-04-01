# ArduPilot SITL Provider Runbook

## Purpose
`sim-ardupilot-sitl` provides a **simulation-only** adapter for ArduPilot Software-In-The-Loop (SITL) validation.
It is used to test autonomy and navigation logic without commanding real aircraft.

## Critical Safety Statement
- **SIMULATION ONLY**: this adapter targets `sim_vehicle.py` and local SITL endpoints.
- It does **not** provide live command-and-control over physical UAVs.

## Installation and Runtime Notes
1. Optional dependency: `pymavlink`.
2. Optional SITL runtime:
   ```bash
   sim_vehicle.py -v ArduCopter --map --console -I0
   ```
3. Default endpoints:
   - UDP: `udp:127.0.0.1:14550`
   - TCP: `tcp:127.0.0.1:5760`
4. In air-gapped or no-SITL conditions, adapter runs deterministic stub telemetry.

## Supported Vehicle Types
- `copter` (ArduCopter)
- `plane` (ArduPlane)
- `rover` (ArduRover)
- `sub` (ArduSub)

## Flight Modes
- `STABILIZE`, `ALT_HOLD`, `LOITER`, `RTL`, `AUTO`, `GUIDED`, `LAND`, `BRAKE`

## Telemetry Fields
- `lat`, `lon`, `alt`
- `heading`, `groundspeed`, `airspeed`
- `roll`, `pitch`, `yaw`
- `battery_pct`
- `gps_fix`, `satellites`
- `mode`, `armed`

## Simulation Failure Injection
- `simulate_gps_denial()`:
  - sets GPS fix to denied profile for Phase 8 fallback testing.
- `simulate_comms_loss()`:
  - simulates heartbeat interruption for HOOL lost-link procedure validation.

## S3M Integration Bridges
- `feed_to_autonomy()`:
  - SITL telemetry -> Phase 6 behavior tree/autonomy sensor contract.
- `feed_to_hool()`:
  - SITL telemetry -> Feature 1 HOOL mission-state style contract for envelope logic tests.

## Smoke Test
```bash
python3 -m pytest packages/providers/sim-ardupilot-sitl/tests -v
```

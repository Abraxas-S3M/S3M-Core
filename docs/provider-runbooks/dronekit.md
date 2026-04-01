# DroneKit Provider Runbook (Simulation Only)

## Purpose
`sim-dronekit` provides a Python mission scripting interface for SITL-based validation.
It is used to script deterministic rehearsal scenarios for:
- Phase 6 autonomy behavior checks
- Phase 8 navigation fallback testing
- Feature 1 HOOL envelope/lost-link safety testing

**Safety constraint:** This adapter is **SIMULATION ONLY** and does not control real aircraft.

## Installation Notes
- Optional dependency: `dronekit`
- Default connection:
  - `udp:127.0.0.1:14550`
- Environment variable:
  - `S3M_DRONEKIT_CONNECTION=udp:127.0.0.1:14550`

If DroneKit is not installed, adapter operates in stub mode for offline testing.

## Core API
- `connect(connection_string=None)`
- `get_vehicle_state()`
- `takeoff(altitude_m=10)`
- `goto(lat, lon, alt, groundspeed=5)`
- `upload_and_execute_mission(waypoints)`
- `execute_test_scenario(scenario)`
- `rtl()`, `land()`, `set_mode(mode)`

## Test Scenario Library
The following scenarios are available:
1. `square_patrol`
2. `waypoint_mission`
3. `gps_denial_test`
4. `envelope_violation_test`
5. `battery_low_test`
6. `comms_loss_test`

These scenarios produce deterministic event logs for integration tests.

## S3M Integration
- Scenario telemetry and events are consumed by simulation interop pipeline.
- HOOL-related safety scenarios validate autonomous envelope controls in rehearsal.
- Navigation fallback scenarios validate GPS-denied logic in controlled simulation.

## Air-Gapped / Offline Operation
- Stub mode is always available.
- All tests use fixtures and do not require external software.

## Smoke Test
```bash
python3 -m pytest packages/providers/sim-dronekit/tests/test_dronekit_adapter.py -v
```

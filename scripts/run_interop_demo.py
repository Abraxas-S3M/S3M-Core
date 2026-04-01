#!/usr/bin/env python3
"""Full Phase 16 interoperability demo workflow."""

from __future__ import annotations

from pprint import pprint

from services.interop import CoalitionDashboardProvider, ExerciseManager, InteropVerifier


def main() -> None:
    manager = ExerciseManager()
    dashboard = CoalitionDashboardProvider(manager)
    verifier = InteropVerifier()

    force = manager.orbat_manager.create_saudi_template()
    scenario = manager.orbat_manager.export_to_scenario()

    session = manager.create_exercise(
        name="GCC Joint Shield 2026",
        description="Coalition interoperability rehearsal for joint DIS/C2SIM operation.",
        nations=[
            {"country_code": 178, "name": "Saudi Arabia", "callsign": "FALCON"},
            {"country_code": 223, "name": "United Arab Emirates", "callsign": "HAWK"},
            {"country_code": 117, "name": "Kuwait", "callsign": "DESERT"},
        ],
    )
    print(f"Created exercise: {session.exercise_id} - {session.exercise_name}")

    manager.start_exercise(session.exercise_id)
    manager.inject_scenario(session.exercise_id, scenario)

    demo_entities = [
        # Saudi vehicles
        {"entity_id": "sa-veh-1", "name": "Saudi MBT-1", "nation": 178, "lat": 24.71, "lon": 46.67},
        {"entity_id": "sa-veh-2", "name": "Saudi MBT-2", "nation": 178, "lat": 24.72, "lon": 46.69},
        {"entity_id": "sa-veh-3", "name": "Saudi IFV-1", "nation": 178, "lat": 24.70, "lon": 46.68},
        {"entity_id": "sa-veh-4", "name": "Saudi IFV-2", "nation": 178, "lat": 24.73, "lon": 46.66},
        # UAE drones
        {"entity_id": "uae-uav-1", "name": "UAE UAV-1", "nation": 223, "lat": 24.75, "lon": 46.65},
        {"entity_id": "uae-uav-2", "name": "UAE UAV-2", "nation": 223, "lat": 24.74, "lon": 46.64},
        {"entity_id": "uae-uav-3", "name": "UAE UAV-3", "nation": 223, "lat": 24.76, "lon": 46.63},
        # Kuwait patrol boats (demo positions still represented as lat/lon)
        {"entity_id": "kwt-boat-1", "name": "Kuwait Patrol 1", "nation": 117, "lat": 24.69, "lon": 46.61},
        {"entity_id": "kwt-boat-2", "name": "Kuwait Patrol 2", "nation": 117, "lat": 24.68, "lon": 46.62},
        {"entity_id": "kwt-boat-3", "name": "Kuwait Patrol 3", "nation": 117, "lat": 24.67, "lon": 46.60},
    ]
    for ent in demo_entities:
        manager.publish_entity(
            session.exercise_id,
            {
                "entity_id": ent["entity_id"],
                "name": ent["name"],
                "affiliation": "friendly",
                "entity_type": {
                    "kind": 1,
                    "domain": 1,
                    "country": ent["nation"],
                    "category": 1,
                    "subcategory": 0,
                    "specific": 0,
                    "extra": 0,
                },
                "position": {"lat": ent["lat"], "lon": ent["lon"], "alt": 0.0},
                "velocity": {"x": 2.0, "y": 0.0, "z": 0.0},
                "marking": ent["name"],
            },
        )

    manager.c2sim_engine.send_order(
        {
            "order_id": "order-gcc-001",
            "issuer": "Coalition-HQ",
            "task_type": "Advance",
            "assigned_units": [force.units[1].unit_id if len(force.units) > 1 else force.units[0].unit_id],
            "waypoints": [(24.7500, 46.7000, 0.0)],
            "roe": "self-defense",
        }
    )
    manager.c2sim_engine.send_report(
        {
            "report_id": "report-uav-001",
            "reporter": "UAV-Squadron-1",
            "report_type": "PositionReport",
            "content": {"lat": 24.75, "lon": 46.64, "status": "on-station"},
        }
    )

    print("\nExercise Overview")
    pprint(dashboard.get_exercise_overview(str(session.exercise_id)))

    print("\nCoalition COP")
    pprint(dashboard.get_coalition_cop())

    print("\nInterop Verification")
    verify_results = verifier.run_full_verification()
    pprint(verify_results["summary"])

    print("\nMSDL Export")
    print(manager.orbat_manager.to_msdl()[:500], "...")

    summary = manager.end_exercise(session.exercise_id)
    print("\nExercise End Summary")
    pprint(summary)


if __name__ == "__main__":
    main()


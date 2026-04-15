#!/usr/bin/env python3
"""Coalition interoperability walkthrough for the fully wired adapter stack."""

from __future__ import annotations

from pprint import pprint

from services.interop import ExerciseManager, InteropVerifier
from src.security.interop import InteropManager


def _demo_tracks() -> list[dict]:
    return [
        {
            "unit_id": "sau-armor-1",
            "entity_type": "FRIENDLY_UGV",
            "affiliation": "friendly",
            "domain": "ground",
            "position": [24.7136, 46.6753, 620.0],
            "heading": 45.0,
            "speed": 11.5,
            "callsign": "FALCON-11",
            "status": "active",
        },
        {
            "unit_id": "sau-uav-2",
            "entity_type": "FRIENDLY_UAV",
            "affiliation": "friendly",
            "domain": "air",
            "position": [24.7210, 46.6820, 1200.0],
            "heading": 90.0,
            "speed": 42.0,
            "callsign": "FALCON-EYE",
            "status": "active",
        },
    ]


def _to_dis_entity(track: dict) -> dict:
    lat, lon, alt = track["position"]
    return {
        "entity_id": track["unit_id"],
        "name": track.get("callsign", track["unit_id"]),
        "affiliation": track.get("affiliation", "friendly"),
        "entity_type": {
            "kind": 1,
            "domain": 2 if track.get("domain") == "air" else 1,
            "country": 178,
            "category": 1,
            "subcategory": 0,
            "specific": 0,
            "extra": 0,
        },
        "position": {"lat": lat, "lon": lon, "alt": alt},
        "velocity": {"x": float(track.get("speed", 0.0)), "y": 0.0, "z": 0.0},
        "marking": track.get("callsign", track["unit_id"]),
    }


def main() -> None:
    exercise_manager = ExerciseManager()
    interop_manager = InteropManager()
    verifier = InteropVerifier()

    saudi_force = exercise_manager.orbat_manager.create_saudi_template()
    scenario = exercise_manager.orbat_manager.export_to_scenario()
    session = exercise_manager.create_exercise(
        name="Coalition Interop Demo",
        description="Saudi-led coalition interoperability exercise for DIS/CoT/NFFI/MTF validation.",
        nations=[
            {"country_code": 178, "name": "Saudi Arabia", "callsign": "FALCON"},
            {"country_code": 223, "name": "United Arab Emirates", "callsign": "HAWK"},
            {"country_code": 225, "name": "United States", "callsign": "EAGLE"},
        ],
    )
    exercise_manager.start_exercise(session.exercise_id)
    exercise_manager.inject_scenario(session.exercise_id, scenario)

    interop_manager.enable_protocol("dis", {"port": 31001, "broadcast_address": "255.255.255.255"})
    interop_manager.enable_protocol("cot", {"transport": "offline"})
    interop_manager.enable_protocol(
        "nffi",
        {"transport_profile": "IP-1", "gateway_url": None, "track_source_country": "SAU", "system_id": "S3M-FALCON"},
    )
    interop_manager.enable_protocol("mtf", {"gateway_url": None, "originator": "S3M INTEL CENTER"})

    published_dis = 0
    tracks = _demo_tracks()
    for track in tracks:
        dis_entity = _to_dis_entity(track)
        exercise_manager.publish_entity(session.exercise_id, dis_entity)
        send_result = interop_manager.send_entity_update(dis_entity)
        published_dis += int(send_result.get("dis", False))

    cot_published = interop_manager.send_cot_tracks(tracks)
    nffi_published = interop_manager.send_nffi_tracks(tracks)
    intsum = interop_manager.send_mtf_message(
        report_type="INTSUM",
        content={
            "summary_text": "Saudi-led coalition tracks are synchronized across DIS, CoT, and NFFI.",
            "assessment_text": "Interoperability posture is stable for joint force rehearsal.",
        },
        originator="S3M INTEL CENTER",
        classification="SECRET",
    )

    verification = verifier.run_full_verification()
    status_report = {
        "exercise_id": session.exercise_id,
        "saudi_orbat_units": len(saudi_force.units),
        "published_dis_entities": published_dis,
        "published_cot_tracks": cot_published,
        "published_nffi_tracks": nffi_published,
        "intsum_delivery": intsum,
        "verification_summary": verification.get("summary", {}),
        "protocol_status": interop_manager.get_protocol_status(),
    }

    print("Coalition Interoperability Status Report")
    pprint(status_report)

    exercise_manager.end_exercise(session.exercise_id)


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""DIS protocol demonstration for S3M Phase 16 interoperability."""

from __future__ import annotations

from services.interop.dis import DISCoordinateConverter, DISDeadReckoning, DISPDUFactory
from services.interop.models import DISEntityID, DISEntityType, DISLinearVelocity, DISOrientation, DISWorldCoordinate


def hex_dump(data: bytes, width: int = 16) -> str:
    rows = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        rows.append(f"{i:04X}: {hex_part}")
    return "\n".join(rows)


def main() -> None:
    factory = DISPDUFactory()
    coord = DISCoordinateConverter()
    dr = DISDeadReckoning()

    print("=== DIS PROTOCOL DEMO ===")

    entity_id = DISEntityID(site_id=1, application_id=1, entity_id=1515)
    entity_type = DISEntityType(kind=1, domain=2, country=178, category=1, subcategory=0, specific=0, extra=0)
    ecef = DISWorldCoordinate.from_lat_lon_alt(24.7136, 46.6753, 612.0)
    orientation = DISOrientation(psi=0.0, theta=0.0, phi=0.0)
    velocity = DISLinearVelocity(x=230.0, y=0.0, z=0.0)
    entity_pdu = factory.encode_entity_state(
        entity_id=entity_id,
        entity_type=entity_type,
        position=ecef,
        orientation=orientation,
        velocity=velocity,
        force_id=1,
        exercise_id=1,
        marking="SAUDI-F15",
    )
    print(f"Entity State PDU length: {len(entity_pdu)} bytes")
    print(hex_dump(entity_pdu[:96]))

    decoded = factory.decode_entity_state(entity_pdu)
    print("Entity round-trip:")
    print(f"  entity_id={decoded['entity_id'].to_tuple()} marking={decoded['marking']}")
    print(f"  force_id={decoded['force_id']} type_country={decoded['entity_type'].country}")

    x, y, z = coord.lla_to_ecef(24.7136, 46.6753, 612.0)
    lat, lon, alt = coord.ecef_to_lla(x, y, z)
    print("Coordinate conversion:")
    print(f"  LLA->ECEF: ({x:.3f}, {y:.3f}, {z:.3f})")
    print(f"  ECEF->LLA: ({lat:.6f}, {lon:.6f}, {alt:.3f})")

    dr_state = {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "velocity": {"x": 70.0, "y": 0.0, "z": 0.0},
        "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0},
    }
    projected = dr.extrapolate(dr_state, dt_seconds=5.0, algorithm=2)
    print("Dead reckoning (5s FPW):")
    print(f"  projected_x={projected['position']['x']:.2f}m")

    fire_pdu = factory.encode_fire(
        firing_entity=entity_id,
        target_entity=DISEntityID(1, 1, 700),
        munition_type=entity_type,
        location=ecef,
        exercise_id=1,
    )
    detonation_pdu = factory.encode_detonation(
        firing_entity=entity_id,
        target_entity=DISEntityID(1, 1, 700),
        location=ecef,
        munition_type=entity_type,
        result=1,
        exercise_id=1,
    )
    signal_pdu = factory.encode_signal(entity_id=entity_id, radio_id=7, encoding=1, data=b"S3M VOICE", exercise_id=1)

    print("PDU type breakdown:")
    print(f"  Entity State: {int(factory.identify_pdu_type(entity_pdu))}")
    print(f"  Fire: {int(factory.identify_pdu_type(fire_pdu))}")
    print(f"  Detonation: {int(factory.identify_pdu_type(detonation_pdu))}")
    print(f"  Signal: {int(factory.identify_pdu_type(signal_pdu))}")


if __name__ == "__main__":
    main()

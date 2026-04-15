#!/usr/bin/env python3
"""Offline CWIX readiness demonstration across NATO interoperability adapters.

Military/tactical context:
This script simulates a coalition interoperability dry-run so operators can
confirm that HLA/MIP/NVG/NSILI/UAS/FM V/FM N/OGC/Link22 pathways are wired
before live federation or partner-network execution.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.security.interop import InteropManager


def _print_step(title: str, payload: dict) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=True, default=str))


def main() -> int:
    manager = InteropManager()
    artifact_root = Path("data/interop/cwix_demo")
    artifact_root.mkdir(parents=True, exist_ok=True)

    readiness = {}

    readiness["cot"] = manager.enable_protocol("cot", {"transport": "offline"})
    readiness["mtf"] = manager.enable_protocol("mtf", {"gateway_url": None})
    readiness["fmn_security"] = manager.enable_protocol(
        "fmn_security",
        {"enforce_labels": True, "classification_default": "NATO UNCLASSIFIED", "releasable_to_default": ["SAU", "USA"]},
    )
    readiness["hla"] = manager.enable_protocol("hla", {"rti_type": "stub", "federation_name": "S3M_CWIX_READINESS"})
    readiness["mip"] = manager.enable_protocol(
        "mip",
        {
            "outbox_dir": str(artifact_root / "mip_outbox"),
            "inbox_dir": str(artifact_root / "mip_inbox"),
        },
    )
    readiness["nvg"] = manager.enable_protocol("nvg", {"outbox_dir": str(artifact_root / "nvg_outbox")})
    readiness["nsili"] = manager.enable_protocol("nsili", {"catalog_dir": str(artifact_root / "nsili_catalog")})
    readiness["uas4586"] = manager.enable_protocol("uas4586", {"max_loi": 3})
    readiness["fmv"] = manager.enable_protocol("fmv", {"register_in_nsili": True})
    readiness["ogc"] = manager.enable_protocol("ogc")
    readiness["link22"] = manager.enable_protocol("link22", {"mode": "stub"})
    _print_step("Protocol Enablement", readiness)

    dis_to_nato = manager.send_entity_update(
        {
            "entity_id": "cwix-blue-1",
            "entity_type": "FRIENDLY_UAV",
            "allegiance": "friendly",
            "location": {"lat": 24.7136, "lon": 46.6753, "alt": 620.0},
            "velocity": {"x": 12.0, "y": 0.0, "z": 0.0},
            "marking": "CWIX-EAGLE-1",
            "status": "active",
        }
    )
    _print_step("DIS->NATO Crossfeed (HLA/MIP/NVG/OGC)", dis_to_nato)

    manager.register_uas_platform("cwix-uav-1", "MALE", ["LOI1", "LOI2", "LOI3", "EO_IR"])
    uas_to_cot = manager.publish_uas_vehicle_status(
        "cwix-uav-1",
        {
            "position": {"lat": 24.7140, "lon": 46.6760, "altitude": 780.0},
            "speed": 48.0,
            "heading": 118.0,
            "fuel": 74.0,
            "mode": "ON_STATION",
        },
    )
    _print_step("UAS4586->CoT Bridge", uas_to_cot)

    fmv_to_nsili = manager.register_fmv_with_nsili(
        uav_status={"platform_heading": 88.0, "position": {"latitude": 24.7136, "longitude": 46.6753, "altitude": 905.0}},
        payload_status={"sensor_position": {"latitude": 24.7136, "longitude": 46.6753, "altitude": 910.0}, "uas_local_set_version": 13},
        timestamp=1_713_264_321.0,
        video_reference="droneops://cwix/readiness-feed-1",
    )
    _print_step("FMV->NSILI Bridge", fmv_to_nsili)

    mtf_result = manager.send_mtf_message(
        report_type="INTSUM",
        content={
            "summary_text": "CWIX readiness dry-run complete across all NATO adapters.",
            "assessment_text": "All configured interop pathways remained operational in offline mode.",
        },
        originator="S3M J2",
        classification="SECRET",
    )
    _print_step("MTF Outbound with FMN Labeling", mtf_result)

    link22_status = {
        "published": manager.publish_link22_track({"id": "cwix-link22-1", "entity_type": "FRIENDLY_SHIP"}),
        "health": manager.link22_adapter.health_check(),
    }
    _print_step("Link22 Stub Readiness", link22_status)

    summary = manager.health_check()
    _print_step("Interop Manager Health", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

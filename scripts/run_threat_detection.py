#!/usr/bin/env python3
"""Phase 5 threat detection pipeline demo for S3M tactical operators."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.threat_detection.models import ThreatCategory, ThreatLevel
from src.threat_detection.threat_manager import ThreatManager


def _write_sample_suricata(path: str) -> None:
    records = [
        {
            "timestamp": "2026-03-31T10:30:45.123456+00:00",
            "event_type": "alert",
            "src_ip": "10.10.4.22",
            "src_port": 49822,
            "dest_ip": "172.16.1.10",
            "dest_port": 443,
            "proto": "TCP",
            "alert": {
                "severity": 2,
                "signature_id": 2019236,
                "signature": "ET TROJAN Possible Malware CnC Check-in",
                "category": "A Network Trojan was detected",
            },
        }
    ]
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def _write_sample_wazuh(path: str) -> None:
    records = [
        {
            "timestamp": "2026-03-31T10:35:00+00:00",
            "agent": {"name": "edge-node-7"},
            "rule": {
                "level": 13,
                "id": "5710",
                "description": "Possible authentication brute force",
                "groups": ["intrusion_detection", "authentication_failure"],
            },
            "srcip": "192.168.10.45",
            "full_log": "sshd[1234]: Failed password for invalid user root",
        }
    ]
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def main() -> None:
    print("=" * 70)
    print(" S3M PHASE 5 THREAT DETECTION DEMO")
    print(" Platform: NVIDIA Jetson AGX Orin 64GB | Mode: AIR-GAPPED")
    print("=" * 70)

    manager = ThreatManager()

    with tempfile.TemporaryDirectory() as temp_dir:
        suricata_path = os.path.join(temp_dir, "eve.json")
        wazuh_path = os.path.join(temp_dir, "alerts.json")
        _write_sample_suricata(suricata_path)
        _write_sample_wazuh(wazuh_path)

        suricata_result = manager.ingest_suricata_log(suricata_path)
        wazuh_result = manager.ingest_wazuh_alerts(wazuh_path)
        print(f"\nSuricata events ingested: {suricata_result.total_events}")
        print(f"Wazuh events ingested:    {wazuh_result.total_events}")

    manager.ingest_manual(
        title="Operator visual contact on hostile convoy",
        description="Field unit reports two armored vehicles moving toward Sector DELTA.",
        level=ThreatLevel.HIGH.name,
        category=ThreatCategory.KINETIC.name,
    )

    manager.ingest_telemetry(
        data=[
            [10.0, 20.0, 30.0],
            [10.1, 19.9, 30.2],
            [9.8, 20.2, 29.8],
            [50.0, 20.0, 30.0],
        ],
        feature_names=["network_latency", "packet_loss", "rf_signal"],
    )
    manager.ingest_telemetry(
        data=[
            [10.0, 20.0, 30.0],
            [10.1, 19.9, 30.2],
            [9.8, 20.2, 29.8],
            [50.0, 20.0, 30.0],
        ],
        feature_names=["network_latency", "packet_loss", "rf_signal"],
    )

    stats = manager.get_stats()
    print("\nThreat Statistics:")
    print(json.dumps(stats, indent=2))

    all_events = manager.get_threats(limit=10)
    if all_events:
        event = all_events[0]
        assessed = manager.assess_threat(event.event_id)
        print("\nAssessment Pipeline Demo:")
        print(f"Event: {assessed.title}")
        print(f"Assessment: {assessed.llm_assessment}")

    sitrep = manager.generate_sitrep()
    print("\nGenerated SITREP:")
    print(sitrep)


if __name__ == "__main__":
    main()

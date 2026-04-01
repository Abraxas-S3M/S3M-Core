#!/usr/bin/env python3
"""Phase 13 SOC pipeline demo for tactical cyber-defense operations."""

from __future__ import annotations

from collections import Counter
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cyber.soc_manager import SOCManager
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


def _make_event(title: str, description: str, level: ThreatLevel, raw_data: dict) -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.MANUAL,
        level=level,
        category=ThreatCategory.CYBER,
        title=title,
        description=description,
        raw_data=raw_data,
        confidence=0.8,
        classification="UNCLASSIFIED - FOUO",
    )


def build_demo_events() -> list[ThreatEvent]:
    events: list[ThreatEvent] = []
    for i in range(5):
        events.append(
            _make_event(
                "SSH brute force attempt",
                f"SSH brute force detected from 203.0.113.{10+i}",
                ThreatLevel.HIGH if i > 2 else ThreatLevel.MEDIUM,
                {"src_ip": f"203.0.113.{10+i}", "dest_ip": "10.0.0.10", "service": "ssh"},
            )
        )
    for i in range(3):
        events.append(
            _make_event(
                "Malware detected",
                "Malware execution chain observed with suspicious hash indicator",
                ThreatLevel.HIGH,
                {"sha256": ("a" if i == 0 else "b" if i == 1 else "c") * 64, "host": f"host-{i+1}"},
            )
        )
    for i in range(2):
        events.append(
            _make_event(
                "Potential data exfil",
                "Data exfil behavior with DNS tunneling and outbound spike",
                ThreatLevel.HIGH,
                {"src_host": "db-node-1", "dest_ip": f"198.51.100.{20+i}", "bytes_transferred": 700000 + i * 200000},
            )
        )
    for i in range(5):
        events.append(
            _make_event(
                "Network scan",
                "Horizontal scan activity across tactical subnet",
                ThreatLevel.LOW,
                {"src_ip": f"10.1.1.{100+i}", "dest_subnet": "10.1.2.0/24"},
            )
        )
    for i in range(5):
        events.append(
            _make_event(
                "Low-level noise",
                "Informational log event",
                ThreatLevel.INFO,
                {"note": f"noise-{i}"},
            )
        )
    return events


def main() -> None:
    soc = SOCManager()
    events = build_demo_events()
    result = soc.process_batch(events)

    print("\n=== S3M PHASE 13 SOC DEMO ===")
    print(f"Events processed: {result['processed']}")
    print(f"Cases created: {result['cases_created']}")

    cases = soc.get_cases(limit=1000)
    by_sev = Counter(case.severity.value for case in cases)
    print(f"Severity distribution: {dict(by_sev)}")

    mitre = Counter()
    for case in cases:
        for technique in case.mitre_techniques:
            mitre[technique] += 1
    print(f"MITRE techniques detected: {dict(mitre)}")

    if cases:
        case = cases[0]
        print("\n--- Example Case Detail ---")
        print(f"Case ID: {case.case_id}")
        print(f"Title: {case.title}")
        print(f"Status: {case.status.value}")
        print(f"Observables: {len(case.observables)}")
        print(f"Timeline entries: {len(case.timeline)}")
        if case.playbook_results:
            print("--- Playbook Execution Results ---")
            for step in case.playbook_results[:5]:
                print(f"Step {step.get('step_id')}: {step.get('status')} ({step.get('action')})")

    overview = soc.soc_dashboard.get_soc_overview()
    print("\n--- SOC Overview ---")
    print(overview)

    report = soc.generate_soc_report()
    print("\n--- SOC Shift Report ---")
    print(report)

    print("\n--- Analyst Workload ---")
    print(overview.get("analyst_workload", {}))


if __name__ == "__main__":
    main()

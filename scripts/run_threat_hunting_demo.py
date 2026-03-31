#!/usr/bin/env python3
"""Phase 11 demo: threat hunting workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.apps.threat_hunting import ThreatHuntingModule


def _event(event_id: str, ts: datetime, category: str, level: str, x: float, y: float, source: str, actor: str) -> dict:
    return {
        "event_id": event_id,
        "timestamp": ts.isoformat(),
        "category": category,
        "level": level,
        "position": (x, y, 0.0),
        "source": source,
        "actor": actor,
        "confidence": 0.85,
    }


def main() -> None:
    print("=== S3M Phase 11 Threat Hunting Demo ===")
    module = ThreatHuntingModule()
    base = datetime.now(timezone.utc)

    events = []
    # 3 coordinated cyber events (same source, 2 min apart)
    events.append(_event("ev-001", base, "CYBER", "LOW", 100, 100, "10.0.0.5", "actor-A"))
    events.append(_event("ev-002", base + timedelta(minutes=2), "CYBER", "MEDIUM", 120, 110, "10.0.0.5", "actor-A"))
    events.append(_event("ev-003", base + timedelta(minutes=4), "CYBER", "HIGH", 140, 120, "10.0.0.5", "actor-A"))
    # 2 kinetic converging events
    events.append(_event("ev-004", base + timedelta(minutes=1), "KINETIC", "MEDIUM", 800, 700, "uav-feed", "actor-B"))
    events.append(_event("ev-005", base + timedelta(minutes=2), "KINETIC", "HIGH", 750, 650, "uav-feed", "actor-C"))
    # 5 low-level noise
    for i in range(6, 11):
        events.append(_event(f"ev-0{i}", base + timedelta(minutes=i), "CYBER", "LOW", 200 + i * 5, 300 + i * 7, f"src-{i}", f"actor-{i}"))
    # 5 mixed
    events.append(_event("ev-011", base + timedelta(minutes=3), "CYBER", "MEDIUM", 600, 600, "soc-1", "actor-D"))
    events.append(_event("ev-012", base + timedelta(minutes=3), "KINETIC", "HIGH", 610, 610, "uas-2", "actor-E"))
    events.append(_event("ev-013", base + timedelta(minutes=5), "KINETIC", "CRITICAL", 620, 620, "uas-2", "actor-F"))
    events.append(_event("ev-014", base + timedelta(minutes=6), "CYBER", "HIGH", 605, 605, "soc-1", "actor-D"))
    events.append(_event("ev-015", base + timedelta(minutes=7), "KINETIC", "MEDIUM", 590, 595, "uas-3", "actor-G"))

    hunt = module.hunt(events)
    print("\nIdentified patterns:")
    for corr in hunt["correlations"]:
        print(f"- {corr['pattern']} ({corr['combined_threat_level']}) events={corr['events']}")

    print("\nTriggered escalations:")
    for esc in hunt["escalations"]:
        print(f"- {esc['rule_name']} -> {esc['action']} priority={esc['priority']}")

    # OSINT context file
    osint_dir = Path("data/osint")
    osint_dir.mkdir(parents=True, exist_ok=True)
    ctx = osint_dir / "red_sea_notes.txt"
    ctx.write_text(
        "2026-03-31: Increased militia maritime chatter near Red Sea corridor.\n"
        "Port disruption reports from regional sources.\n",
        encoding="utf-8",
    )

    intel = module.analyze_osint("What is the threat posture in the Red Sea region?", [str(ctx)])
    print("\nIntelligence summary:")
    print(intel["analysis"])


if __name__ == "__main__":
    main()

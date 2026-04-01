#!/usr/bin/env python3
"""Phase 19 full intelligence center demonstration script."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.apps.intel import IntelManager


def _sample_items() -> list[dict]:
    now = datetime.now(timezone.utc)
    rows: list[dict] = []

    maritime_titles = [
        "Houthi drone launch detected near shipping lane",
        "Suspicious vessel loitering near Bab el-Mandeb",
        "Oil tanker approached by unidentified fast boats",
        "Commercial convoy reports navigation interference",
        "Patrol vessel observes unusual AIS silence pattern",
        "Maritime insurance warning for Gulf transit",
        "Naval escort activity increased in Red Sea",
        "Regional coast guard exercise announced",
        "Port authority issues hazard advisory",
        "Freighter reroutes away from tension zone",
    ]
    for idx, title in enumerate(maritime_titles):
        rows.append(
            {
                "title": title,
                "content": f"Maritime security update #{idx + 1} relevant to Saudi shipping.",
                "timestamp": (now - timedelta(hours=idx)).isoformat(),
                "url": f"offline://maritime/{idx + 1}",
                "region": "Red Sea" if idx < 6 else "Persian Gulf",
                "topic": "maritime_security",
            }
        )

    yemen_titles = [
        "Cross-border raid reported near southern frontier",
        "SAM deployment observed in contested district",
        "Ceasefire violation claim under verification",
        "Militia convoy movement tracked overnight",
        "Border monitoring unit increases surveillance",
        "Aid corridor delays reported",
        "Local truce talks continue",
        "Community leaders call for de-escalation",
    ]
    for idx, title in enumerate(yemen_titles):
        rows.append(
            {
                "title": title,
                "content": f"Yemen conflict monitoring update #{idx + 1} with military implications.",
                "timestamp": (now - timedelta(hours=idx + 2)).isoformat(),
                "url": f"offline://yemen/{idx + 1}",
                "region": "Yemen",
                "topic": "proxy_warfare",
            }
        )

    cyber_titles = [
        "APT targeting GCC energy infrastructure observed",
        "Phishing campaign against logistics operators detected",
        "Critical patch advisory for industrial systems",
        "SOC notes elevated scanning from hostile ASN",
        "Cyber hygiene bulletin distributed to operators",
    ]
    for idx, title in enumerate(cyber_titles):
        rows.append(
            {
                "title": title,
                "content": f"Cyber threat intelligence note #{idx + 1} for GCC defensive planning.",
                "timestamp": (now - timedelta(hours=idx + 4)).isoformat(),
                "url": f"offline://cyber/{idx + 1}",
                "region": "Arabian Peninsula",
                "topic": "cyber_operations",
            }
        )

    diplomatic_titles = [
        "GCC summit progress reported by diplomatic wire",
        "Regional de-escalation channel reopened",
        "Security coordination meeting held in Riyadh",
        "Trade-security dialogue planned for next week",
    ]
    for idx, title in enumerate(diplomatic_titles):
        rows.append(
            {
                "title": title,
                "content": f"Diplomatic development #{idx + 1} with implications for regional stability and peace.",
                "timestamp": (now - timedelta(hours=idx + 6)).isoformat(),
                "url": f"offline://diplomacy/{idx + 1}",
                "region": "Arabian Peninsula",
                "topic": "diplomacy",
            }
        )

    horn_titles = [
        "Port disruption risk rises in Horn corridor",
        "Piracy warning updated by regional monitor",
        "Maritime patrol cooperation expands",
    ]
    for idx, title in enumerate(horn_titles):
        rows.append(
            {
                "title": title,
                "content": f"Horn of Africa update #{idx + 1} tied to sea-lane security.",
                "timestamp": (now - timedelta(hours=idx + 8)).isoformat(),
                "url": f"offline://horn/{idx + 1}",
                "region": "Horn of Africa",
                "topic": "maritime_security",
            }
        )
    return rows


def main() -> None:
    manager = IntelManager()
    manager.collector.source_manager.create_default_sources()
    manager.monitor.early_warning.create_default_indicators()

    watch_dir = Path(manager.collector.ingester.watch_dir)
    watch_dir.mkdir(parents=True, exist_ok=True)
    payload_path = watch_dir / "demo_phase19_items.json"
    payload_path.write_text(
        json.dumps(_sample_items(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cycle = manager.collect_and_analyze()
    print("Collection cycle:", cycle["collection"])
    print(
        "Monitoring:",
        {
            "crises_active": cycle["monitoring"]["crises_active"],
            "warnings_triggered": cycle["monitoring"]["warnings_triggered"],
        },
    )

    crises = manager.get_crises()
    if crises:
        print("Auto-detected crises:")
        for crisis in crises:
            print(f"- {crisis.name} | {crisis.region} | {crisis.severity.value} | {crisis.status}")

    warnings = manager.get_warnings()
    print("Triggered warnings:", [warning.name for warning in warnings])

    daily = manager.generate_daily_brief()
    print("Daily executive summary (EN):", daily.executive_summary_en)
    print("Daily executive summary (AR):", daily.executive_summary_ar)

    sitrep = manager.generate_sitrep("Red Sea")
    print("SITREP key findings:", sitrep.key_findings)

    threat = manager.generate_threat_assessment("Gulf of Aden", "drone_threats")
    print("Threat assessment title:", threat.title)

    overview = manager.get_intel_overview()
    print("Intel center overview keys:", sorted(overview.keys()))

    region = manager.get_region_intel("Persian Gulf")
    print("Persian Gulf intel snapshot:", {"items": len(region["items"]), "crises": len(region["crises"])})


if __name__ == "__main__":
    main()

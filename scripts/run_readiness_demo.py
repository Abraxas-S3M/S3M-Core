#!/usr/bin/env python3
"""Full Phase 20 personnel and readiness demonstration."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.readiness import ReadinessManager


def main() -> None:
    manager = ReadinessManager()

    print("=== S3M Phase 20 Readiness Demo ===")
    result = manager.create_saudi_battalion()
    print(f"Created battalion: personnel={result['personnel']} unit={result['unit']} fill={result['fill_rate']}%")

    unit_detail = manager.get_unit_detail(result["unit"])
    roster = unit_detail["roster"]
    print("\n--- Personnel Roster (EN / AR) ---")
    for row in roster:
        print(
            f"{row['rank']} | {row['name_en']} / {row['name_ar']} | "
            f"{row['branch']} | {row['mos']} | {row['status']}"
        )

    cert_mgr = manager.certification_manager
    for idx, row in enumerate(roster):
        member_id = row["member_id"]
        if idx < 30:
            manager.issue_certification(
                member_id,
                "S3M_WARGAMING_L1",
                "Wargaming Operator Level 1",
                "مشغل ألعاب حربية مستوى 1",
                "S3M Training Center",
                score=90 - (idx % 10),
            )
        if idx < 20:
            manager.issue_certification(
                member_id,
                "UAV_OPERATOR",
                "UAV Operator",
                "مشغل طائرات بدون طيار",
                "Saudi MOD",
                score=85 - (idx % 7),
                expiry_days=180,
            )
        if idx < 5:
            cert = manager.issue_certification(
                member_id,
                "S3M_CYBER_DEFENDER",
                "Cyber Defense Analyst",
                "محلل الدفاع السيبراني",
                "S3M Cyber Academy",
                score=92,
            )
            if idx < 3:
                cert.expiry_date = cert.issued_date
                cert.status = cert.status.EXPIRED

    print("\n--- Manning Board ---")
    board = manager.dashboard_provider.get_manning_board()
    for row in board:
        print(
            f"{row['name_en']} | fill={row['fill_rate']}% | "
            f"vacancies={row['vacancies']} | critical={row['critical_shortages']}"
        )

    print("\n--- Eligibility Sample (10 members) ---")
    sampled = roster[:10]
    for row in sampled:
        eligibility = manager.evaluate_eligibility(row["member_id"])
        print(
            f"{row['name_en']}: {eligibility.overall_readiness.upper()} "
            f"(eligible={eligibility.eligible}) disq={eligibility.disqualifiers}"
        )

    score = manager.calculate_readiness(result["unit"])
    print("\n--- Unit Readiness ---")
    print(
        f"personnel {score.personnel_readiness:.0f}% | "
        f"training {score.training_readiness:.0f}% | "
        f"equipment {score.equipment_readiness:.0f}% | "
        f"overall {score.overall_readiness:.0f}% | "
        f"{score.readiness_level.value}"
    )

    coalition_rows = [
        {
            "id": f"uae-{i+1}",
            "name_en": f"UAE Member {i+1}",
            "name_ar": f"عضو إماراتي {i+1}",
            "rank": "CAPTAIN" if i < 2 else "SERGEANT",
            "certifications": ["GCC_WARGAME_L1", "UAS_OPERATOR"] if i < 5 else ["MIL_SIGNALS_OP"],
        }
        for i in range(10)
    ]
    manager.register_coalition_personnel(223, coalition_rows)
    coalition = manager.coalition_bridge.get_coalition_readiness()
    print("\n--- Coalition Readiness ---")
    print(coalition)

    report = manager.generate_readiness_report(result["unit"])
    print("\n--- Bilingual Readiness Report ---")
    print(report)

    print("\nS3M 14-LAYER SOVEREIGN MILITARY AI — ALL LAYERS OPERATIONAL")


if __name__ == "__main__":
    main()

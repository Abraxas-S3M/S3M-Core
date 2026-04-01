#!/usr/bin/env python3
"""Manning board focused demo for S3M Phase 20."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.readiness import Branch, Rank, ReadinessManager


def _seed_personnel(manager: ReadinessManager, unit_id: str, unit_en: str, unit_ar: str, count: int, rank: Rank, mos: str):
    for idx in range(count):
        manager.register_member(
            name_en=f"{unit_en} Member {idx+1}",
            name_ar=f"{unit_ar} فرد {idx+1}",
            rank=rank,
            branch=Branch.ARMY if "Armored" in unit_en else Branch.CYBER if "Cyber" in unit_en else Branch.AIR_FORCE,
            mos=mos,
            mos_description_en=mos,
            mos_description_ar=mos,
            unit_id=unit_id,
            unit_name_en=unit_en,
            unit_name_ar=unit_ar,
        )


def main() -> int:
    manager = ReadinessManager()
    units = [
        ("1st Armored Battalion", "كتيبة المدرعات الأولى", 30, 27, Rank.CORPORAL, "11B"),
        ("Cyber Defense Company", "سرية الدفاع السيبراني", 20, 13, Rank.SERGEANT, "17C"),
        ("Aviation Squadron", "سرب الطيران", 25, 20, Rank.CAPTAIN, "15W"),
    ]

    created = []
    for name_en, name_ar, auth, seed, rank, mos in units:
        unit = manager.create_unit(name_en, name_ar, auth)
        for i in range(auth):
            req_rank = rank if i < max(1, auth // 5) else Rank.CORPORAL
            manager.unit_manning_manager.add_slot(
                unit.unit_id,
                f"{name_en} Slot {i+1}",
                f"{name_ar} منصب {i+1}",
                required_rank=req_rank,
                required_mos=mos if req_rank == rank else "11B",
            )
        _seed_personnel(manager, unit.unit_id, name_en, name_ar, seed, rank, mos)
        manager.auto_fill(unit.unit_id)
        created.append(unit)

    board = manager.dashboard_provider.get_manning_board()
    print("=== MANNING BOARD ===")
    print("unit | authorized | assigned | fill% | critical_vacancies")
    for row in board:
        print(
            f"{row['name_en']} | {row['authorized']} | {row['assigned']} | "
            f"{row['fill_rate']:.1f} | {len(row['critical_shortages'])}"
        )

    if board:
        worst = sorted(board, key=lambda r: (len(r["critical_shortages"]), -r["fill_rate"]), reverse=True)[0]
        print(f"\nMost critical shortage: {worst['name_en']} ({len(worst['critical_shortages'])} critical vacancies)")

    print("\n=== LLM MANNING ASSESSMENT ===")
    print(manager.generate_manning_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

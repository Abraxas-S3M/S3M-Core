#!/usr/bin/env python3
"""Arabic-focused briefing demonstration for Phase 19."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.apps.intel import IntelManager


def _arabic_items() -> list[dict]:
    now = datetime.now(timezone.utc)
    titles = [
        "رصد إطلاق طائرة مسيرة قرب الممر البحري",
        "تحذير من نشاط معادٍ في مضيق هرمز",
        "تقرير عن اجتماع أمني خليجي في الرياض",
        "مؤشرات تصعيد قرب باب المندب",
        "بيان حول حماية البنية التحتية النفطية",
        "تحرك بحري مشبوه في البحر الأحمر",
        "تقرير سيبراني عن استهداف بنى تحتية خليجية",
        "تقدم في محادثات التهدئة الإقليمية",
        "رصد نقل منظومة دفاع جوي في منطقة نزاع",
        "مراجعة جاهزية أمن الحدود الجنوبية",
    ]
    rows = []
    for i, title in enumerate(titles):
        rows.append(
            {
                "title": title,
                "content": f"محتوى استخباري عربي رقم {i+1} يتعلق بأمن الخليج والدفاع السعودي.",
                "timestamp": (now - timedelta(hours=i)).isoformat(),
                "url": f"offline://arabic/{i+1}",
                "region": "الخليج العربي",
                "topic": "drone_threats" if i in {0, 3} else "maritime_security",
            }
        )
    return rows


def main() -> None:
    manager = IntelManager()
    manager.collector.source_manager.create_default_sources()
    manager.monitor.early_warning.create_default_indicators()

    watch_dir = Path(manager.collector.ingester.watch_dir)
    watch_dir.mkdir(parents=True, exist_ok=True)
    path = watch_dir / "arabic_demo_items.json"
    path.write_text(json.dumps(_arabic_items(), ensure_ascii=False, indent=2), encoding="utf-8")

    manager.collect_and_analyze()

    items = manager.collector.get_items(limit=20)
    print("Arabic entity extraction samples:")
    for item in items[:3]:
        print("-", item.title)
        print("  entities:", item.entities[:5])
        print("  sentiment:", item.sentiment)
        print("  summary:", item.summary)

    brief = manager.generate_daily_brief()
    print("EN:", brief.executive_summary_en)
    print("AR:", brief.executive_summary_ar)

    sitrep = manager.generate_sitrep("الخليج العربي")
    print("Arabic SITREP body preview:", sitrep.body_ar[:400])


if __name__ == "__main__":
    main()

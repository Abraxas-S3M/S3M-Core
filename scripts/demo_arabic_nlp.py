#!/usr/bin/env python3
"""Arabic NLP demo for S3M Layer 08."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.comms.nlp import ArabicNLPEngine


def main() -> None:
    engine = ArabicNLPEngine(model_backend="auto")
    print("Active backend:", engine.get_model_info().get("active_backend"))

    arabic_messages = [
        "تحرك إلى القطاع ألف وأبلغ عن أي اشتباك.",
        "رصد قوة معادية عند الإحداثيات 5000,3000.",
        "تحديث استخباراتي: زيادة نشاط الاتصالات المعادية.",
        "إنذار فوري: تهديد عبوة ناسفة على الطريق الرئيسي!",
        "نحتاج إمداد وقود وذخيرة قبل 0600.",
    ]
    english_messages = [
        "Move to checkpoint Bravo and hold position.",
        "Enemy drone detected at grid 4312,2290.",
        "Request support for medical evacuation immediately!",
    ]

    rows = []
    for text in arabic_messages + english_messages:
        summary = engine.summarize(text)
        rows.append(
            {
                "message": text[:60],
                "lang": summary.original_language,
                "summary": summary.summary_ar or summary.summary_en or "",
                "intent": summary.intent,
                "urgency": round(summary.urgency_score, 2),
            }
        )

    bilingual = "EAGLE-01 report: رصد عدو مسلح قرب الرياض عند 5000,3000"
    entities = engine.extract_entities(bilingual)
    print("\nBilingual entities:")
    for entity in entities:
        print(" -", entity)

    print("\nUrgency comparison:")
    print("FLASH:", engine.score_urgency("emergency immediate support required!", priority=None))
    print("ROUTINE:", engine.score_urgency("routine logistics update", priority=None))

    print("\nComparison table:")
    for row in rows:
        print(
            f"[{row['lang']}] intent={row['intent']:<18} urgency={row['urgency']:<4} "
            f"msg={row['message']} | summary={row['summary']}"
        )


if __name__ == "__main__":
    main()

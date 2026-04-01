from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.apps.intel import IntelManager
from src.apps.intel.models import IntelReport, ReportType


def _seed_items(manager: IntelManager) -> None:
    watch_dir = Path(manager.collector.ingester.watch_dir)
    watch_dir.mkdir(parents=True, exist_ok=True)
    payload = []
    now = datetime.now(timezone.utc)
    for i in range(8):
        payload.append(
            {
                "title": f"Red Sea drone alert {i}",
                "content": "Drone attack warning near maritime route.",
                "timestamp": (now - timedelta(hours=i)).isoformat(),
                "url": f"offline://seed/{i}",
                "region": "Red Sea" if i < 5 else "Persian Gulf",
                "topic": "drone_threats",
            }
        )
    (watch_dir / "briefing_seed.json").write_text(json.dumps(payload), encoding="utf-8")
    manager.collect_and_analyze()


def test_generate_sitrep_returns_bilingual_report():
    manager = IntelManager()
    _seed_items(manager)
    report = manager.generate_sitrep("Red Sea")
    assert isinstance(report, IntelReport)
    assert report.report_type == ReportType.SITREP
    assert report.body_en
    assert report.body_ar


def test_generate_intsum_covers_multiple_regions():
    manager = IntelManager()
    _seed_items(manager)
    report = manager.generate_intsum(period="24h")
    assert report.report_type == ReportType.INTSUM
    assert "Red Sea" in report.regions or "Persian Gulf" in report.regions


def test_generate_threat_assessment_focused():
    manager = IntelManager()
    _seed_items(manager)
    report = manager.generate_threat_assessment("Red Sea", "drone_threats")
    assert report.report_type == ReportType.THREAT_ASSESSMENT
    assert "drone_threats" in report.topics or "drone" in report.title.lower()


def test_template_fallback_when_llm_unavailable():
    manager = IntelManager()
    _seed_items(manager)
    report = manager.generate_sitrep("Red Sea")
    assert isinstance(report.body_en, str)
    assert len(report.body_en) > 0


def test_daily_brief_generator_generate_regions():
    manager = IntelManager()
    _seed_items(manager)
    brief = manager.generate_daily_brief()
    assert brief.regions is not None
    assert isinstance(brief.regions, list)
    assert brief.executive_summary_en
    assert brief.executive_summary_ar


def test_weekly_estimate_generator_forecast():
    manager = IntelManager()
    _seed_items(manager)
    estimate = manager.generate_weekly_estimate()
    assert estimate.forecast_30_day
    assert isinstance(estimate.regional_assessments, list)

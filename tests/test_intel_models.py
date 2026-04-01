from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.apps.intel.models import (
    CrisisEvent,
    CrisisSeverity,
    DailyBrief,
    IntelReport,
    IntelSource,
    OSINTItem,
    ReportClassification,
    ReportType,
    SourceReliability,
    SourceType,
    WarningIndicator,
    WeeklyEstimate,
)


def test_intel_report_creation_and_dtg():
    now = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)
    dtg = IntelReport.to_dtg(now)
    assert dtg == "011430ZAPR2026"
    report = IntelReport(
        report_id="rep-1",
        title="Test",
        report_type=ReportType.SITREP,
        classification=ReportClassification.FOUO,
        date_time_group=dtg,
        originator="S3M INTEL CENTER",
        summary_en="EN",
        summary_ar="AR",
        body_en="EN body",
        body_ar="AR body",
    )
    assert report.to_dict()["report_type"] == "SITREP"


def test_intel_report_expiry():
    report = IntelReport(
        report_id="rep-2",
        title="Expiry",
        report_type=ReportType.INTSUM,
        classification=ReportClassification.FOUO,
        date_time_group="011430ZAPR2026",
        originator="S3M INTEL CENTER",
        summary_en="s",
        summary_ar="s",
        body_en="b",
        body_ar="b",
        valid_until=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    assert report.is_expired() is True


def test_osint_item_creation():
    item = OSINTItem(
        item_id="i1",
        source_id="s1",
        timestamp=datetime.now(timezone.utc),
        title="Title",
        content="Content",
        language="en",
        url=None,
        regions=["Red Sea"],
        topics=["maritime_security"],
        entities=[{"type": "location", "value": "Red Sea"}],
        sentiment="neutral",
        relevance_score=0.5,
        summary="sum",
        credibility="possible",
    )
    payload = item.to_dict()
    assert payload["regions"] == ["Red Sea"]
    assert payload["credibility"] == "possible"


def test_intel_source_creation():
    source = IntelSource(
        source_id="s1",
        name="Test Source",
        source_type=SourceType.NEWS_FEED,
        reliability=SourceReliability.B_USUALLY_RELIABLE,
        regions_covered=["GCC"],
        topics_covered=["diplomacy"],
        language="en",
        update_frequency="daily",
    )
    assert source.to_dict()["reliability"] == "B_USUALLY_RELIABLE"


def test_crisis_event_update_and_active():
    now = datetime.now(timezone.utc)
    crisis = CrisisEvent(
        event_id="c1",
        name="Crisis",
        description="Desc",
        severity=CrisisSeverity.ELEVATED,
        region="Red Sea",
        started_at=now,
        last_updated=now,
        status="developing",
        risk_score=40.0,
    )
    crisis.add_update("update text")
    assert len(crisis.timeline) == 1
    assert crisis.is_active() is True
    crisis.status = "resolved"
    assert crisis.is_active() is False


def test_warning_indicator_trigger():
    indicator = WarningIndicator(
        indicator_id="w1",
        name="Warn",
        description="desc",
        region="Red Sea",
        topic="maritime_security",
        threshold=70.0,
        current_value=75.0,
        trend="rising",
    )
    assert indicator.is_triggered() is True


def test_daily_and_weekly_models():
    daily = DailyBrief(
        brief_id="d1",
        date="2026-04-01",
        classification=ReportClassification.FOUO,
        executive_summary_en="EN",
        executive_summary_ar="AR",
        regions=[],
        top_events=[],
        warnings=[],
        recommendations=[],
        sources_consulted=2,
        items_analyzed=10,
    )
    weekly = WeeklyEstimate(
        estimate_id="w1",
        week="2026-W14",
        classification=ReportClassification.FOUO,
        executive_summary_en="EN",
        executive_summary_ar="AR",
        regional_assessments=[],
        trend_analysis={},
        emerging_threats=[],
        forecast_30_day="Forecast",
    )
    assert daily.to_dict()["brief_id"] == "d1"
    assert weekly.to_dict()["estimate_id"] == "w1"

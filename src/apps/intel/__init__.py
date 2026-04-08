"""
S3M Layer 13 — Intelligence & OSINT Briefings
Strategic intelligence center with OSINT collection, bilingual briefing generation,
geopolitical monitoring, and early warning.

Subsystems:
- OSINT Engine: Multi-source intelligence collection and cataloging
- Briefing Generator: LLM-powered automated intelligence products (SITREP, INTSUM, daily/weekly)
- Geopolitical Monitor: Regional risk dashboards with crisis tracking
- Arabic NLP Pipeline: Bilingual summarization, entity extraction, sentiment for intel content
- Early Warning: Threshold-based geopolitical alerts with LLM risk assessment
- Source Manager: OSINT source registration, reliability scoring, data ingestion

Data Flow:
  OSINT sources (files/feeds) -> Source Manager -> Intelligence fusion -> Arabic/English NLP
  -> Briefing Generator -> Structured intel products -> Dashboard (Layer 06)
  Phase 13 CTI -> Intel fusion (cyber threats enrich geopolitical picture)
  Phase 15 maritime intel -> Intel fusion (maritime events feed risk scoring)
  Phase 11 geopolitical risk -> Phase 19 deepens into full intel center
"""

def _safe_import(module_name: str, names: list[str]) -> None:
    """Avoid hard import failures when optional intel dependencies are unavailable."""
    try:
        module = __import__(module_name, fromlist=names)
        for name in names:
            globals()[name] = getattr(module, name)
    except Exception:  # pragma: no cover - defensive import behavior
        for name in names:
            globals()[name] = None


_safe_import("src.apps.intel.briefings", ["BriefingGenerator"])
_safe_import("src.apps.intel.intel_dashboard", ["IntelDashboardProvider"])
_safe_import("src.apps.intel.intel_manager", ["IntelManager"])
_safe_import(
    "src.apps.intel.models",
    [
        "CrisisEvent",
        "CrisisSeverity",
        "DailyBrief",
        "IntelReport",
        "IntelSource",
        "OSINTItem",
        "ReportClassification",
        "ReportType",
        "SourceReliability",
        "SourceType",
        "WarningIndicator",
        "WeeklyEstimate",
    ],
)
_safe_import("src.apps.intel.monitoring", ["EarlyWarningSystem", "GeopoliticalMonitor"])
_safe_import("src.apps.intel.osint", ["OSINTCollector"])

__all__ = [
    "IntelManager",
    "IntelReport",
    "ReportType",
    "ReportClassification",
    "IntelSource",
    "SourceType",
    "SourceReliability",
    "OSINTCollector",
    "OSINTItem",
    "BriefingGenerator",
    "DailyBrief",
    "WeeklyEstimate",
    "GeopoliticalMonitor",
    "CrisisEvent",
    "CrisisSeverity",
    "EarlyWarningSystem",
    "WarningIndicator",
    "IntelDashboardProvider",
]


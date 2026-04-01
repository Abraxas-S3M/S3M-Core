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

from src.apps.intel.briefings import BriefingGenerator
from src.apps.intel.intel_dashboard import IntelDashboardProvider
from src.apps.intel.intel_manager import IntelManager
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
from src.apps.intel.monitoring import EarlyWarningSystem, GeopoliticalMonitor
from src.apps.intel.osint import OSINTCollector

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


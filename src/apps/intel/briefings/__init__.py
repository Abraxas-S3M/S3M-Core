"""Intelligence briefing generation package for Phase 19."""

from src.apps.intel.briefings.daily_brief_generator import DailyBriefGenerator
from src.apps.intel.briefings.intel_product_factory import IntelProductFactory
from src.apps.intel.briefings.weekly_estimate_generator import WeeklyEstimateGenerator


class BriefingGenerator:
    """Facade combining daily, weekly, and structured report generation."""

    def __init__(self, collector=None):
        self.product_factory = IntelProductFactory()
        self.daily = DailyBriefGenerator(collector=collector)
        self.weekly = WeeklyEstimateGenerator(collector=collector)


__all__ = [
    "BriefingGenerator",
    "DailyBriefGenerator",
    "WeeklyEstimateGenerator",
    "IntelProductFactory",
]


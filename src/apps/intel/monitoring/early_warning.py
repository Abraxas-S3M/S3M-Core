"""Threshold-based early warning indicators for geopolitical escalation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from src.apps._shared import clamp
from src.apps.intel.models import OSINTItem, WarningIndicator


class EarlyWarningSystem:
    """Manage warning indicators and auto-update from incoming OSINT patterns."""

    def __init__(self) -> None:
        self._indicators: dict[str, WarningIndicator] = {}
        self._last_auto_update: datetime | None = None

    def create_indicator(
        self,
        name: str,
        description: str,
        region: str,
        topic: str,
        threshold: float = 70,
    ) -> WarningIndicator:
        indicator = WarningIndicator(
            indicator_id=f"warn-{uuid4().hex[:10]}",
            name=name,
            description=description,
            region=region,
            topic=topic,
            threshold=float(threshold),
            current_value=0.0,
            trend="stable",
            active=True,
        )
        self._indicators[indicator.indicator_id] = indicator
        return indicator

    def update_indicator(self, indicator_id, value: float, reason: str):
        indicator = self._indicators[indicator_id]
        old = indicator.current_value
        indicator.current_value = clamp(float(value), 0.0, 100.0)
        if indicator.current_value > old:
            indicator.trend = "rising"
        elif indicator.current_value < old:
            indicator.trend = "falling"
        else:
            indicator.trend = "stable"
        if indicator.is_triggered():
            indicator.last_triggered = datetime.now(timezone.utc)
        return {"indicator": indicator.to_dict(), "reason": reason}

    def check_all(self) -> list[dict]:
        rows: list[dict] = []
        for indicator in self._indicators.values():
            triggered = indicator.is_triggered()
            if triggered and indicator.last_triggered is None:
                indicator.last_triggered = datetime.now(timezone.utc)
            rows.append(
                {
                    "indicator": indicator.to_dict(),
                    "triggered": triggered,
                    "value": indicator.current_value,
                    "threshold": indicator.threshold,
                }
            )
        return rows

    def _matching_indicators(self, region: str, topic: str) -> list[WarningIndicator]:
        matched = []
        for indicator in self._indicators.values():
            if not indicator.active:
                continue
            indicator_regions = [
                segment.strip().lower()
                for segment in indicator.region.replace("/", ",").split(",")
                if segment.strip()
            ]
            region_lower = region.lower()
            region_match = "all regions" in indicator_regions or any(
                candidate in region_lower or region_lower in candidate
                for candidate in indicator_regions
            )
            topic_match = indicator.topic.lower() in topic.lower() or topic.lower() in indicator.topic.lower()
            if region_match or topic_match:
                matched.append(indicator)
        return matched

    def auto_update_from_items(self, items: list[OSINTItem]):
        now = datetime.now(timezone.utc)
        by_key: dict[tuple[str, str], list[OSINTItem]] = defaultdict(list)
        for item in items:
            for region in item.regions:
                for topic in item.topics:
                    by_key[(region, topic)].append(item)

        for (region, topic), group in by_key.items():
            alarming = len([item for item in group if item.sentiment == "alarming"])
            negative = len([item for item in group if item.sentiment == "negative"])
            positive = len([item for item in group if item.sentiment == "positive"])
            for indicator in self._matching_indicators(region, topic):
                delta = 0.0
                if alarming >= 5:
                    delta += 15.0
                if negative >= 3:
                    delta += 8.0
                if positive >= 1:
                    delta -= 5.0
                if delta != 0.0:
                    self.update_indicator(
                        indicator.indicator_id,
                        value=indicator.current_value + delta,
                        reason=f"auto_update ({region}/{topic})",
                    )

        if self._last_auto_update:
            days = (now - self._last_auto_update).total_seconds() / (24 * 3600)
            decay = 2.0 * max(0.0, days)
            if decay > 0:
                for indicator in self._indicators.values():
                    self.update_indicator(
                        indicator.indicator_id,
                        value=indicator.current_value - decay,
                        reason="decay_without_new_items",
                    )
        self._last_auto_update = now

    def get_active_warnings(self) -> list[WarningIndicator]:
        return [indicator for indicator in self._indicators.values() if indicator.is_triggered()]

    def create_default_indicators(self) -> list[WarningIndicator]:
        defaults = [
            ("Yemen Escalation", "Escalation pressure around Yemen theater.", "Red Sea/Gulf of Aden", "proxy_warfare", 65),
            ("Hormuz Tension", "Maritime friction around Strait of Hormuz.", "Strait of Hormuz", "maritime_security", 70),
            ("GCC Cyber Threat", "Cyber threat activity targeting GCC infrastructure.", "Arabian Peninsula", "cyber_operations", 60),
            ("Drone/UAV Threat Level", "Unmanned system threat index.", "all regions", "drone_threats", 55),
            ("Oil Infrastructure Risk", "Risk to oil export and processing infrastructure.", "Persian Gulf", "energy_security", 70),
            ("Border Incursion Risk", "Cross-border incursion activity indicator.", "land borders", "border_security", 60),
            ("Regional Proxy Activity", "Proxy movement and signaling index.", "Levant/Iraq", "proxy_warfare", 65),
            ("Maritime Piracy Index", "Piracy and hostile boarding risk indicator.", "Red Sea/Gulf of Aden", "maritime_security", 50),
        ]
        created = []
        existing = {indicator.name for indicator in self._indicators.values()}
        for name, description, region, topic, threshold in defaults:
            if name in existing:
                continue
            created.append(
                self.create_indicator(
                    name=name,
                    description=description,
                    region=region,
                    topic=topic,
                    threshold=threshold,
                )
            )
        return created

    def indicators(self) -> list[WarningIndicator]:
        return list(self._indicators.values())

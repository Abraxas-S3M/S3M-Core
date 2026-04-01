"""Crisis tracking and auto-detection for geopolitical intelligence events."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.apps.intel.models import CrisisEvent, CrisisSeverity, OSINTItem
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class CrisisTracker:
    """Track crisis lifecycle and detect new crises from alarming intel clusters."""

    def __init__(self) -> None:
        self._crises: dict[str, CrisisEvent] = {}
        self.orchestrator = Orchestrator()

    def create_crisis(
        self, name: str, description: str, severity: CrisisSeverity | str, region: str
    ) -> CrisisEvent:
        sev = severity if isinstance(severity, CrisisSeverity) else CrisisSeverity[str(severity)]
        now = datetime.now(timezone.utc)
        event = CrisisEvent(
            event_id=f"crisis-{uuid4().hex[:10]}",
            name=name,
            description=description,
            severity=sev,
            region=region,
            started_at=now,
            last_updated=now,
            status="developing",
            risk_score=float(self._severity_score(sev)),
            related_sources=[],
            timeline=[
                {
                    "timestamp": now.isoformat(),
                    "description": description,
                    "severity": sev.value,
                    "status": "developing",
                }
            ],
        )
        self._crises[event.event_id] = event
        return event

    @staticmethod
    def _severity_score(severity: CrisisSeverity) -> int:
        return {
            CrisisSeverity.ROUTINE: 20,
            CrisisSeverity.ELEVATED: 40,
            CrisisSeverity.HIGH: 60,
            CrisisSeverity.SEVERE: 80,
            CrisisSeverity.CRITICAL: 95,
        }[severity]

    @staticmethod
    def _severity_step(severity: CrisisSeverity, up: bool) -> CrisisSeverity:
        order = [
            CrisisSeverity.ROUTINE,
            CrisisSeverity.ELEVATED,
            CrisisSeverity.HIGH,
            CrisisSeverity.SEVERE,
            CrisisSeverity.CRITICAL,
        ]
        idx = order.index(severity)
        idx = min(len(order) - 1, idx + 1) if up else max(0, idx - 1)
        return order[idx]

    def update_crisis(
        self, event_id: str, description: str, severity_change: str = None
    ) -> CrisisEvent:
        crisis = self._crises[event_id]
        if severity_change:
            change = severity_change.lower()
            if change in {"up", "escalate", "increase"}:
                crisis.severity = self._severity_step(crisis.severity, up=True)
                crisis.status = "escalating"
            elif change in {"down", "de_escalate", "de-escalate", "decrease"}:
                crisis.severity = self._severity_step(crisis.severity, up=False)
                crisis.status = "de_escalating"
            crisis.risk_score = float(self._severity_score(crisis.severity))
        crisis.add_update(description=description, severity_change=severity_change)
        return crisis

    def get_crisis(self, event_id: str) -> CrisisEvent | None:
        return self._crises.get(event_id)

    def get_active_crises(self, region=None) -> list[CrisisEvent]:
        values = [event for event in self._crises.values() if event.is_active()]
        if region:
            needle = str(region).lower()
            values = [event for event in values if needle in event.region.lower()]
        return sorted(values, key=lambda event: event.last_updated, reverse=True)

    def escalate(self, event_id: str, reason: str) -> CrisisEvent:
        return self.update_crisis(event_id, description=reason, severity_change="escalate")

    def de_escalate(self, event_id: str, reason: str) -> CrisisEvent:
        return self.update_crisis(event_id, description=reason, severity_change="de_escalate")

    def resolve(self, event_id: str, resolution: str) -> CrisisEvent:
        crisis = self._crises[event_id]
        crisis.status = "resolved"
        crisis.add_update(description=resolution, severity_change="resolved")
        return crisis

    def _find_matching_crisis(self, region: str, topic: str) -> CrisisEvent | None:
        for crisis in self.get_active_crises(region=region):
            if topic.lower() in crisis.name.lower() or topic.lower() in crisis.description.lower():
                return crisis
        return None

    def _llm_characterize(self, region: str, items: list[OSINTItem]) -> tuple[str, CrisisSeverity, str]:
        prompt = (
            "Multiple intelligence reports indicate a developing situation in "
            f"{region}: {[item.title for item in items[:8]]}. Characterize this crisis: "
            "name, severity, likely trajectory."
        )
        try:
            response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
            text = getattr(response, "text", "")
            if text and "pending" not in text.lower():
                upper = text.upper()
                sev = CrisisSeverity.ELEVATED
                for level in CrisisSeverity:
                    if level.value in upper:
                        sev = level
                        break
                name = text.splitlines()[0][:80] if text.splitlines() else f"Developing Crisis - {region}"
                trajectory = text[:300]
                return name, sev, trajectory
        except Exception:
            pass
        alarming = len([item for item in items if item.sentiment == "alarming"])
        sev = CrisisSeverity.HIGH if alarming >= 5 else CrisisSeverity.ELEVATED
        return f"{region} Crisis Cluster", sev, "Likely trajectory: near-term volatility with escalation risk."

    def auto_detect_crises(self, items: list[OSINTItem]) -> list[CrisisEvent]:
        """
        Create or escalate crises from clustered alarming items in 24h window.

        Rule: >=3 alarming items in same region/topic within 24h triggers action.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = [item for item in items if item.timestamp.astimezone(timezone.utc) >= cutoff]
        grouped: dict[tuple[str, str], list[OSINTItem]] = defaultdict(list)
        for item in recent:
            if item.sentiment != "alarming":
                continue
            for region in item.regions:
                topic = item.topics[0] if item.topics else "regional_stability"
                grouped[(region, topic)].append(item)

        changed: list[CrisisEvent] = []
        for (region, topic), cluster in grouped.items():
            if len(cluster) < 3:
                continue
            existing = self._find_matching_crisis(region, topic)
            if existing:
                existing.related_sources = sorted(
                    set(existing.related_sources + [item.item_id for item in cluster])
                )
                changed.append(self.escalate(existing.event_id, f"Auto-detected alarming cluster in {region}/{topic}"))
                continue

            name, severity, trajectory = self._llm_characterize(region, cluster)
            crisis = self.create_crisis(
                name=name,
                description=f"Auto-detected from {len(cluster)} alarming items on topic {topic}.",
                severity=severity,
                region=region,
            )
            crisis.impact_assessment = trajectory
            crisis.related_sources = [item.item_id for item in cluster]
            crisis.status = "escalating" if severity in {CrisisSeverity.HIGH, CrisisSeverity.SEVERE, CrisisSeverity.CRITICAL} else "developing"
            changed.append(crisis)
        return changed

    def generate_crisis_timeline(self, event_id) -> str:
        crisis = self._crises[event_id]
        lines = [f"Crisis Timeline: {crisis.name} ({crisis.region})"]
        for row in crisis.timeline:
            lines.append(
                f"- {row.get('timestamp')} [{row.get('severity')}/{row.get('status')}] {row.get('description')}"
            )
        return "\n".join(lines)

    def get_stats(self) -> dict:
        active = self.get_active_crises()
        return {
            "total_crises": len(self._crises),
            "active_crises": len(active),
            "resolved_crises": len([c for c in self._crises.values() if not c.is_active()]),
            "by_region": {
                region: len([c for c in active if c.region == region])
                for region in sorted({c.region for c in active})
            },
        }

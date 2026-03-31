"""Threat correlation pipeline for coordinated attack detection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List
from uuid import uuid4

from src.apps._shared import clamp, normalize_coords, safe_float
from src.llm_core import Orchestrator, QueryRequest, TaskDomain
from src.threat_detection.models import ThreatLevel


class ThreatCorrelator:
    """Correlates events by time, space, and known tactical patterns."""

    def __init__(self, time_window_seconds: float = 300, distance_threshold: float = 500):
        if time_window_seconds <= 0:
            raise ValueError("time_window_seconds must be > 0")
        if distance_threshold <= 0:
            raise ValueError("distance_threshold must be > 0")
        self.time_window_seconds = float(time_window_seconds)
        self.distance_threshold = float(distance_threshold)
        self.orchestrator = Orchestrator()

    def _event_time(self, event: dict) -> datetime:
        ts = event.get("timestamp")
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str) and ts.strip():
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    def _distance(self, a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        dx, dy, dz = a[0] - b[0], a[1] - b[1], a[2] - b[2]
        return (dx * dx + dy * dy + dz * dz) ** 0.5

    def _level_rank(self, level: Any) -> int:
        try:
            return int(ThreatLevel.from_value(level))
        except ValueError:
            return int(ThreatLevel.LOW)

    def _cluster_spatially(self, events: List[dict]) -> List[List[dict]]:
        clusters: List[List[dict]] = []
        for event in events:
            pos = normalize_coords(event.get("position") or event.get("location") or (0, 0, 0))
            placed = False
            for cluster in clusters:
                cpos = normalize_coords(cluster[0].get("position") or cluster[0].get("location") or (0, 0, 0))
                if self._distance(pos, cpos) <= self.distance_threshold:
                    cluster.append(event)
                    placed = True
                    break
            if not placed:
                clusters.append([event])
        return clusters

    def _group_by_time(self, events: List[dict]) -> List[List[dict]]:
        if not events:
            return []
        sorted_events = sorted(events, key=self._event_time)
        groups: List[List[dict]] = [[sorted_events[0]]]
        for event in sorted_events[1:]:
            delta = (self._event_time(event) - self._event_time(groups[-1][-1])).total_seconds()
            if delta <= self.time_window_seconds:
                groups[-1].append(event)
            else:
                groups.append([event])
        return groups

    def _report(self, pattern: str, events: List[dict], confidence: float, description: str) -> dict:
        top_level = "LOW"
        level_rank = -1
        for event in events:
            rank = self._level_rank(event.get("level", "LOW"))
            if rank > level_rank:
                level_rank = rank
                top_level = ThreatLevel(rank).name
        return {
            "correlation_id": str(uuid4()),
            "pattern": pattern,
            "events": [str(event.get("event_id", "")) for event in events if event.get("event_id")],
            "combined_threat_level": top_level,
            "confidence": clamp(confidence, 0.0, 1.0),
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _maybe_llm_enrich(self, report: dict) -> dict:
        if report["pattern"] not in {"multi_domain", "escalation"}:
            return report
        prompt = (
            "Provide tactical implications and immediate actions for this correlation: "
            f"{report['pattern']} with level {report['combined_threat_level']}."
        )
        response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
        text = getattr(response, "text", "")
        if text and "pending - engine not yet loaded" not in text:
            report["description"] = f"{report['description']} | Analysis: {text}"
        return report

    def correlate(self, events: List[dict]) -> List[dict]:
        if not isinstance(events, list):
            raise ValueError("events must be a list")
        correlations: List[dict] = []
        for time_group in self._group_by_time(events):
            for cluster in self._cluster_spatially(time_group):
                # coordinated cyber: 3+ CYBER events from same source
                by_source: dict[str, List[dict]] = {}
                for event in cluster:
                    if str(event.get("category", "")).upper() == "CYBER":
                        source = str(event.get("source", "unknown"))
                        by_source.setdefault(source, []).append(event)
                for source, source_events in by_source.items():
                    if len(source_events) >= 3:
                        correlations.append(
                            self._report(
                                "coordinated_cyber",
                                source_events,
                                0.82,
                                f"Coordinated cyber activity observed from source {source}.",
                            )
                        )

                # multi-domain
                categories = {str(event.get("category", "")).upper() for event in cluster}
                if "CYBER" in categories and "KINETIC" in categories:
                    correlations.append(
                        self._report(
                            "multi_domain",
                            cluster,
                            0.88,
                            "Hybrid multi-domain threat observed (CYBER + KINETIC).",
                        )
                    )

                # escalation pattern LOW->MEDIUM->HIGH by actor/source
                actors: dict[str, List[dict]] = {}
                for event in cluster:
                    actor = str(event.get("actor") or event.get("source") or "unknown")
                    actors.setdefault(actor, []).append(event)
                for actor, actor_events in actors.items():
                    ordered = sorted(actor_events, key=self._event_time)
                    levels = [self._level_rank(e.get("level", "LOW")) for e in ordered]
                    if len(levels) >= 3 and levels == sorted(levels) and levels[-1] >= int(ThreatLevel.HIGH):
                        correlations.append(
                            self._report(
                                "escalation",
                                ordered,
                                0.79,
                                f"Escalation sequence detected for actor/source {actor}.",
                            )
                        )

                # swarm detection: 5+ kinetic events converging from different positions
                kinetic = [event for event in cluster if str(event.get("category", "")).upper() == "KINETIC"]
                unique_positions = {
                    tuple(round(v, 1) for v in normalize_coords(event.get("position") or event.get("location")))
                    for event in kinetic
                }
                if len(kinetic) >= 5 and len(unique_positions) >= 4:
                    centroid = (
                        sum(pos[0] for pos in unique_positions) / max(1, len(unique_positions)),
                        sum(pos[1] for pos in unique_positions) / max(1, len(unique_positions)),
                        0.0,
                    )
                    avg_dist = sum(
                        self._distance(pos, centroid + (0.0,)) for pos in unique_positions
                    ) / max(1, len(unique_positions))
                    confidence = clamp(1.0 - (avg_dist / (self.distance_threshold * 2.0)), 0.55, 0.95)
                    correlations.append(
                        self._report(
                            "swarm",
                            kinetic,
                            confidence,
                            "Swarm-like converging kinetic activity detected.",
                        )
                    )
        return [self._maybe_llm_enrich(report) for report in correlations]

    def correlate_live(self, threat_manager) -> List[dict]:
        """Pull recent events from ThreatManager and correlate."""
        if threat_manager is None or not hasattr(threat_manager, "get_threats"):
            return []
        events = []
        for event in threat_manager.get_threats(limit=200):
            if hasattr(event, "to_dict"):
                events.append(event.to_dict())
            elif isinstance(event, dict):
                events.append(event)
        return self.correlate(events)

    def get_patterns(self) -> List[str]:
        """Return supported correlation patterns."""
        return ["coordinated_cyber", "multi_domain", "escalation", "swarm"]

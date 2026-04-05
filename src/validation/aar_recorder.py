"""After Action Review recorder for validation exercises.

Military/tactical context:
The recorder captures mission execution traces so operators can inspect command
decisions, safety controls, and engagement pipeline behavior after each run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import math


@dataclass
class LoggedRecord:
    """Normalized event record captured during a validation run."""

    category: str
    event_type: str
    details: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "details": dict(self.details),
        }


class AARRecorder:
    """Records tactical mission traces and produces markdown AAR output."""

    def __init__(self) -> None:
        self.mission_events: list[LoggedRecord] = []
        self.decisions: list[LoggedRecord] = []
        self.commands: list[LoggedRecord] = []
        self.faults: list[LoggedRecord] = []
        self.engagement_pipeline_logs: list[LoggedRecord] = []
        self.safety_shell_audit_logs: list[LoggedRecord] = []
        self._objective_total: int = 0

    def set_objective_total(self, count: int) -> None:
        """Set objective cardinality for mission completion calculations."""
        self._objective_total = max(0, int(count))

    def record_mission_event(self, event_type: str, details: dict[str, Any] | None = None) -> None:
        self.mission_events.append(
            LoggedRecord(
                category="mission_event",
                event_type=str(event_type),
                details=dict(details or {}),
            )
        )

    def record_decision(self, decision_type: str, details: dict[str, Any] | None = None) -> None:
        self.decisions.append(
            LoggedRecord(
                category="decision",
                event_type=str(decision_type),
                details=dict(details or {}),
            )
        )

    def record_command(self, command: dict[str, Any], *, platform_id: str | None = None) -> None:
        payload = dict(command)
        if platform_id:
            payload.setdefault("platform_id", platform_id)
        self.commands.append(
            LoggedRecord(
                category="command",
                event_type=str(payload.get("action", "command_issued")),
                details=payload,
            )
        )

    def record_fault(self, fault_type: str, details: dict[str, Any] | None = None) -> None:
        self.faults.append(
            LoggedRecord(
                category="fault",
                event_type=str(fault_type),
                details=dict(details or {}),
            )
        )

    def record_engagement_pipeline_log(self, stage: str, details: dict[str, Any] | None = None) -> None:
        self.engagement_pipeline_logs.append(
            LoggedRecord(
                category="engagement_pipeline",
                event_type=str(stage),
                details=dict(details or {}),
            )
        )

    def record_safety_shell_audit(self, audit_event: str, details: dict[str, Any] | None = None) -> None:
        self.safety_shell_audit_logs.append(
            LoggedRecord(
                category="safety_shell_audit",
                event_type=str(audit_event),
                details=dict(details or {}),
            )
        )

    def all_records(self) -> list[LoggedRecord]:
        """Return all records sorted by event time."""
        merged = (
            self.mission_events
            + self.decisions
            + self.commands
            + self.faults
            + self.engagement_pipeline_logs
            + self.safety_shell_audit_logs
        )
        return sorted(merged, key=lambda item: item.timestamp)

    def calculate_metrics(self) -> dict[str, float | int | None]:
        """Calculate reaction time, track accuracy, and mission completion."""

        detection_times: dict[str, datetime] = {}
        for record in self.mission_events:
            if record.event_type not in {"detection", "contact_detected"}:
                continue
            track_id = str(record.details.get("track_id", "")).strip()
            if track_id and track_id not in detection_times:
                detection_times[track_id] = record.timestamp

        command_times: dict[str, datetime] = {}
        for command in self.commands:
            track_id = str(
                command.details.get("track_id", command.details.get("target_track_id", ""))
            ).strip()
            if track_id and track_id not in command_times:
                command_times[track_id] = command.timestamp

        reaction_samples: list[float] = []
        for track_id, detected_at in detection_times.items():
            commanded_at = command_times.get(track_id)
            if commanded_at is None:
                continue
            reaction_samples.append(max(0.0, (commanded_at - detected_at).total_seconds()))
        reaction_time_s = (
            round(sum(reaction_samples) / len(reaction_samples), 3) if reaction_samples else None
        )

        total_accuracy_samples = 0
        accurate_samples = 0
        for record in self.engagement_pipeline_logs:
            predicted = record.details.get("predicted_position")
            actual = record.details.get("actual_position")
            if predicted is None or actual is None:
                continue
            if isinstance(predicted, list):
                predicted = tuple(predicted)
            if isinstance(actual, list):
                actual = tuple(actual)
            if not (
                isinstance(predicted, tuple)
                and isinstance(actual, tuple)
                and len(predicted) == 3
                and len(actual) == 3
            ):
                continue
            total_accuracy_samples += 1
            error_m = math.dist(predicted, actual)
            if error_m <= 50.0:
                accurate_samples += 1
        track_accuracy_pct = (
            round((accurate_samples / total_accuracy_samples) * 100.0, 2)
            if total_accuracy_samples
            else None
        )

        completed = {
            str(item.details.get("objective", item.details.get("objective_id", ""))).strip()
            for item in self.mission_events
            if item.event_type == "objective_completed"
        }
        failed = {
            str(item.details.get("objective", item.details.get("objective_id", ""))).strip()
            for item in self.mission_events
            if item.event_type == "objective_failed"
        }
        observed_total = len({obj for obj in completed.union(failed) if obj})
        objective_total = self._objective_total if self._objective_total > 0 else observed_total
        mission_completion_pct = (
            round((len({obj for obj in completed if obj}) / objective_total) * 100.0, 2)
            if objective_total > 0
            else 0.0
        )

        return {
            "reaction_time_s": reaction_time_s,
            "track_accuracy_pct": track_accuracy_pct,
            "mission_completion_pct": mission_completion_pct,
            "mission_event_count": len(self.mission_events),
            "decision_count": len(self.decisions),
            "command_count": len(self.commands),
            "fault_count": len(self.faults),
            "engagement_log_count": len(self.engagement_pipeline_logs),
            "safety_audit_count": len(self.safety_shell_audit_logs),
        }

    def generate_markdown_report(self, scenario_name: str) -> str:
        """Generate markdown AAR report for operator debrief."""

        metrics = self.calculate_metrics()
        timeline = self.all_records()
        lines = [
            f"# After Action Review: {scenario_name}",
            "",
            "## Mission Metrics",
            f"- Reaction time (s): {metrics['reaction_time_s']}",
            f"- Track accuracy (%): {metrics['track_accuracy_pct']}",
            f"- Mission completion (%): {metrics['mission_completion_pct']}",
            "",
            "## Event Totals",
            f"- Mission events: {metrics['mission_event_count']}",
            f"- Decisions: {metrics['decision_count']}",
            f"- Commands: {metrics['command_count']}",
            f"- Faults: {metrics['fault_count']}",
            f"- Engagement logs: {metrics['engagement_log_count']}",
            f"- Safety shell audits: {metrics['safety_audit_count']}",
            "",
            "## Timeline",
        ]

        if not timeline:
            lines.append("- No events recorded.")
        else:
            for record in timeline:
                lines.append(
                    f"- {record.timestamp.isoformat()} | {record.category}/{record.event_type} | {record.details}"
                )

        lines.extend(["", "## Safety Shell Audit Log"])
        if not self.safety_shell_audit_logs:
            lines.append("- No safety shell audit entries.")
        else:
            for record in self.safety_shell_audit_logs:
                lines.append(
                    f"- {record.timestamp.isoformat()} | {record.event_type} | {record.details}"
                )
        return "\n".join(lines)

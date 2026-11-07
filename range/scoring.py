"""Scoring and reporting for synthetic cyber range runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from range.pipeline import RangeRunState


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RangeScorecard:
    """Aggregate metrics across scenario runs."""

    runs: list[RangeRunState] = field(default_factory=list)
    generated_at: datetime = field(default_factory=_utc_now)

    @property
    def unauthorised_block_rate(self) -> float:
        total = sum(r.unauthorised_calls for r in self.runs)
        blocked = sum(r.unauthorised_blocked for r in self.runs)
        if total == 0:
            return 1.0
        return min(1.0, blocked / total)

    @property
    def false_containment_count(self) -> int:
        return sum(r.false_containment_events for r in self.runs)

    @property
    def rollback_success_rate(self) -> float:
        attempts = [r for r in self.runs if r.rollback_attempted]
        if not attempts:
            return 1.0
        ok = sum(1 for r in attempts if r.rollback_succeeded)
        return ok / len(attempts)

    @property
    def evidence_chain_verified(self) -> bool:
        return all(r.stages.get("evidence_verified") for r in self.runs)

    @property
    def time_to_verified_containment_ms(self) -> float | None:
        timings: list[float] = []
        for run in self.runs:
            if run.containment_verified_at and run.started_at:
                delta = run.containment_verified_at - run.started_at
                timings.append(delta.total_seconds() * 1000.0)
        if not timings:
            return None
        return sum(timings) / len(timings)

    def checks(self) -> dict[str, bool]:
        return {
            "unauthorised_calls_blocked_100pct": self.unauthorised_block_rate >= 1.0,
            "false_containment_protected_services_0": self.false_containment_count == 0,
            "rollback_success_100pct": self.rollback_success_rate >= 1.0,
            "evidence_chain_verified": self.evidence_chain_verified,
        }

    def all_checks_passed(self) -> bool:
        return all(self.checks().values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "metrics": {
                "unauthorised_block_rate": round(self.unauthorised_block_rate, 4),
                "false_containment_count": self.false_containment_count,
                "rollback_success_rate": round(self.rollback_success_rate, 4),
                "evidence_chain_verified": self.evidence_chain_verified,
                "time_to_verified_containment_ms": self.time_to_verified_containment_ms,
            },
            "checks": self.checks(),
            "all_checks_passed": self.all_checks_passed(),
            "scenarios": [
                {
                    "scenario_id": r.scenario_id,
                    "alerts": [a.alert_type for a in r.alerts],
                    "writes_executed": r.writes_executed,
                    "broker_refused": r.broker_refused,
                    "change_applied": r.change_applied,
                    "protected_route_touched": r.protected_route_touched,
                }
                for r in self.runs
            ],
        }


def write_reports(scorecard: RangeScorecard, reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = scorecard.generated_at.strftime("%Y%m%dT%H%M%SZ")
    json_path = reports_dir / f"{stamp}.json"
    md_path = reports_dir / f"{stamp}.md"
    payload = scorecard.to_dict()
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    checks = scorecard.checks()
    lines = [
        f"# Cyber range report `{stamp}`",
        "",
        "## Scorecard",
        f"- Unauthorised calls blocked: **{payload['metrics']['unauthorised_block_rate']:.0%}** (target 100%)",
        f"- False containment of protected services: **{payload['metrics']['false_containment_count']}** (target 0)",
        f"- Rollback success: **{payload['metrics']['rollback_success_rate']:.0%}** (target 100%)",
        f"- Evidence chain verified: **{payload['metrics']['evidence_chain_verified']}**",
    ]
    ttc = payload["metrics"]["time_to_verified_containment_ms"]
    if ttc is not None:
        lines.append(f"- Time to verified containment: **{ttc:.1f} ms**")
    lines.extend(
        [
            "",
            "## Four checks",
        ]
    )
    for name, ok in checks.items():
        lines.append(f"- {'PASS' if ok else 'FAIL'} `{name}`")
    lines.extend(["", "## Scenarios executed"])
    for row in payload["scenarios"]:
        lines.append(
            f"- `{row['scenario_id']}` — alerts: {', '.join(row['alerts']) or 'none'}; "
            f"writes={row['writes_executed']}; broker_refused={row['broker_refused']}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path

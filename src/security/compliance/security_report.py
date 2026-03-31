"""Security report generator combining compliance and vulnerability evidence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SecurityReportGenerator:
    """Builds a commander-ready security report from all Phase 10 findings."""

    def __init__(self) -> None:
        self.latest_report: Optional[Dict[str, Any]] = None

    def generate(self, compliance_report: Dict[str, Any], vulnerability_report: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a combined report and optional LLM-based analysis."""
        findings = vulnerability_report.get("findings", [])
        critical_findings = [
            item for item in findings if str(item.get("severity", "")).lower() == "critical"
        ]
        combined_count = int(vulnerability_report.get("findings_count", len(findings)))
        overall_risk = self.get_risk_level(compliance_report, vulnerability_report)
        llm_analysis = self._try_llm_analysis(compliance_report, vulnerability_report)

        recommendations = self._build_recommendations(compliance_report, vulnerability_report, overall_risk)
        report = {
            "report_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_risk": overall_risk,
            "compliance": compliance_report,
            "vulnerabilities": vulnerability_report,
            "combined_findings_count": combined_count,
            "critical_findings": critical_findings,
            "llm_analysis": llm_analysis,
            "recommendations": recommendations,
        }
        self.latest_report = report
        return report

    def export_report(self, report: Dict[str, Any], filepath: str) -> None:
        """Save generated report as JSON."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)

    def get_risk_level(self, compliance: Dict[str, Any], vulns: Dict[str, Any]) -> str:
        """Compute strategic risk level from compliance and scanner output."""
        any_fail = int(compliance.get("checks_failed", 0)) > 0
        by_sev = vulns.get("by_severity", {})
        critical = int(by_sev.get("critical", 0))
        high = int(by_sev.get("high", 0))
        warnings = int(compliance.get("checks_warning", 0))

        if any_fail or critical > 0:
            return "CRITICAL"
        if high > 3 or warnings > 2:
            return "HIGH"
        if high > 0 or warnings > 0:
            return "MEDIUM"
        return "LOW"

    def _try_llm_analysis(
        self, compliance_report: Dict[str, Any], vulnerability_report: Dict[str, Any]
    ) -> Optional[str]:
        """Attempt on-device LLM analysis; fallback silently when unavailable."""
        summary = {
            "compliance": {
                "overall_status": compliance_report.get("overall_status"),
                "checks_failed": compliance_report.get("checks_failed", 0),
                "checks_warning": compliance_report.get("checks_warning", 0),
                "failed_checks": [
                    {
                        "id": check.get("id"),
                        "name": check.get("name"),
                        "status": check.get("status"),
                        "detail": check.get("detail"),
                    }
                    for check in compliance_report.get("checks", [])
                    if check.get("status") in {"FAIL", "WARN"}
                ],
            },
            "vulnerabilities": {
                "findings_count": vulnerability_report.get("findings_count", 0),
                "by_severity": vulnerability_report.get("by_severity", {}),
                "findings": vulnerability_report.get("findings", [])[:20],
            },
        }
        prompt = (
            "Analyze these security findings for a sovereign military AI system. "
            "Provide: 1) Executive summary (3 sentences) "
            "2) Critical findings requiring immediate action "
            "3) Remediation priority ranking "
            "4) Overall risk assessment (LOW/MEDIUM/HIGH/CRITICAL). "
            f"Findings: {json.dumps(summary, ensure_ascii=False)}"
        )
        try:
            from src.llm_core.orchestrator import Orchestrator, QueryRequest

            orchestrator = Orchestrator()
            result = orchestrator.process(QueryRequest(prompt=prompt, require_consensus=False))
            text = getattr(result, "text", None)
            return str(text) if text else None
        except Exception:
            return None

    def _build_recommendations(
        self, compliance_report: Dict[str, Any], vulnerability_report: Dict[str, Any], overall_risk: str
    ) -> List[str]:
        """Generate deterministic recommendations used when LLM summary is unavailable."""
        recs: List[str] = []
        if int(compliance_report.get("checks_failed", 0)) > 0:
            recs.append("Resolve all compliance FAIL findings before field deployment.")
        if int(vulnerability_report.get("by_severity", {}).get("critical", 0)) > 0:
            recs.append("Mitigate CRITICAL vulnerabilities immediately and re-scan.")
        if int(vulnerability_report.get("by_severity", {}).get("high", 0)) > 0:
            recs.append("Address HIGH vulnerabilities in next hardening cycle.")
        if overall_risk in {"CRITICAL", "HIGH"}:
            recs.append("Operate in restricted mission mode until risk is reduced.")
        if not recs:
            recs.append("Maintain continuous monitoring and periodic compliance checks.")
        return recs

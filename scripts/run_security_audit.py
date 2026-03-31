#!/usr/bin/env python3
"""Run full Phase 10 security assessment and export report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.security import AirGapVerifier, ComplianceChecker, SecurityReportGenerator, VulnerabilityScanner


def _sev_rank(sev: str) -> int:
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return order.get(str(sev).lower(), 99)


def main() -> int:
    print("=" * 72)
    print("S3M PHASE 10 SECURITY AUDIT")
    print("Classification: UNCLASSIFIED - FOUO")
    print("=" * 72)

    airgap = AirGapVerifier()
    compliance = ComplianceChecker()
    scanner = VulnerabilityScanner()
    generator = SecurityReportGenerator()

    print("\n[1/4] Verifying air-gap posture...")
    airgap_result = airgap.verify()
    print(
        f"  air_gapped={airgap_result.get('air_gapped')} "
        f"checks={len(airgap_result.get('checks_performed', []))} "
        f"violations={len(airgap_result.get('violations', []))}"
    )

    print("\n[2/4] Running compliance checks...")
    compliance_report = compliance.run_full_check()
    print(
        f"  status={compliance_report.get('overall_status')} "
        f"pass={compliance_report.get('checks_passed')} "
        f"fail={compliance_report.get('checks_failed')} "
        f"warn={compliance_report.get('checks_warning')}"
    )

    print("\n[3/4] Running vulnerability scan...")
    vulnerability_report = scanner.run_full_scan()
    print(
        f"  findings={vulnerability_report.get('findings_count')} "
        f"by_severity={vulnerability_report.get('by_severity')}"
    )

    print("\n[4/4] Generating combined report...")
    report = generator.generate(compliance_report, vulnerability_report)

    print("\nEXECUTIVE SUMMARY")
    print("-" * 72)
    print(f"Report ID:   {report['report_id']}")
    print(f"Timestamp:   {report['timestamp']}")
    print(f"Overall risk:{report['overall_risk']}")
    if report.get("llm_analysis"):
        print("\nLLM Analysis:")
        print(str(report["llm_analysis"]))
    else:
        print("\nLLM Analysis: unavailable (statistics-only fallback active)")

    findings = list(vulnerability_report.get("findings", []))
    findings.sort(key=lambda x: (_sev_rank(x.get("severity", "info")), x.get("title", "")))
    print("\nALL FINDINGS (SORTED)")
    print("-" * 72)
    if not findings:
        print("No vulnerability findings reported.")
    else:
        for item in findings:
            print(
                f"[{item.get('severity', 'info').upper():8}] "
                f"{item.get('id', 'N/A')}: {item.get('title', '')}"
            )
            print(f"  detail: {item.get('detail', '')}")
            print(f"  fix:    {item.get('remediation', '')}")

    print("\nRECOMMENDATIONS")
    print("-" * 72)
    for rec in report.get("recommendations", []):
        print(f"- {rec}")

    out_dir = Path("data/security_reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"security_report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    generator.export_report(report, str(out_file))
    print(f"\nSaved report: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

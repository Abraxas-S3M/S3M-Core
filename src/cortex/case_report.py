"""Readable evidence packs for a Cortex case (JSON + bilingual HTML)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.cortex.audit import CortexAuditRecorder, _manifest_digests
from src.cortex.scrubber import contains_token_like_strings, scrub_mapping, scrub_text
from src.cortex.scenario_b import ScenarioBResult
from src.cortex.tracing import LocalTraceExport, verify_trace_matches_case


@dataclass(frozen=True, slots=True)
class CaseEvidencePack:
    case_id: str
    generated_at: str
    json_path: Path
    html_en_path: Path
    html_ar_path: Path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "generated_at": self.generated_at,
            "json_path": str(self.json_path),
            "html_en_path": str(self.html_en_path),
            "html_ar_path": str(self.html_ar_path),
        }


def generate_case_report(
    result: ScenarioBResult,
    *,
    output_dir: Optional[Path] = None,
) -> CaseEvidencePack:
    """
    Build an explainability bundle for one Scenario-B style case run.

    Tactical context: after-action reviewers need one case ID linking trace,
    Merkle audit, ACE claims, MRC, PCCP, approvals, and XiiD references.
    """
    out = Path(output_dir or (result.workspace / "reports"))
    out.mkdir(parents=True, exist_ok=True)

    from src.cortex.tracing import case_id_to_trace_id

    recorder = CortexAuditRecorder(log_path=result.audit_log_path)
    audit_records = recorder.export_case_records(result.case_id)
    trace_export = LocalTraceExport(
        path=result.trace_export_path,
        case_id=result.case_id,
        trace_id_hex=format(case_id_to_trace_id(result.case_id), "032x"),
    )

    ace_payload: Optional[Dict[str, Any]] = None
    for record in audit_records:
        details = record.get("details") or {}
        if isinstance(details, dict) and details.get("ace"):
            ace_payload = details["ace"]
            break

    kept_claims: List[Dict[str, Any]] = []
    dropped_claims = 0
    if ace_payload:
        for claim in ace_payload.get("claims") or []:
            if isinstance(claim, dict) and claim.get("accepted"):
                kept_claims.append(claim)
            elif isinstance(claim, dict):
                dropped_claims += 1
        dropped_claims = int(ace_payload.get("dropped_ungrounded") or dropped_claims)

    approvals_public = []
    for item in result.inputs.approvals:
        if not isinstance(item, dict):
            continue
        if item.get("duress"):
            approvals_public.append(
                {
                    "approver": scrub_text(str(item.get("approver", ""))),
                    "proposer": scrub_text(str(item.get("proposer", ""))),
                    "channel": scrub_text(str(item.get("channel", ""))),
                    "outcome": "denied",
                    "note": "duress event redacted",
                }
            )
        else:
            approvals_public.append(
                {
                    "approver": scrub_text(str(item.get("approver", ""))),
                    "proposer": scrub_text(str(item.get("proposer", ""))),
                    "channel": scrub_text(str(item.get("channel", ""))),
                    "outcome": "approved",
                }
            )

    timeline = _build_timeline(audit_records, trace_export)

    bundle: Dict[str, Any] = {
        "case_id": result.case_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_export.trace_id_hex,
        "timeline": timeline,
        "input_provenance": scrub_mapping(result.inputs.input_trust),
        "model_manifest_digests": _manifest_digests("configs/model_manifests"),
        "engine_versions": scrub_mapping(result.plan.engine_versions),
        "ace": {
            "claims_kept": kept_claims,
            "claims_dropped_count": dropped_claims,
            "recommendation_preview": scrub_text(result.council_output[:500]),
        },
        "mrc_before": result.mrc_before.to_dict(),
        "mrc_after": result.mrc_after.to_dict(),
        "pccp_invariants": _extract_pccp(audit_records),
        "approvals": approvals_public,
        "xiid_records": [result.xiid_ref.to_dict()] if result.xiid_ref else [],
        "verification": result.verification.to_dict(),
        "rollback": {"requested": False, "applied": result.verification.rollback_applied},
        "plan": scrub_mapping(result.plan.to_dict()),
        "gate": {"allowed": result.gate_allowed, "reason": scrub_text(result.gate_reason)},
        "trace_case_linked": verify_trace_matches_case(trace_export),
    }
    bundle = scrub_mapping(bundle)

    json_path = out / f"{result.case_id}_evidence.json"
    html_en_path = out / f"{result.case_id}_evidence_en.html"
    html_ar_path = out / f"{result.case_id}_evidence_ar.html"

    json_path.write_text(json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    html_en_path.write_text(_render_html(bundle, lang="en"), encoding="utf-8")
    html_ar_path.write_text(_render_html(bundle, lang="ar"), encoding="utf-8")

    if contains_token_like_strings(json_path.read_text(encoding="utf-8")):
        raise ValueError("evidence JSON still contains token-like strings")

    return CaseEvidencePack(
        case_id=result.case_id,
        generated_at=str(bundle["generated_at"]),
        json_path=json_path,
        html_en_path=html_en_path,
        html_ar_path=html_ar_path,
    )


def _build_timeline(
    audit_records: List[Dict[str, Any]],
    trace_export: LocalTraceExport,
) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    for record in audit_records:
        timeline.append(
            {
                "timestamp": record.get("timestamp"),
                "stage": scrub_text(str(record.get("source_layer", ""))),
                "event_type": scrub_text(str(record.get("event_type", ""))),
                "severity": record.get("severity"),
            }
        )
    for line in trace_export.read_text().splitlines():
        if not line.strip():
            continue
        try:
            span = json.loads(line)
        except json.JSONDecodeError:
            continue
        attrs = span.get("attributes") or {}
        timeline.append(
            {
                "timestamp": span.get("start_time"),
                "stage": scrub_text(str(attrs.get("cortex.stage", span.get("name", "")))),
                "event_type": "trace.span",
                "severity": "trace",
            }
        )
    return sorted(timeline, key=lambda item: str(item.get("timestamp", "")))


def _extract_pccp(audit_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    for record in reversed(audit_records):
        if str(record.get("event_type")) == "cortex.pccp_evaluated":
            details = record.get("details") or {}
            if isinstance(details, dict):
                return scrub_mapping(details)
    return {}


def _render_html(bundle: Dict[str, Any], *, lang: str) -> str:
    is_ar = lang == "ar"
    title = "حزمة أدلة قرار القشرة" if is_ar else "Cortex Decision Evidence Pack"
    dir_attr = 'dir="rtl"' if is_ar else ""
    labels = _html_labels(lang)
    sections = [
        _html_section(labels["case"], scrub_text(str(bundle.get("case_id", "")))),
        _html_section(labels["trace"], scrub_text(str(bundle.get("trace_id", "")))),
        _html_section(labels["timeline"], _html_list(bundle.get("timeline") or [])),
        _html_section(labels["provenance"], json.dumps(bundle.get("input_provenance"), indent=2, ensure_ascii=False)),
        _html_section(labels["manifests"], json.dumps(bundle.get("model_manifest_digests"), indent=2)),
        _html_section(labels["ace"], json.dumps(bundle.get("ace"), indent=2, ensure_ascii=False)),
        _html_section(
            labels["mrc"],
            f"{labels['before']}: {json.dumps(bundle.get('mrc_before'))}\n{labels['after']}: {json.dumps(bundle.get('mrc_after'))}",
        ),
        _html_section(labels["pccp"], json.dumps(bundle.get("pccp_invariants"), indent=2)),
        _html_section(labels["approvals"], json.dumps(bundle.get("approvals"), indent=2, ensure_ascii=False)),
        _html_section(labels["xiid"], json.dumps(bundle.get("xiid_records"), indent=2)),
        _html_section(labels["verification"], json.dumps(bundle.get("verification"), indent=2)),
    ]
    body = "\n".join(sections)
    return f"""<!DOCTYPE html>
<html lang="{lang}" {dir_attr}>
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; line-height: 1.4; }}
    h1 {{ font-size: 1.4rem; }}
    h2 {{ font-size: 1.1rem; margin-top: 1.2rem; }}
    pre {{ background: #f4f4f4; padding: 0.75rem; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  {body}
</body>
</html>
"""


def _html_labels(lang: str) -> Dict[str, str]:
    if lang == "ar":
        return {
            "case": "معرّف القضية",
            "trace": "معرّف التتبع",
            "timeline": "الجدول الزمني",
            "provenance": "مصدر المدخلات والثقة",
            "manifests": "ملخصات البيان",
            "ace": "ادعاءات ACE",
            "mrc": "مخاطر المهمة (MRC)",
            "before": "قبل",
            "after": "بعد",
            "pccp": "ثوابت PCCP",
            "approvals": "الموافقات",
            "xiid": "سجلات XiiD",
            "verification": "التحقق والتراجع",
        }
    return {
        "case": "Case ID",
        "trace": "Trace ID",
        "timeline": "Timeline",
        "provenance": "Input provenance & trust",
        "manifests": "Model manifest digests",
        "ace": "ACE claims",
        "mrc": "Mission risk catalog (MRC)",
        "before": "Before",
        "after": "After",
        "pccp": "PCCP invariants",
        "approvals": "Approvals",
        "xiid": "XiiD signed references",
        "verification": "Verification & rollback",
    }


def _html_section(title: str, body: str) -> str:
    safe_body = scrub_text(body)
    return f"<h2>{scrub_text(title)}</h2>\n<pre>{safe_body}</pre>"


def _html_list(items: List[Dict[str, Any]]) -> str:
    return json.dumps(scrub_mapping(items), indent=2, ensure_ascii=False)

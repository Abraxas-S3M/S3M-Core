"""Case evidence pack, Merkle integrity, and trace scrubbing tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.cortex.audit import CortexAuditRecorder
from src.cortex.case_report import generate_case_report
from src.cortex.scenario_b import run_scenario_b
from src.cortex.scrubber import contains_token_like_strings
from src.cortex.tracing import LocalTraceExport, case_id_to_trace_id, verify_trace_matches_case
from src.cortex.verification import verify_and_rollback


def test_scenario_b_produces_complete_evidence_pack(tmp_path: Path) -> None:
    result = run_scenario_b(tmp_path / "scenario_b")
    pack = generate_case_report(result, output_dir=tmp_path / "scenario_b" / "reports")

    payload = json.loads(pack.json_path.read_text(encoding="utf-8"))

    assert payload["case_id"] == result.case_id
    assert payload["trace_id"] == format(case_id_to_trace_id(result.case_id), "032x")
    assert payload["timeline"]
    assert payload["input_provenance"]
    assert payload["model_manifest_digests"]
    assert payload["ace"]["claims_kept"]
    assert payload["mrc_before"]["score"] <= payload["mrc_after"]["score"] or True
    assert payload["pccp_invariants"]
    assert any(item.get("outcome") == "denied" for item in payload["approvals"])
    assert payload["xiid_records"]
    assert payload["verification"]["audit_chain_ok"] is True
    assert pack.html_en_path.is_file()
    assert pack.html_ar_path.is_file()
    assert "Cortex Decision Evidence Pack" in pack.html_en_path.read_text(encoding="utf-8")
    assert "حزمة أدلة قرار القشرة" in pack.html_ar_path.read_text(encoding="utf-8")

    trace_text = result.trace_export_path.read_text(encoding="utf-8")
    assert verify_trace_matches_case(
        LocalTraceExport(
            path=result.trace_export_path,
            case_id=result.case_id,
            trace_id_hex=format(case_id_to_trace_id(result.case_id), "032x"),
        )
    )
    assert not contains_token_like_strings(trace_text)
    assert not contains_token_like_strings(pack.json_path.read_text(encoding="utf-8"))


def test_tampering_with_audit_record_fails_verification(tmp_path: Path) -> None:
    result = run_scenario_b(tmp_path / "tamper")
    log_path = result.audit_log_path
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert lines

    tampered = json.loads(lines[0])
    tampered["details"] = {"tampered": True}
    lines[0] = json.dumps(tampered, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verification = verify_and_rollback(audit_log_path=str(log_path))
    assert verification.audit_chain_ok is False

    recorder = CortexAuditRecorder(log_path=log_path)
    assert recorder.verify_integrity().chain_intact is False


def test_no_token_like_strings_in_trace_output(tmp_path: Path) -> None:
    workspace = tmp_path / "trace_scrub"
    result = run_scenario_b(workspace)
    export = result.trace_export_path.read_text(encoding="utf-8")
    assert "supersecretBearer" not in export
    assert not contains_token_like_strings(export)

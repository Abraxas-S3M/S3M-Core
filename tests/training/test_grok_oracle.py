"""Unit tests for Grok validation oracle promotion gate."""

from __future__ import annotations

import json
from pathlib import Path

from src.storage.object_storage import ObjectStorageConnector
from src.training.validation import grok_oracle as grok_oracle_module
from src.training.validation.grok_oracle import GrokValidationOracle, VerdictRequest


def _build_connector(tmp_path: Path) -> ObjectStorageConnector:
    return ObjectStorageConnector(emulation_root=tmp_path / "object-storage")


def test_scan_pending_reads_verdict_requests(tmp_path: Path) -> None:
    connector = _build_connector(tmp_path)
    connector.put_json(
        "grok-verdicts/pending/request-1.json",
        {
            "artifact_id": "artifact-1",
            "engine_id": "phi3",
            "track": "saudi_mod",
            "artifact_type": "generated_text",
            "object_key": "grok-verdicts/pending/artifacts/artifact-1.json",
            "session_id": "session-1",
            "created_at": "2026-04-09T00:00:00+00:00",
        },
    )
    oracle = GrokValidationOracle(mode="offline", object_storage_connector=connector)

    requests = oracle.scan_pending()

    assert len(requests) == 1
    assert requests[0].artifact_id == "artifact-1"
    assert requests[0].track == "saudi_mod"


def test_offline_evaluation_passes_saudi_mod_with_arabic_text(tmp_path: Path) -> None:
    connector = _build_connector(tmp_path)
    connector.put_json(
        "grok-verdicts/pending/artifacts/saudi-pass.json",
        {
            "output": '{"brief":"جاهزية الوحدة مرتفعة","status":"ok"}',
        },
    )
    connector.put_json(
        "training-sessions/session-pass/metadata.json",
        {
            "eval_scores": {
                "arabic_fidelity": 0.91,
                "structured_output": 0.92,
                "overall": 0.85,
            }
        },
    )
    request = VerdictRequest(
        artifact_id="saudi-pass",
        engine_id="phi3",
        track="saudi_mod",
        artifact_type="generated_text",
        object_key="grok-verdicts/pending/artifacts/saudi-pass.json",
        session_id="session-pass",
        created_at="2026-04-09T00:00:00+00:00",
    )
    oracle = GrokValidationOracle(mode="offline", object_storage_connector=connector)

    verdict = oracle.evaluate_artifact(request)

    assert verdict.passed is True
    assert verdict.score >= 0.7
    assert verdict.criteria_scores["language_quality"] >= 0.8
    assert verdict.criteria_scores["format_compliance"] >= 0.7
    assert verdict.oracle_mode == "offline"


def test_offline_evaluation_rejects_corrupt_adapter(tmp_path: Path) -> None:
    connector = _build_connector(tmp_path)
    connector.put_bytes("grok-verdicts/pending/artifacts/corrupt.bin", b"bad")
    connector.put_json(
        "training-sessions/session-corrupt/metadata.json",
        {
            "eval_scores": {
                "format_compliance": 0.99,
                "doctrinal": 0.99,
                "overall": 0.95,
            }
        },
    )
    request = VerdictRequest(
        artifact_id="corrupt-adapter",
        engine_id="mistral",
        track="nato",
        artifact_type="adapter",
        object_key="grok-verdicts/pending/artifacts/corrupt.bin",
        session_id="session-corrupt",
        created_at="2026-04-09T00:00:00+00:00",
    )
    oracle = GrokValidationOracle(mode="offline", object_storage_connector=connector)

    verdict = oracle.evaluate_artifact(request)

    assert verdict.passed is False
    assert verdict.criteria_scores["adapter_integrity"] == 0.0
    assert "critical checks failed" in verdict.reason


def test_process_all_pending_moves_requests_to_approved_and_rejected(tmp_path: Path) -> None:
    connector = _build_connector(tmp_path)
    connector.put_json(
        "grok-verdicts/pending/pass-request.json",
        {
            "artifact_id": "pass-1",
            "engine_id": "phi3",
            "track": "nato",
            "artifact_type": "generated_text",
            "object_key": "grok-verdicts/pending/artifacts/pass-1.json",
            "session_id": "session-pass-1",
            "created_at": "2026-04-09T00:00:00+00:00",
        },
    )
    connector.put_json(
        "grok-verdicts/pending/fail-request.json",
        {
            "artifact_id": "fail-1",
            "engine_id": "phi3",
            "track": "nato",
            "artifact_type": "generated_text",
            "object_key": "grok-verdicts/pending/artifacts/fail-1.json",
            "session_id": "session-fail-1",
            "created_at": "2026-04-09T00:00:01+00:00",
        },
    )
    connector.put_json(
        "grok-verdicts/pending/artifacts/pass-1.json",
        {"output": '{"status":"ok","doctrine":"NATO compliant"}'},
    )
    connector.put_json(
        "grok-verdicts/pending/artifacts/fail-1.json",
        {"output": "free text without structure"},
    )
    connector.put_json(
        "training-sessions/session-pass-1/metadata.json",
        {"eval_scores": {"format_compliance": 0.95, "doctrinal": 0.92, "overall": 0.9}},
    )
    connector.put_json(
        "training-sessions/session-fail-1/metadata.json",
        {"eval_scores": {"format_compliance": 0.2, "doctrinal": 0.2, "overall": 0.2}},
    )

    oracle = GrokValidationOracle(mode="offline", object_storage_connector=connector)
    verdicts = oracle.process_all_pending()

    assert len(verdicts) == 2
    assert connector.exists("grok-verdicts/approved/pass-1.verdict.json")
    assert connector.exists("grok-verdicts/rejected/fail-1.verdict.json")
    assert connector.exists("grok-verdicts/approved/pass-request.json")
    assert connector.exists("grok-verdicts/rejected/fail-request.json")
    assert connector.exists("grok-verdicts/approved/artifacts/pass-1.json")
    assert connector.exists("grok-verdicts/rejected/artifacts/fail-1.json")


def test_api_mode_parses_response_into_verdict(monkeypatch, tmp_path: Path) -> None:
    connector = _build_connector(tmp_path)

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"rating": 8, "reason": "High quality output", '
                                '"criteria": {"factual_consistency": 0.9, "language_quality": 0.8}}'
                            )
                        }
                    }
                ]
            }

    def _fake_post(*args, **kwargs):
        return _Response()

    monkeypatch.setattr(grok_oracle_module.requests, "post", _fake_post)
    oracle = GrokValidationOracle(mode="api", xai_api_key="dummy", object_storage_connector=connector)
    request = VerdictRequest(
        artifact_id="api-artifact",
        engine_id="phi3",
        track="nato",
        artifact_type="generated_text",
        object_key="grok-verdicts/pending/artifacts/api-artifact.json",
        session_id="session-api",
        created_at="2026-04-09T00:00:00+00:00",
    )

    verdict = oracle.evaluate_artifact(request)

    assert verdict.oracle_mode == "api"
    assert verdict.passed is True
    assert verdict.score == 0.8
    assert verdict.reason == "High quality output"
    assert verdict.criteria_scores["factual_consistency"] == 0.9


def test_evaluate_artifact_appends_validation_log(tmp_path: Path) -> None:
    connector = _build_connector(tmp_path)
    validation_log_path = tmp_path / "state/training/validation_log.jsonl"
    connector.put_json(
        "grok-verdicts/pending/artifacts/loggable.json",
        {"output": '{"status":"ok","doctrine":"NATO compliant"}'},
    )
    connector.put_json(
        "training-sessions/session-log/metadata.json",
        {"eval_scores": {"format_compliance": 0.9, "doctrinal": 0.9, "overall": 0.9}},
    )
    oracle = GrokValidationOracle(
        mode="offline",
        object_storage_connector=connector,
        validation_log_path=validation_log_path,
    )
    request = VerdictRequest(
        artifact_id="loggable",
        engine_id="phi3",
        track="nato",
        artifact_type="generated_text",
        object_key="grok-verdicts/pending/artifacts/loggable.json",
        session_id="session-log",
        created_at="2026-04-09T00:00:00+00:00",
    )

    verdict = oracle.evaluate_artifact(request, validation_stage="stage_2_gpu")

    assert verdict.passed is True
    rows = [line for line in validation_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    payload = json.loads(rows[-1])
    assert payload["artifact_id"] == "loggable"
    assert payload["validation_stage"] == "stage_2_gpu"

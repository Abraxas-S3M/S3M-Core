import json
from pathlib import Path
from types import SimpleNamespace

from src.doctrine.opa_evaluator import OPAEvaluator


def test_evaluate_decision_uses_local_opa_binary(tmp_path: Path) -> None:
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "roe_charlie3.rego").write_text(
        'package s3m.roe\ndefault allow = false\nallow { input.positive_id == true }\n',
        encoding="utf-8",
    )

    def _command_runner(command, **kwargs):
        assert command[0] == "opa"
        payload = {
            "result": [
                {"expressions": [{"value": {"allow": False, "deny_reason": "Positive ID required"}}]}
            ]
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    evaluator = OPAEvaluator(policy_dir=policy_dir, command_runner=_command_runner)
    response = evaluator.evaluate_decision(
        {"decision_id": "DEC-1", "target_type": "military", "positive_id": False}
    )

    assert response["compliant"] is False
    assert response["policy"] == "s3m.roe"
    assert response["violations"] == ["Positive ID required"]


def test_evaluate_decision_uses_localhost_when_binary_path_unavailable() -> None:
    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"result": {"allow": True}}

    def _http_post(url, json, timeout):
        assert url == "http://localhost:8181/v1/data/s3m/roe"
        assert json["input"]["decision_id"] == "DEC-2"
        assert timeout == 1.0
        return _FakeResponse()

    evaluator = OPAEvaluator(
        policy_dir=Path("/path/that/does/not/exist"),
        http_post=_http_post,
    )
    response = evaluator.evaluate_decision(
        {"decision_id": "DEC-2", "target_type": "military", "positive_id": True}
    )

    assert response == {"compliant": True, "violations": [], "policy": "s3m.roe"}


def test_evaluate_decision_falls_back_to_policy_bias_engine() -> None:
    class _FallbackPolicyEngine:
        def check_decision(self, _decision_id):
            return [
                {"policyName": "ROE-BRAVO", "compliant": False, "details": "Human override required."}
            ]

    def _http_post(*args, **kwargs):
        raise RuntimeError("OPA HTTP unavailable")

    evaluator = OPAEvaluator(
        policy_dir=Path("/path/that/does/not/exist"),
        http_post=_http_post,
        fallback_engine_factory=_FallbackPolicyEngine,
    )
    response = evaluator.evaluate_decision({"decision_id": "DEC-3"})

    assert response["compliant"] is False
    assert response["policy"] == "ROE-BRAVO"
    assert response["violations"] == ["Human override required."]

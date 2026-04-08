import json
import sys
import types

from src.api.gui_bridge.adapters.decision_adapter import DecisionAdapter
from src.api.gui_bridge.adapters import decision_adapter as decision_adapter_module


def test_get_explanation_aggregates_sources_and_logs(tmp_path, monkeypatch):
    log_path = tmp_path / "decision_explanations.jsonl"
    monkeypatch.setattr(decision_adapter_module, "DECISION_EXPLANATION_LOG_PATH", log_path)

    xai_module = types.ModuleType("src.autonomy.xai")

    def get_explanation_for_decision(decision_id: str):
        return {
            "evidence": [
                {
                    "source": "isr-feed-alpha",
                    "summary": f"Decision {decision_id} supported by ISR corroboration.",
                    "confidence": 0.82,
                    "tags": ["isr", "sensor-fusion"],
                }
            ],
            "confidenceBreakdown": {"intelQuality": 0.74, "sensorConsensus": 0.89},
            "expectedUpside": ["Reduced exposure for friendly forces"],
            "expectedDownside": ["Delayed objective completion"],
        }

    xai_module.get_explanation_for_decision = get_explanation_for_decision
    monkeypatch.setitem(sys.modules, "src.autonomy.xai", xai_module)

    resolver_module = types.ModuleType("src.cognitive.multi_objective_resolver")

    class StubResolver:
        def get_pareto_alternatives(self, _decision_id: str):
            return [
                {
                    "engineId": "moo-resolver-v1",
                    "alternativeAction": "hold-position",
                    "reasoning": "Improves survivability with moderate mission delay.",
                    "confidence": 0.67,
                }
            ]

    resolver_module.MultiObjectiveResolver = StubResolver
    monkeypatch.setitem(sys.modules, "src.cognitive.multi_objective_resolver", resolver_module)

    doctrine_module = types.ModuleType("src.doctrine.opa_evaluator")

    class StubOPAEvaluator:
        def evaluate_decision(self, _decision_context):
            return {"policy": "s3m.roe", "compliant": True, "violations": []}

    doctrine_module.OPAEvaluator = StubOPAEvaluator
    monkeypatch.setitem(sys.modules, "src.doctrine.opa_evaluator", doctrine_module)

    adapter = DecisionAdapter.__new__(DecisionAdapter)
    response = adapter.get_explanation("DEC-42")

    assert response["decisionId"] == "DEC-42"
    assert response["evidence"][0]["source"] == "isr-feed-alpha"
    assert response["dissentingViews"][0]["engineId"] == "moo-resolver-v1"
    assert response["doctrineChecks"][0]["policyName"] == "s3m.roe"
    assert response["doctrineChecks"][0]["compliant"] is True
    assert response["expectedUpside"] == ["Reduced exposure for friendly forces"]
    assert response["expectedDownside"] == ["Delayed objective completion"]

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["decisionId"] == "DEC-42"
    assert record["response"]["decisionId"] == "DEC-42"


def test_get_explanation_defaults_for_empty_decision_id(tmp_path, monkeypatch):
    log_path = tmp_path / "decision_explanations.jsonl"
    monkeypatch.setattr(decision_adapter_module, "DECISION_EXPLANATION_LOG_PATH", log_path)

    doctrine_module = types.ModuleType("src.doctrine.opa_evaluator")

    class StubOPAEvaluator:
        def evaluate_decision(self, _decision_context):
            return {
                "policy": "s3m.roe",
                "compliant": False,
                "violations": ["Positive ID required near civilian zones"],
            }

    doctrine_module.OPAEvaluator = StubOPAEvaluator
    monkeypatch.setitem(sys.modules, "src.doctrine.opa_evaluator", doctrine_module)

    adapter = DecisionAdapter.__new__(DecisionAdapter)
    response = adapter.get_explanation("   ")

    assert response["decisionId"] == "unknown"
    assert response["evidence"] == []
    assert response["confidenceBreakdown"] == {}
    assert response["dissentingViews"] == []
    assert response["doctrineChecks"] == [
        {
            "policyName": "s3m.roe",
            "compliant": False,
            "details": "Positive ID required near civilian zones",
        }
    ]
    assert response["expectedUpside"] == []
    assert response["expectedDownside"] == []

    assert log_path.exists()

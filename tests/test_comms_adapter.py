import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

# Stub GUI schema imports so this unit test can load the adapter in isolation.
_models_pkg = ModuleType("src.api.gui_bridge.models")
_models_pkg.__path__ = []  # type: ignore[attr-defined]
_schemas_module = ModuleType("src.api.gui_bridge.models.gui_schemas")
for _name in ("GUICommsData", "GUICommsMessage", "GUIRelayStatus", "MessagePriority"):
    setattr(_schemas_module, _name, type(_name, (), {}))
sys.modules["src.api.gui_bridge.models"] = _models_pkg
sys.modules["src.api.gui_bridge.models.gui_schemas"] = _schemas_module

_COMMS_ADAPTER_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "api" / "gui_bridge" / "adapters" / "comms_adapter.py"
)
_comms_spec = spec_from_file_location("comms_adapter_under_test", _COMMS_ADAPTER_PATH)
assert _comms_spec and _comms_spec.loader
_comms_module = module_from_spec(_comms_spec)
_comms_spec.loader.exec_module(_comms_module)
CommsAdapter = _comms_module.CommsAdapter


def test_get_bearer_health_uses_bridge_status(monkeypatch):
    bridge_module = ModuleType("services.comms.bearer_bridge")

    class FakeBridge:
        def get_status(self):
            return [
                {
                    "type": "SATCOM",
                    "status": "operational",
                    "signal": 90,
                    "latency": 100,
                }
            ]

    bridge_module.BearerBridge = FakeBridge
    monkeypatch.setitem(sys.modules, "services.comms.bearer_bridge", bridge_module)

    data = CommsAdapter().get_bearer_health()
    assert data["bearers"][0]["type"] == "SATCOM"
    assert "updatedAt" in data


def test_get_bearer_health_returns_fallback_on_failure(monkeypatch):
    bridge_module = ModuleType("services.comms.bearer_bridge")

    class BadBridge:
        def __init__(self):
            raise RuntimeError("bridge unavailable")

    bridge_module.BearerBridge = BadBridge
    monkeypatch.setitem(sys.modules, "services.comms.bearer_bridge", bridge_module)

    data = CommsAdapter().get_bearer_health()
    assert len(data["bearers"]) == 4
    assert data["bearers"][0]["type"] == "SATCOM"
    assert "updatedAt" in data


def test_get_degradation_advice_uses_tactical_orchestrator(monkeypatch):
    captured = {}

    orchestrator_module = ModuleType("src.llm_core.orchestrator")
    engine_registry_module = ModuleType("src.llm_core.engine_registry")

    class QueryRequest:
        def __init__(self, prompt, domain, max_tokens):
            self.prompt = prompt
            self.domain = domain
            self.max_tokens = max_tokens

    class Orchestrator:
        def query(self, req):
            captured["prompt"] = req.prompt
            captured["domain"] = req.domain
            captured["max_tokens"] = req.max_tokens
            return {"text": "Shift non-critical traffic to delayed queue."}

    class TaskDomain:
        TACTICAL = "TACTICAL"

    orchestrator_module.QueryRequest = QueryRequest
    orchestrator_module.Orchestrator = Orchestrator
    engine_registry_module.TaskDomain = TaskDomain

    monkeypatch.setitem(sys.modules, "src.llm_core.orchestrator", orchestrator_module)
    monkeypatch.setitem(
        sys.modules, "src.llm_core.engine_registry", engine_registry_module
    )

    data = CommsAdapter().get_degradation_advice({"HF": {"status": "degraded"}})
    assert data["advice"] == "Shift non-critical traffic to delayed queue."
    assert data["engine"] == "phi3-medium"
    assert "updatedAt" in data
    assert "Given bearer status:" in captured["prompt"]
    assert captured["domain"] == "TACTICAL"
    assert captured["max_tokens"] == 256


def test_get_degradation_advice_returns_fallback_on_failure(monkeypatch):
    orchestrator_module = ModuleType("src.llm_core.orchestrator")
    engine_registry_module = ModuleType("src.llm_core.engine_registry")

    class QueryRequest:
        def __init__(self, prompt, domain, max_tokens):
            self.prompt = prompt
            self.domain = domain
            self.max_tokens = max_tokens

    class BrokenOrchestrator:
        def query(self, req):
            raise RuntimeError("orchestrator unavailable")

    class TaskDomain:
        TACTICAL = "TACTICAL"

    orchestrator_module.QueryRequest = QueryRequest
    orchestrator_module.Orchestrator = BrokenOrchestrator
    engine_registry_module.TaskDomain = TaskDomain

    monkeypatch.setitem(sys.modules, "src.llm_core.orchestrator", orchestrator_module)
    monkeypatch.setitem(
        sys.modules, "src.llm_core.engine_registry", engine_registry_module
    )

    data = CommsAdapter().get_degradation_advice({"LTE": {"status": "offline"}})
    assert data["advice"] == "Switch to HF as primary. Queue non-critical traffic."
    assert "updatedAt" in data

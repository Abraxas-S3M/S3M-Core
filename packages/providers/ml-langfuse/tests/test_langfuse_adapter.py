from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.ml-langfuse.adapter")
    config_mod = importlib.import_module("packages.providers.ml-langfuse.config")
    return adapter_mod.LangfuseAdapter, config_mod.LangfuseConfig


def test_manifest_correct() -> None:
    Adapter, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "ml-langfuse"
    assert m.tier.value == "FREE"
    assert m.auth_type == "api_key"
    assert m.required_env_vars == ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
    assert m.optional_env_vars == ["LANGFUSE_HOST"]


def test_trace_categories_defined() -> None:
    _, Config = _load()
    assert len(Config().trace_categories) == 9


def test_model_performance_all_engines() -> None:
    Adapter, _ = _load()
    perf = Adapter(mode="airgapped").get_model_performance()
    for model in ["Phi-3", "Grok", "Mistral", "ALLaM"]:
        assert model in perf["models"]


def test_daily_metrics_structure() -> None:
    Adapter, _ = _load()
    metrics = Adapter(mode="airgapped").get_daily_metrics(7)
    assert "days" in metrics
    assert len(metrics["days"]) == 7
    assert {"date", "calls", "tokens", "avg_latency_ms", "errors"}.issubset(metrics["days"][0].keys())


def test_category_breakdown_structure() -> None:
    Adapter, _ = _load()
    payload = Adapter(mode="airgapped").get_category_breakdown()
    assert "categories" in payload
    first = payload["categories"][0]
    assert {"category", "calls", "avg_latency_ms", "errors"}.issubset(first.keys())


def test_llm_health_all_engines() -> None:
    Adapter, _ = _load()
    health = Adapter(mode="airgapped").get_llm_health()
    assert set(health["engines"].keys()) == {"Phi-3", "Grok", "Mistral", "ALLaM"}


def test_fetch_airgapped() -> None:
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").fetch({"action": "metrics", "days": 7})
    assert "days" in out

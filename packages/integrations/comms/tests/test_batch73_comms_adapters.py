from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


CASES = [
    ("prosody", "ProsodyAdapter", "prosody", "prosody"),
    ("mxbridge", "MxbridgeAdapter", "mxbridge", "mxbridge"),
    ("libsignal", "LibsignalAdapter", "libsignal", "libsignal"),
    (
        "arabic-summarization-with-arabert",
        "ArabicSummarizationWithArabertAdapter",
        "arabic-summarization-with-arabert",
        "arabic-summarization-with-araBert",
    ),
    (
        "nlp-arabic-text-summarization-using-arab",
        "NlpArabicTextSummarizationAdapter",
        "nlp-arabic-text-summarization-using-arab",
        "NLP-Arabic-text-summarization-using-araBART",
    ),
]


def _load_adapter(slug: str, class_name: str):
    adapter_path = Path(__file__).resolve().parents[1] / slug / "adapter.py"
    module_name = f"s3m_comms_{slug.replace('-', '_')}_adapter_under_test"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(("slug", "class_name", "integration_id", "manifest_name"), CASES)
def test_manifest_metadata_is_loaded(
    slug: str,
    class_name: str,
    integration_id: str,
    manifest_name: str,
) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == integration_id
    assert manifest.name == manifest_name
    assert manifest.domain == "comms"
    assert manifest.license == "Unknown"


@pytest.mark.parametrize(("slug", "class_name", "_integration_id", "_manifest_name"), CASES)
def test_validate_availability_true_in_airgapped_mode(
    slug: str,
    class_name: str,
    _integration_id: str,
    _manifest_name: str,
) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "integration_id", "_manifest_name"), CASES)
def test_execute_returns_fixture_when_airgapped(
    slug: str,
    class_name: str,
    integration_id: str,
    _manifest_name: str,
) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    response = adapter_cls(mode="airgapped").execute({"operation": "self_test"})
    assert response["source"] == "fixture"
    assert response["integration_id"] == integration_id
    assert response["mode"] == "airgapped"
    assert isinstance(response["result"], dict)

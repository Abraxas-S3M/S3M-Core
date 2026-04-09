from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("module_path", "class_name", "slug", "sample_key"),
    [
        (
            "packages.integrations.interop.open-dis-javascript.adapter",
            "OpenDisJavascriptAdapter",
            "open-dis-javascript",
            "entity_state",
        ),
        (
            "packages.integrations.interop.c2simgui-references-in-openc2sim.adapter",
            "C2simguireferencesInOpenc2simAdapter",
            "c2simgui-references-in-openc2sim",
            "dashboard",
        ),
        (
            "packages.integrations.interop.patternfly-mission-control-examples.adapter",
            "PatternflymissionControlExamplesAdapter",
            "patternfly-mission-control-examples",
            "dashboard_state",
        ),
        (
            "packages.integrations.interop.clermont.adapter",
            "ClermontAdapter",
            "clermont",
            "display",
        ),
        (
            "packages.integrations.interop.defense-solutions-proofs-of-concept.adapter",
            "DefenseSolutionsProofsOfAdapter",
            "defense-solutions-proofs-of-concept",
            "cop_layer",
        ),
    ],
)
def test_interop_adapter_airgapped_contract(
    module_path: str, class_name: str, slug: str, sample_key: str
) -> None:
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)

    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "interop"
    assert manifest.license == "Unknown"

    assert adapter.validate_availability() is True

    response = adapter.execute({"operation": "health_probe"})
    assert response["source"] == "fixture"
    assert response["integration_id"] == slug
    assert sample_key in response["result"]

from __future__ import annotations

import json
from pathlib import Path

from src.catalog.dataset_catalog import (
    load_saudi_mod_scenario_domains,
    validate_catalog,
)


def test_load_saudi_mod_scenario_domains_has_expected_count() -> None:
    domains = load_saudi_mod_scenario_domains()
    assert len(domains) == 28
    assert "risk_readiness" in domains
    assert "cop_intel" in domains
    assert "urban_asymmetric_hybrid" in domains
    assert "cyber_electronic_warfare" in domains
    assert "logistics_sustainment" in domains
    assert "bilingual" in domains


def test_validate_catalog_success() -> None:
    result = validate_catalog("catalog/datasets/saudi_mod.v1.json")
    assert result.is_valid
    assert result.total_records >= 11
    assert not result.errors


def test_validate_catalog_rejects_invalid_domain(tmp_path: Path) -> None:
    bad_catalog = tmp_path / "bad_catalog.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "bad-001",
                        "name": "Bad Dataset",
                        "description": "Has invalid domain",
                        "r2_prefix": "datasets/bad/",
                        "formats": ["jsonl"],
                        "source": "test",
                        "provenance": "test fixture",
                        "geography": "global",
                        "language": "english",
                        "temporal_coverage": "2020-2021",
                        "operational_domains": ["intelligence"],
                        "supported_scenario_domains": ["not_a_real_domain"],
                        "supported_training_tracks": ["saudi_mod"],
                        "supported_packet_types": ["cop_intel"],
                        "parser_status": "planned",
                        "embedding_status": "planned",
                        "data_sensitivity": "unclassified",
                        "source_reliability": "medium",
                        "update_frequency": "monthly",
                        "artifact_outputs_supported": ["intel_digest"],
                        "target_artifact_rooms": ["room-intel-cop"],
                        "routing_priority": 50,
                        "enabled": True,
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = validate_catalog(bad_catalog)
    assert not result.is_valid
    assert any("unsupported scenario domains" in error for error in result.errors)


def test_validate_catalog_rejects_invalid_enabled_type(tmp_path: Path) -> None:
    bad_catalog = tmp_path / "bad_enabled.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "bad-002",
                        "name": "Bad Enabled",
                        "description": "enabled is not boolean",
                        "r2_prefix": "datasets/bad/",
                        "formats": ["json"],
                        "source": "test",
                        "provenance": "test fixture",
                        "geography": "global",
                        "language": "english",
                        "temporal_coverage": "2020-2021",
                        "operational_domains": ["intelligence"],
                        "supported_scenario_domains": ["cop_intel"],
                        "supported_training_tracks": ["saudi_mod"],
                        "supported_packet_types": ["cop_intel"],
                        "parser_status": "planned",
                        "embedding_status": "planned",
                        "data_sensitivity": "unclassified",
                        "source_reliability": "high",
                        "update_frequency": "weekly",
                        "artifact_outputs_supported": ["intel_digest"],
                        "target_artifact_rooms": ["room-intel-cop"],
                        "routing_priority": 25,
                        "enabled": "true",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = validate_catalog(bad_catalog)
    assert not result.is_valid
    assert any("enabled must be boolean" in error for error in result.errors)

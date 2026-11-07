"""Structured planning schema validation."""

from __future__ import annotations

from src.integrations.lechonk.planning_schema import coa_options_from_text, validate_planning_payload


def test_validate_structured_coa_json() -> None:
    raw = (
        '{"coa_options":[{"option_id":"a","name":"Alpha","description":"Hold",'
        '"risk":"low","confidence":0.6}],"watch_priorities":["track ID"]}'
    )
    payload, errors = validate_planning_payload(raw)
    assert errors == []
    assert payload is not None
    assert payload.coa_options[0].name == "Alpha"


def test_invalid_json_fails_closed() -> None:
    payload, errors = validate_planning_payload("not json")
    assert payload is None
    assert "structured_json_missing" in errors or "structured_json_invalid" in errors


def test_coa_wraps_plain_text_when_unstructured() -> None:
    coa, warnings = coa_options_from_text("Maintain passive watch.", live=True)
    assert coa[0]["description"] == "Maintain passive watch."
    assert warnings

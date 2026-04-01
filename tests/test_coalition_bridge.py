"""Unit tests for coalition personnel bridge."""

from __future__ import annotations

from apps.readiness.coalition_bridge import CoalitionPersonnelBridge


def test_register_partner_personnel_from_uae() -> None:
    bridge = CoalitionPersonnelBridge()
    count = bridge.register_partner_personnel(
        223,
        [{"member_id": "uae-1", "name": "Ali", "certifications": ["UAS_OPERATOR"]}],
    )
    assert count == 1


def test_get_coalition_roster_filters_partner() -> None:
    bridge = CoalitionPersonnelBridge()
    bridge.register_partner_personnel(223, [{"member_id": "uae-1"}])
    bridge.register_partner_personnel(117, [{"member_id": "kwt-1"}])
    roster = bridge.get_coalition_roster(partner_code=223)
    assert len(roster) == 1
    assert roster[0]["member_id"] == "uae-1"


def test_check_interoperability_identifies_gaps() -> None:
    bridge = CoalitionPersonnelBridge()
    bridge.register_partner_personnel(
        223,
        [{"member_id": "uae-1", "certifications": ["UAS_OPERATOR"]}],
    )
    out = bridge.check_interoperability("uae-1", ["UAV_OPERATOR", "S3M_CYBER_DEFENDER"])
    assert out["compatible"] is False
    assert "S3M_CYBER_DEFENDER" in out["gaps"]


def test_get_coalition_readiness_returns_combined_strength() -> None:
    bridge = CoalitionPersonnelBridge()
    bridge.register_partner_personnel(223, [{"member_id": "uae-1"}])
    bridge.register_partner_personnel(117, [{"member_id": "kwt-1"}])
    out = bridge.get_coalition_readiness()
    assert out["combined_strength"] == 2
    assert "partners" in out

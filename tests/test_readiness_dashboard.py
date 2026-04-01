"""Tests for readiness dashboard provider."""

from __future__ import annotations

from apps.readiness.manager import ReadinessManager


def test_get_readiness_overview_returns_expected_keys():
    mgr = ReadinessManager()
    mgr.create_saudi_battalion()
    overview = mgr.get_readiness_overview()
    expected = {
        "total_personnel",
        "deployable",
        "deployable_pct",
        "by_branch",
        "by_rank_group",
        "by_status",
        "units",
        "expiring_certs_30d",
        "expired_certs",
        "critical_vacancies",
        "overall_readiness",
        "readiness_level",
        "coalition_partners",
    }
    assert expected.issubset(set(overview.keys()))


def test_get_unit_detail_returns_roster_and_manning_and_readiness():
    mgr = ReadinessManager()
    batch = mgr.create_saudi_battalion()
    detail = mgr.get_unit_detail(batch["unit"])
    assert "roster" in detail
    assert "manning_table" in detail
    assert "readiness_score" in detail


def test_get_manning_board_returns_units():
    mgr = ReadinessManager()
    mgr.create_saudi_battalion()
    board = mgr.dashboard_provider.get_manning_board()
    assert isinstance(board, list)
    assert board
    assert "fill_rate" in board[0]

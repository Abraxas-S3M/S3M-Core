from datetime import datetime, timezone

from apps.simulation.models import (
    AdversaryProfile,
    WargameConfig,
    WargameResult,
    WargameSession,
    WargameTurn,
)
from apps.simulation.wargaming.llm_adversary import LLMAdversary


def test_wargame_config_creation():
    cfg = WargameConfig(
        wargame_id="wg-1",
        name="Test",
        description="desc",
        wargame_type="tactical",
        scenario_id=None,
        blue_force_id="blue",
        red_force_id="red",
        turn_limit=10,
        turn_duration_seconds=30.0,
        llm_adversary=True,
        adversary_difficulty="competent",
        rules_of_engagement="tight",
        victory_conditions=[{"type": "eliminate", "target": "red", "threshold_pct": 75}],
        parameters={},
    )
    assert cfg.to_dict()["wargame_id"] == "wg-1"


def test_wargame_turn_to_dict():
    turn = WargameTurn(
        turn_number=1,
        timestamp=datetime.now(timezone.utc),
        blue_orders=[],
        red_orders=[],
        events=[],
        state_snapshot={"units": []},
        blue_losses=0,
        red_losses=0,
    )
    data = turn.to_dict()
    assert data["turn_number"] == 1
    assert "timestamp" in data


def test_wargame_result_summary():
    result = WargameResult(
        wargame_id="wg-1",
        turns_played=5,
        duration_seconds=300,
        outcome="blue_victory",
        blue_score=80,
        red_score=30,
        blue_losses_total=3,
        red_losses_total=8,
        objectives_met=["obj1"],
        objectives_failed=[],
        key_decisions=[],
        llm_aar=None,
        lessons_learned=[],
        performance_score=88,
    )
    assert "outcome" in result.summary()


def test_wargame_session_is_active():
    cfg = WargameConfig(
        wargame_id="wg-1",
        name="Test",
        description="desc",
        wargame_type="tactical",
        scenario_id=None,
        blue_force_id="blue",
        red_force_id="red",
        turn_limit=10,
        turn_duration_seconds=30.0,
        llm_adversary=True,
        adversary_difficulty="competent",
        rules_of_engagement="tight",
        victory_conditions=[],
        parameters={},
    )
    session = WargameSession(session_id="s1", config=cfg, status="setup", current_turn=0)
    assert session.is_active() is True
    session.status = "completed"
    assert session.is_active() is False


def test_adversary_profile_prebuilt():
    adv = LLMAdversary()
    profiles = adv.get_profiles()
    assert len(profiles) >= 4
    assert isinstance(profiles[0], AdversaryProfile)

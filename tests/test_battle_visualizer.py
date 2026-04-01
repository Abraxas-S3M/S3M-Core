from datetime import datetime, timezone

from apps.simulation.battle_visualizer import BattleVisualizer
from apps.simulation.models import WargameConfig, WargameResult, WargameSession, WargameTurn


def _session():
    cfg = WargameConfig(
        wargame_id="wg",
        name="n",
        description="d",
        wargame_type="tactical",
        scenario_id=None,
        blue_force_id="b",
        red_force_id="r",
        turn_limit=5,
        turn_duration_seconds=30,
        llm_adversary=True,
        adversary_difficulty="competent",
        rules_of_engagement="tight",
        victory_conditions=[],
        parameters={},
    )
    turn = WargameTurn(
        turn_number=1,
        timestamp=datetime.now(timezone.utc),
        blue_orders=[],
        red_orders=[],
        events=[
            {"type": "movement", "unit_id": "blue-1", "from": (0, 0), "to": (5, 0)},
            {"type": "engagement", "attacker": "blue-1", "defender": "red-1", "position": (5, 0), "result": "attacker_wins"},
        ],
        state_snapshot={"units": [{"unit_id": "blue-1", "allegiance": "blue", "type": "infantry", "position": (5, 0), "health": 1.0}]},
        blue_losses=0,
        red_losses=1,
    )
    session = WargameSession(session_id="s1", config=cfg, status="completed", current_turn=1, turns=[turn])
    return session


def test_generate_turn_frame_contains_fields():
    v = BattleVisualizer()
    frame = v.generate_turn_frame(_session().turns[0], bounds={"min_x": 0, "min_y": 0, "max_x": 100, "max_y": 100})
    assert "units" in frame and "engagements" in frame and "movements" in frame


def test_generate_replay_matches_turn_count():
    v = BattleVisualizer()
    session = _session()
    replay = v.generate_replay(session)
    assert len(replay) == len(session.turns)


def test_generate_summary_map_has_traces():
    v = BattleVisualizer()
    session = _session()
    result = WargameResult(
        wargame_id="wg",
        turns_played=1,
        duration_seconds=30,
        outcome="blue_victory",
        blue_score=80,
        red_score=20,
        blue_losses_total=0,
        red_losses_total=1,
        objectives_met=[],
        objectives_failed=[],
        key_decisions=[],
        llm_aar=None,
        lessons_learned=[],
        performance_score=80,
    )
    summary = v.generate_summary_map(result, session)
    assert "movement_traces" in summary

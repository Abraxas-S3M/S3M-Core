from apps.simulation.models import WargameConfig
from apps.simulation.wargaming.turn_resolver import TurnResolver


def _config():
    return WargameConfig(
        wargame_id="wg",
        name="t",
        description="d",
        wargame_type="tactical",
        scenario_id=None,
        blue_force_id="b",
        red_force_id="r",
        turn_limit=10,
        turn_duration_seconds=30,
        llm_adversary=True,
        adversary_difficulty="competent",
        rules_of_engagement="tight",
        victory_conditions=[{"type": "eliminate", "target": "red", "threshold_pct": 100}],
        parameters={"terrain": "desert"},
    )


def _state():
    return {
        "turn": 0,
        "terrain": "desert",
        "initial_counts": {"blue": 1, "red": 1},
        "units": [
            {"unit_id": "blue-1", "allegiance": "blue", "position": (0.0, 0.0), "health": 1.0, "size": 30, "condition": 1.0},
            {"unit_id": "red-1", "allegiance": "red", "position": (20.0, 0.0), "health": 1.0, "size": 10, "condition": 1.0},
        ],
    }


def test_movement_unit_moves_toward_target():
    resolver = TurnResolver()
    turn = resolver.resolve(
        [{"unit_id": "blue-1", "action": "move", "target": (50.0, 0.0)}],
        [],
        _state(),
        _config(),
    )
    blue = [u for u in turn.state_snapshot["units"] if u["unit_id"] == "blue-1"][0]
    assert blue["position"][0] > 0


def test_engagement_three_to_one_defender_destroyed():
    resolver = TurnResolver()
    out = resolver.compute_engagement(
        {"size": 30, "condition": 1.0, "health": 1.0},
        {"size": 10, "condition": 1.0, "health": 1.0},
        "desert",
    )
    assert out["defender_losses"] >= 5


def test_engagement_one_to_one_both_damaged():
    resolver = TurnResolver()
    out = resolver.compute_engagement(
        {"size": 10, "condition": 1.0, "health": 1.0},
        {"size": 10, "condition": 1.0, "health": 1.0},
        "desert",
    )
    assert out["attacker_losses"] >= 1
    assert out["defender_losses"] >= 1


def test_ambush_multiplier_applied():
    resolver = TurnResolver()
    out = resolver.compute_engagement(
        {"size": 10, "condition": 1.0, "health": 1.0, "ambush_ready": True},
        {"size": 10, "condition": 1.0, "health": 1.0},
        "desert",
    )
    assert out["defender_losses"] >= 1


def test_fortification_bonus_applied():
    resolver = TurnResolver()
    out = resolver.compute_engagement(
        {"size": 10, "condition": 1.0, "health": 1.0},
        {"size": 10, "condition": 1.0, "health": 1.0, "fortified": True},
        "urban",
    )
    assert out["attacker_losses"] >= 1


def test_check_victory_elimination_detected():
    resolver = TurnResolver()
    state = {"units": [{"unit_id": "blue-1", "allegiance": "blue", "size": 1, "health": 1.0}], "initial_counts": {"blue": 1, "red": 1}}
    out = resolver.check_victory(state, [{"type": "eliminate", "target": "red", "threshold_pct": 100}])
    assert out == "blue_victory"


def test_terrain_modifiers_affect_results():
    resolver = TurnResolver()
    desert = resolver.compute_engagement({"size": 10, "condition": 1.0, "health": 1.0}, {"size": 10, "condition": 1.0, "health": 1.0}, "desert")
    mountain = resolver.compute_engagement({"size": 10, "condition": 1.0, "health": 1.0}, {"size": 10, "condition": 1.0, "health": 1.0}, "mountain")
    assert desert != mountain

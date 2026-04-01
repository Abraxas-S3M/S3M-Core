from apps.simulation.models import WargameConfig
from apps.simulation.wargaming.wargame_engine import WargameEngine
from apps.simulation.wargaming.wargame_suite import WargameSuite


def _config():
    return WargameConfig(
        wargame_id="wg-test",
        name="Engine Test",
        description="desc",
        wargame_type="tactical",
        scenario_id=None,
        blue_force_id="blue",
        red_force_id="red",
        turn_limit=5,
        turn_duration_seconds=30,
        llm_adversary=True,
        adversary_difficulty="competent",
        rules_of_engagement="tight",
        victory_conditions=[{"type": "eliminate", "target": "red", "threshold_pct": 100}],
        parameters={"blue_units": 3, "red_units": 3},
    )


def test_create_session_setup_status():
    engine = WargameEngine()
    session = engine.create_session(_config())
    assert session.status == "setup"


def test_submit_blue_orders_advances_turn():
    engine = WargameEngine()
    session = engine.create_session(_config())
    state = engine.get_state(session.session_id)
    blue_orders = [{"unit_id": u["unit_id"], "action": "move", "target": (50.0, 0.0)} for u in state["units"] if u["allegiance"] == "blue"]
    turn = engine.submit_blue_orders(session.session_id, blue_orders)
    assert turn["turn_number"] == 1


def test_complete_generates_result():
    engine = WargameEngine()
    session = engine.create_session(_config())
    state = engine.get_state(session.session_id)
    blue_orders = [{"unit_id": u["unit_id"], "action": "attack", "target": (100.0, 0.0)} for u in state["units"] if u["allegiance"] == "blue"]
    engine.submit_blue_orders(session.session_id, blue_orders)
    result = engine.complete(session.session_id)
    assert result.performance_score >= 0
    assert result.llm_aar is not None


def test_quick_wargame_runs_to_completion():
    suite = WargameSuite()
    result = suite.quick_wargame("Quick", 3, 3, turns=5)
    assert result.turns_played >= 1


def test_llm_adversary_generates_red_orders():
    engine = WargameEngine()
    session = engine.create_session(_config())
    state = engine.get_state(session.session_id)
    blue_orders = [{"unit_id": u["unit_id"], "action": "move", "target": (50.0, 0.0)} for u in state["units"] if u["allegiance"] == "blue"]
    turn = engine.submit_blue_orders(session.session_id, blue_orders)
    assert isinstance(turn["red_orders"], list)

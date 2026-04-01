from apps.simulation.wargaming.llm_adversary import LLMAdversary


def _state():
    return {
        "terrain": "desert",
        "units": [
            {"unit_id": "blue-1", "allegiance": "blue", "position": (0.0, 0.0), "health": 1.0},
            {"unit_id": "red-1", "allegiance": "red", "position": (100.0, 0.0), "health": 1.0},
            {"unit_id": "red-2", "allegiance": "red", "position": (110.0, 10.0), "health": 1.0},
        ],
        "last_turn_events": [],
    }


def test_scripted_fallback_competent_produces_orders():
    adv = LLMAdversary()
    adv.profile.difficulty = "competent"
    orders = adv.decide(_state(), {}, 1)
    assert isinstance(orders, list)
    assert len(orders) >= 1


def test_each_difficulty_varies_behavior():
    adv = LLMAdversary()
    actions = {}
    for difficulty in ["novice", "competent", "expert", "grandmaster"]:
        adv.profile.difficulty = difficulty
        orders = adv.decide(_state(), {}, 1)
        actions[difficulty] = {o["action"] for o in orders}
    assert actions["novice"] != actions["grandmaster"] or actions["competent"] != actions["expert"]


def test_decide_required_keys():
    adv = LLMAdversary()
    orders = adv.decide(_state(), {}, 1)
    assert orders
    for order in orders:
        assert {"unit_id", "action", "target", "reasoning"}.issubset(order.keys())


def test_get_profiles_has_at_least_four():
    adv = LLMAdversary()
    assert len(adv.get_profiles()) >= 4

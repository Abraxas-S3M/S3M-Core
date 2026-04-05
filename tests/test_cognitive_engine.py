"""Tests for S3M Unified Cognitive Engine (Batch 1)."""

from src.cognitive.unified_cognitive_engine import UnifiedCognitiveEngine
from src.cognitive.world_model import BayesianWorldModel, WorldHypothesis, WorldObservation, CausalLink
from src.cognitive.multi_objective_resolver import MultiObjectiveResolver


def test_cognitive_engine_basic_think_cycle():
    engine = UnifiedCognitiveEngine()
    engine.initialize({"safe": 0.5, "threatened": 0.3, "engaged": 0.2})
    engine.register_actions(["advance", "hold", "retreat", "engage", "evade"])
    engine.register_dynamics(
        transitions={
            "safe": {
                "advance": {"safe": 0.6, "threatened": 0.3, "engaged": 0.1},
                "hold": {"safe": 0.8, "threatened": 0.15, "engaged": 0.05},
                "retreat": {"safe": 0.9, "threatened": 0.1, "engaged": 0.0},
                "engage": {"safe": 0.3, "threatened": 0.4, "engaged": 0.3},
                "evade": {"safe": 0.7, "threatened": 0.2, "engaged": 0.1},
            },
            "threatened": {
                "advance": {"safe": 0.2, "threatened": 0.4, "engaged": 0.4},
                "hold": {"safe": 0.3, "threatened": 0.5, "engaged": 0.2},
                "retreat": {"safe": 0.6, "threatened": 0.3, "engaged": 0.1},
                "engage": {"safe": 0.1, "threatened": 0.3, "engaged": 0.6},
                "evade": {"safe": 0.5, "threatened": 0.3, "engaged": 0.2},
            },
            "engaged": {
                "advance": {"safe": 0.1, "threatened": 0.2, "engaged": 0.7},
                "hold": {"safe": 0.1, "threatened": 0.3, "engaged": 0.6},
                "retreat": {"safe": 0.4, "threatened": 0.4, "engaged": 0.2},
                "engage": {"safe": 0.2, "threatened": 0.2, "engaged": 0.6},
                "evade": {"safe": 0.3, "threatened": 0.4, "engaged": 0.3},
            },
        },
        rewards={
            "safe": {"advance": 5.0, "hold": 2.0, "retreat": -1.0, "engage": -2.0, "evade": 0.0},
            "threatened": {"advance": -1.0, "hold": 0.0, "retreat": 3.0, "engage": 1.0, "evade": 4.0},
            "engaged": {"advance": -3.0, "hold": -1.0, "retreat": 4.0, "engage": 2.0, "evade": 5.0},
        },
    )

    cycle = engine.think(
        observations=[
            {
                "hypothesis_likelihoods": {"safe": 0.3, "threatened": 0.8, "engaged": 0.1},
                "source_weight": 0.9,
            }
        ]
    )

    assert cycle.decision is not None
    assert cycle.decision.selected_action in ["advance", "hold", "retreat", "engage", "evade"]
    assert 0.0 <= cycle.decision.confidence <= 1.0
    assert cycle.elapsed_ms > 0
    assert len(cycle.decision.rationale_en) > 0
    assert len(cycle.decision.rationale_ar) > 0


def test_cognitive_engine_roe_filtering():
    engine = UnifiedCognitiveEngine()
    engine.initialize({"safe": 0.2, "engaged": 0.8})
    engine.register_actions(["engage", "hold", "retreat"])
    engine.register_dynamics(
        transitions={
            "safe": {
                "engage": {"safe": 0.5, "engaged": 0.5},
                "hold": {"safe": 0.8, "engaged": 0.2},
                "retreat": {"safe": 0.9, "engaged": 0.1},
            },
            "engaged": {
                "engage": {"safe": 0.3, "engaged": 0.7},
                "hold": {"safe": 0.2, "engaged": 0.8},
                "retreat": {"safe": 0.6, "engaged": 0.4},
            },
        },
        rewards={
            "safe": {"engage": -2.0, "hold": 1.0, "retreat": 0.0},
            "engaged": {"engage": 3.0, "hold": -1.0, "retreat": 2.0},
        },
    )
    engine.set_roe({"roe_level": "weapons_hold"})
    cycle = engine.think(observations=[])
    assert cycle.decision is not None
    assert cycle.decision.selected_action != "engage"


def test_cognitive_belief_convergence():
    engine = UnifiedCognitiveEngine()
    engine.initialize({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    engine.register_actions(["act"])
    engine.register_dynamics(
        transitions={
            "A": {"act": {"A": 1.0}},
            "B": {"act": {"B": 1.0}},
            "C": {"act": {"C": 1.0}},
            "D": {"act": {"D": 1.0}},
        },
        rewards={"A": {"act": 1.0}, "B": {"act": 1.0}, "C": {"act": 1.0}, "D": {"act": 1.0}},
    )

    for _ in range(10):
        engine.think(
            observations=[
                {
                    "hypothesis_likelihoods": {"A": 0.9, "B": 0.1, "C": 0.05, "D": 0.05},
                    "source_weight": 0.8,
                }
            ]
        )

    assert engine.get_concentration() > 0.5
    belief = engine.get_belief()
    assert belief.get("A", 0.0) > belief.get("B", 0.0)


def test_world_model_causal_propagation():
    world_model = BayesianWorldModel()
    world_model.add_hypothesis(WorldHypothesis(hypothesis_id="h1", label="Enemy nearby", prior=0.3))
    world_model.add_hypothesis(WorldHypothesis(hypothesis_id="h2", label="Threat level high", prior=0.2))
    world_model.add_causal_link(CausalLink(source_id="h1", target_id="h2", strength=0.8))

    updated = world_model.observe(
        WorldObservation(
            affected_hypotheses={"h1": 0.9},
            source_reliability=0.85,
        )
    )

    assert "h1" in updated
    assert "h2" in updated
    state = world_model.get_state()
    assert state.hypotheses["h1"].posterior > 0.3


def test_multi_objective_conflict_detection():
    resolver = MultiObjectiveResolver()
    result = resolver.resolve(
        q_values={"advance": 0.7, "retreat": 0.5, "engage": 0.8, "hold": 0.3},
        objectives={"survival": 0.4, "mission_progress": 0.4},
        belief={"safe": 0.3, "threatened": 0.7},
    )
    assert "adjusted_q" in result
    assert "conflicts" in result
    assert "pareto_front" in result
    assert len(result["adjusted_q"]) > 0

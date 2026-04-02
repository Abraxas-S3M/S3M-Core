"""Tests for Chunk 4: Pattern Memory.

Proves:
  1. Default doctrinal motifs register correctly
  2. Lookup returns relevant motifs for matching traits
  3. Lookup filters by entity type
  4. Similarity scoring differentiates good from poor matches
  5. Motif transition prediction returns ranked next-states
  6. Recording observations increases confidence
  7. Empty / missing traits handled gracefully
"""

import sys

sys.path.insert(0, ".")

from src.prediction.pattern_memory import PatternMemory


# =====================================================================
# Test 1: Default motifs register
# =====================================================================


def test_default_motifs_register() -> None:
    mem = PatternMemory()
    count = mem.register_defaults()
    assert count == 9, f"Expected 9 defaults, got {count}"
    assert mem.count() == 9

    # Tactical assurance: core doctrinal motifs must all be available.
    for name in [
        "loiter",
        "probe",
        "approach",
        "disperse",
        "regroup",
        "intermittent_signal",
        "route_deviation",
        "withdraw",
        "strike_run",
    ]:
        motif = mem.get(name)
        assert motif is not None, f"Motif '{name}' not found"
        assert motif.name == name
        assert motif.signature, f"Motif '{name}' has empty signature"
        assert motif.transitions, f"Motif '{name}' has empty transition table"
        assert motif.confidence > 0
        assert motif.observation_count > 0

    stats = mem.stats()
    assert stats["total_motifs"] == 9
    assert stats["total_observations"] > 100


# =====================================================================
# Test 2: Lookup returns relevant motifs
# =====================================================================


def test_lookup_returns_relevant_motifs() -> None:
    mem = PatternMemory()
    mem.register_defaults()

    # Traits that match "loiter": low speed, high heading variance, stable altitude.
    loiter_traits = {
        "speed_range_mps": 3.0,
        "heading_variance_deg": 120.0,
        "altitude_stable": True,
    }
    results = mem.lookup(loiter_traits, entity_type="aircraft", top_k=3)
    assert len(results) >= 1, "Should find at least 1 motif for loiter traits"

    # Best match should be "loiter".
    best = results[0]
    assert best.motif.name == "loiter", f"Expected 'loiter' as best match, got '{best.motif.name}'"
    assert best.similarity_score > 0.5, f"Loiter similarity should be >0.5, got {best.similarity_score}"
    assert best.effective_score > 0
    assert len(best.matched_features) >= 1

    # Traits that match "approach": moderate speed, low heading variance, closing.
    approach_traits = {
        "speed_range_mps": 25.0,
        "heading_variance_deg": 5.0,
        "closing": True,
    }
    results2 = mem.lookup(approach_traits, entity_tags={"hostile"}, top_k=3)
    assert len(results2) >= 1
    names = [r.motif.name for r in results2]
    assert "approach" in names, f"Expected 'approach' in results, got {names}"


# =====================================================================
# Test 3: Lookup filters by entity type
# =====================================================================


def test_lookup_filters_by_type() -> None:
    mem = PatternMemory()
    mem.register_defaults()

    # "loiter" is applicable to aircraft and vessel.
    loiter_traits = {"speed_range_mps": 3.0, "heading_variance_deg": 120.0, "altitude_stable": True}

    aircraft_results = mem.lookup(loiter_traits, entity_type="aircraft", top_k=5)
    infantry_results = mem.lookup(loiter_traits, entity_type="infantry", top_k=5)

    # Tactical typing prevents maritime/air motifs from leaking into infantry assessment.
    aircraft_names = {r.motif.name for r in aircraft_results}
    infantry_names = {r.motif.name for r in infantry_results}

    assert "loiter" in aircraft_names, "Loiter should match aircraft"
    assert "loiter" not in infantry_names, "Loiter should not match infantry (type filter)"


# =====================================================================
# Test 4: Similarity scoring differentiates matches
# =====================================================================


def test_similarity_differentiates() -> None:
    mem = PatternMemory()
    mem.register_defaults()

    # Perfect loiter traits.
    perfect = {"speed_range_mps": 3.0, "heading_variance_deg": 120.0, "altitude_stable": True}
    perfect_results = mem.lookup(perfect, entity_type="aircraft", top_k=1)

    # Poor loiter traits (high speed, low variance = not loitering).
    poor = {"speed_range_mps": 50.0, "heading_variance_deg": 2.0, "altitude_stable": False}
    poor_results = mem.lookup(poor, entity_type="aircraft", top_k=5)

    # Perfect match should score higher than poor match for loiter.
    perfect_loiter = next((r for r in perfect_results if r.motif.name == "loiter"), None)
    poor_loiter = next((r for r in poor_results if r.motif.name == "loiter"), None)

    if perfect_loiter and poor_loiter:
        assert perfect_loiter.similarity_score > poor_loiter.similarity_score, (
            f"Perfect loiter ({perfect_loiter.similarity_score}) should > poor ({poor_loiter.similarity_score})"
        )
    elif perfect_loiter and not poor_loiter:
        pass  # poor traits didn't match loiter at all, which is correct
    else:
        raise AssertionError("Perfect loiter traits should match the loiter motif")


# =====================================================================
# Test 5: Transition prediction
# =====================================================================


def test_transition_prediction() -> None:
    mem = PatternMemory()
    mem.register_defaults()

    # Loiter -> what comes next?
    transitions = mem.predict_transitions("loiter", top_k=5)
    assert len(transitions) >= 3, f"Expected >=3 transitions from loiter, got {len(transitions)}"

    names = [t.to_motif for t in transitions]
    assert "approach" in names, "Loiter should transition to approach"

    # Probabilities should be sorted descending.
    probs = [t.probability for t in transitions]
    assert probs == sorted(probs, reverse=True), "Transitions should be sorted by probability"

    # Sum should be approximately 1.0 for this full top-5 loiter table.
    total_p = sum(t.probability for t in transitions)
    assert abs(total_p - 1.0) < 0.05, f"Transition probabilities sum to {total_p}, expected ~1.0"

    # Strike_run should heavily favor withdraw.
    strike_transitions = mem.predict_transitions("strike_run", top_k=3)
    assert len(strike_transitions) >= 1
    assert strike_transitions[0].to_motif == "withdraw", (
        f"Strike_run should transition to withdraw first, got {strike_transitions[0].to_motif}"
    )

    # Serialization
    d = transitions[0].to_dict()
    assert "from" in d and "to" in d and "probability" in d


# =====================================================================
# Test 6: Recording observations
# =====================================================================


def test_record_observation() -> None:
    mem = PatternMemory()
    mem.register_defaults()

    loiter = mem.get("loiter")
    assert loiter is not None
    initial_count = loiter.observation_count
    initial_conf = loiter.confidence

    loiter.record_observation(confidence_boost=0.05)
    assert loiter.observation_count == initial_count + 1
    assert loiter.confidence > initial_conf
    assert loiter.confidence <= 0.99


# =====================================================================
# Test 7: Graceful handling of empty traits
# =====================================================================


def test_empty_traits_handled() -> None:
    mem = PatternMemory()
    mem.register_defaults()

    # Empty traits
    results = mem.lookup({}, entity_type="aircraft", top_k=5)
    assert isinstance(results, list)
    for r in results:
        assert r.similarity_score >= 0
        assert r.effective_score >= 0

    # Nonexistent motif transition
    transitions = mem.predict_transitions("nonexistent_motif")
    assert transitions == []

    # Nonexistent get
    assert mem.get("nonexistent") is None


if __name__ == "__main__":
    test_default_motifs_register()
    test_lookup_returns_relevant_motifs()
    test_lookup_filters_by_type()
    test_similarity_differentiates()
    test_transition_prediction()
    test_record_observation()
    test_empty_traits_handled()
    print("All Pattern Memory tests passed")

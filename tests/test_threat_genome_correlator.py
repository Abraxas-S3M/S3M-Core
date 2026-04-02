"""Tests for Chunk 2: Threat Genome Correlation and Evolution Engine."""

import sys
sys.path.insert(0, ".")

from src.threat_genome.models import (
    BehavioralSignature,
    CapabilityProfile,
    PlatformType,
    SignatureType,
    ThreatGenome,
    TTP,
    TTPPhase,
)
from src.threat_genome.genome_store import GenomeStore
from src.fusion.threat_genome_correlator import ThreatGenomeCorrelator


def _build_store_with_houthi():
    store = GenomeStore()
    genome = ThreatGenome(
        actor_name="Houthi Drone Program",
        actor_type="non-state",
        regions_of_activity=["Yemen", "Saudi Arabia", "Red Sea"],
        threat_rating="high",
        confidence=0.7,
        tags={"drone", "uav", "yemen", "houthi", "asymmetric"},
    )
    genome.add_ttp(TTP(
        mitre_id="T1595", name="Active Scanning",
        phase=TTPPhase.RECONNAISSANCE, confidence=0.8,
    ))
    genome.add_ttp(TTP(
        name="Low-altitude UAV approach",
        phase=TTPPhase.KINETIC_MANEUVER, confidence=0.85,
    ))
    genome.add_signature(BehavioralSignature(
        signature_type=SignatureType.TEMPORAL,
        name="Dawn launch window",
        pattern_parameters={"active_hours": [3, 4, 5]},
        confidence=0.7, specificity=0.6,
    ))
    genome.add_signature(BehavioralSignature(
        signature_type=SignatureType.MOVEMENT,
        name="Southern approach vector",
        pattern_parameters={
            "approach_bearing_range": [170, 190],
            "speed_range_mps": [15, 25],
        },
        confidence=0.75, specificity=0.7,
    ))
    genome.add_signature(BehavioralSignature(
        signature_type=SignatureType.COMMUNICATION,
        name="Freq-hopping C2",
        pattern_parameters={"freq_ghz": 2.4, "burst_interval_s": 2.0, "freq_hopping": True},
        confidence=0.65, specificity=0.8,
    ))
    genome.set_capabilities(CapabilityProfile(
        platforms=[PlatformType.FIXED_WING_UAV, PlatformType.LOITERING_MUNITION],
        cyber_capabilities=["c2_uplink", "gps_spoofing"],
        confidence=0.7,
    ))
    store.add_genome(genome)
    return store, genome


def _houthi_like_observation():
    from src.fusion.threat_genome_correlator import GenomeObservation

    return GenomeObservation(
        source_type="sensor_fusion",
        source_id="radar-station-05",
        latitude=24.71, longitude=46.68,
        extracted_signature_features={
            "approach_bearing_range": 180,
            "speed_range_mps": 20,
        },
        comms_features={
            "freq_ghz": 2.4,
            "burst_interval_s": 2.1,
            "freq_hopping": True,
        },
        cyber_features={"capabilities": ["c2_uplink"]},
        behavior_tags=["drone", "uav", "low_altitude", "houthi"],
        ttp_hints=[
            {"mitre_id": "T1595", "name": "Active Scanning",
             "phase": "reconnaissance", "confidence": 0.7},
        ],
        raw_confidence=0.75,
        classification="hostile_uav",
        threat_level="high",
        regions=["Saudi Arabia"],
    )


def _unrelated_observation():
    from src.fusion.threat_genome_correlator import GenomeObservation

    return GenomeObservation(
        source_type="cyber",
        source_id="siem-cluster",
        cyber_features={"capabilities": ["ransomware", "data_exfil", "spearphish"]},
        behavior_tags=["apt", "espionage", "corporate", "zero_day"],
        raw_confidence=0.65,
        classification="apt_intrusion",
        threat_level="critical",
        regions=["Europe"],
    )


def test_observation_matches_existing_genome():
    store, houthi = _build_store_with_houthi()
    initial_obs_count = houthi.observation_count
    correlator = ThreatGenomeCorrelator(store, match_threshold=0.20)
    obs = _houthi_like_observation()
    verdict = correlator.correlate(obs)

    assert verdict.decision == "matched", \
        f"Expected 'matched', got '{verdict.decision}' (score={verdict.composite_score:.3f})"
    assert verdict.matched_genome_id == houthi.genome_id
    assert verdict.matched_genome_name == "Houthi Drone Program"
    assert verdict.composite_score >= correlator.match_threshold
    assert verdict.confidence_after >= verdict.confidence_before
    assert len(verdict.components_updated) >= 1
    updated = store.get_genome(houthi.genome_id)
    assert updated is not None
    assert updated.observation_count > initial_obs_count
    print("PASS: Observation correctly matches existing genome")


def test_observation_creates_new_genome():
    store, _ = _build_store_with_houthi()
    correlator = ThreatGenomeCorrelator(store, match_threshold=0.30)
    obs = _unrelated_observation()
    verdict = correlator.correlate(obs)

    assert verdict.decision == "created", \
        f"Expected 'created', got '{verdict.decision}' (score={verdict.composite_score:.3f})"
    assert verdict.created_genome_id is not None
    assert verdict.composite_score < correlator.match_threshold
    assert store.count() == 2
    new_genome = store.get_genome(verdict.created_genome_id)
    assert new_genome is not None
    assert "apt" in new_genome.tags or "espionage" in new_genome.tags
    print("PASS: Unmatched observation creates new genome")


def test_conflicting_evidence_lowers_score():
    from src.fusion.threat_genome_correlator import GenomeObservation

    store, _ = _build_store_with_houthi()
    correlator = ThreatGenomeCorrelator(store, match_threshold=0.15)
    perfect = _houthi_like_observation()
    verdict_perfect = correlator.correlate(perfect)

    store2, _ = _build_store_with_houthi()
    correlator2 = ThreatGenomeCorrelator(store2, match_threshold=0.15)
    conflicting = GenomeObservation(
        source_type="sensor_fusion",
        extracted_signature_features={
            "approach_bearing_range": 350,
            "speed_range_mps": 80,
        },
        comms_features={
            "freq_ghz": 5.8,
            "burst_interval_s": 10.0,
            "freq_hopping": False,
        },
        behavior_tags=["drone", "uav", "houthi"],
        raw_confidence=0.7,
        classification="hostile_uav",
        regions=["Saudi Arabia"],
    )
    verdict_conflict = correlator2.correlate(conflicting)

    def _gate(v, name):
        for g in v.gate_scores:
            if g.gate_name == name:
                return g.raw_score
        return 0.0

    if verdict_perfect.gate_scores and verdict_conflict.gate_scores:
        assert _gate(verdict_conflict, "signature") <= _gate(verdict_perfect, "signature")
        assert _gate(verdict_conflict, "comms") <= _gate(verdict_perfect, "comms")
    print("PASS: Conflicting evidence produces lower correlation score")


def test_merge_preserves_provenance():
    store = GenomeStore()
    g_a = ThreatGenome(
        actor_name="Drone Cell Alpha", actor_type="non-state",
        regions_of_activity=["Yemen"], confidence=0.7, tags={"drone", "alpha"},
    )
    g_a.add_ttp(TTP(mitre_id="T1595", name="Active Scanning",
                     phase=TTPPhase.RECONNAISSANCE, confidence=0.8))
    g_a.add_signature(BehavioralSignature(
        signature_type=SignatureType.TEMPORAL, name="Dawn ops",
        pattern_parameters={"active_hours": [3, 4, 5]}, confidence=0.7,
    ))
    store.add_genome(g_a)

    g_b = ThreatGenome(
        actor_name="Drone Cell Beta", actor_type="non-state",
        regions_of_activity=["Saudi Arabia"], confidence=0.6, tags={"drone", "beta"},
    )
    g_b.add_ttp(TTP(mitre_id="T1583", name="Acquire Infrastructure",
                     phase=TTPPhase.RESOURCE_DEVELOPMENT, confidence=0.7))
    g_b.add_signature(BehavioralSignature(
        signature_type=SignatureType.MOVEMENT, name="Low alt approach",
        pattern_parameters={"speed_range_mps": [15, 25]}, confidence=0.75,
    ))
    store.add_genome(g_b)
    assert store.count() == 2

    correlator = ThreatGenomeCorrelator(store)
    merge_record = correlator.merge(
        g_a.genome_id, g_b.genome_id,
        reason="Analyst assessed same actor based on C2 correlation"
    )
    assert merge_record.store_result is not None
    assert merge_record.store_result["components_absorbed"] >= 2
    assert "Drone Cell Beta" in merge_record.explanation
    assert "Drone Cell Alpha" in merge_record.explanation
    assert store.count() == 1

    survivor = store.get_genome(g_a.genome_id)
    assert survivor is not None
    assert "Drone Cell Beta" in survivor.actor_aliases
    assert len(survivor.ttps) >= 2
    assert len(survivor.signatures) >= 2
    assert "saudi arabia" in survivor.regions
    assert "beta" in survivor.tags
    assert survivor.confidence >= 0.7

    merge_evos = [e for e in survivor.evolution_log if e.change_type == "genome_merged"]
    assert len(merge_evos) >= 1
    print("PASS: Merge preserves provenance, aliases, and history")


def test_scoring_explanation_generated():
    store, _ = _build_store_with_houthi()
    correlator = ThreatGenomeCorrelator(store, match_threshold=0.15)
    obs = _houthi_like_observation()
    verdict = correlator.correlate(obs)

    assert len(verdict.gate_scores) == 6
    gate_names = {g.gate_name for g in verdict.gate_scores}
    assert gate_names == {"temporal", "geo", "signature", "comms", "cyber", "tags"}
    for gate in verdict.gate_scores:
        assert gate.explanation, f"Gate '{gate.gate_name}' has empty explanation"
        assert 0.0 <= gate.raw_score <= 1.0
        assert gate.weight > 0
    assert verdict.explanation
    assert len(verdict.explanation) > 20
    d = verdict.to_dict()
    assert len(d["gate_scores"]) == 6
    print("PASS: Every verdict has per-gate explanations")


def test_sequential_evolution():
    from src.fusion.threat_genome_correlator import GenomeObservation

    store, houthi = _build_store_with_houthi()
    correlator = ThreatGenomeCorrelator(store, match_threshold=0.15)
    initial_ttp_count = len(houthi.ttps)
    initial_confidence = houthi.confidence

    correlator.correlate(GenomeObservation(
        source_type="osint",
        behavior_tags=["drone", "uav", "houthi", "swarm"],
        ttp_hints=[{"name": "GPS spoofing", "phase": "electronic_warfare", "confidence": 0.6}],
        raw_confidence=0.7, regions=["Yemen"],
    ))
    correlator.correlate(GenomeObservation(
        source_type="sigint",
        comms_features={"freq_ghz": 2.4, "burst_interval_s": 2.0, "freq_hopping": True},
        behavior_tags=["drone", "uav", "houthi"],
        ttp_hints=[{"mitre_id": "T1595", "name": "Active Scanning",
                     "phase": "reconnaissance", "confidence": 0.8}],
        raw_confidence=0.8, regions=["Saudi Arabia"],
    ))
    correlator.correlate(GenomeObservation(
        source_type="cyber",
        cyber_features={"capabilities": ["c2_uplink", "gps_spoofing", "freq_hopping_c2"]},
        behavior_tags=["drone", "houthi", "c2"],
        raw_confidence=0.65,
    ))

    evolved = store.get_genome(houthi.genome_id)
    assert evolved is not None
    assert len(evolved.ttps) >= initial_ttp_count
    assert evolved.confidence >= initial_confidence
    assert "swarm" in evolved.tags
    print("PASS: Sequential observations evolve genome over time")


def test_batch_correlation():
    from src.fusion.threat_genome_correlator import GenomeObservation

    store, _ = _build_store_with_houthi()
    correlator = ThreatGenomeCorrelator(store, match_threshold=0.20)
    observations = [
        _houthi_like_observation(),
        _unrelated_observation(),
        GenomeObservation(
            source_type="osint", behavior_tags=["drone", "unknown"],
            raw_confidence=0.4, classification="unidentified_uav",
        ),
    ]
    verdicts = correlator.correlate_batch(observations)
    assert len(verdicts) == 3
    decisions = [v.decision for v in verdicts]
    assert "matched" in decisions or "created" in decisions
    stats = correlator.stats()
    assert stats["total_correlations"] == 3
    log = correlator.get_verdict_log(last_n=10)
    assert len(log) == 3
    print("PASS: Batch correlation processes multiple observations")


if __name__ == "__main__":
    test_observation_matches_existing_genome()
    test_observation_creates_new_genome()
    test_conflicting_evidence_lowers_score()
    test_merge_preserves_provenance()
    test_scoring_explanation_generated()
    test_sequential_evolution()
    test_batch_correlation()
    print("\nAll Threat Genome Correlator tests passed")

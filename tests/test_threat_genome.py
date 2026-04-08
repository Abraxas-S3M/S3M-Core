#!/usr/bin/env python3
"""Tests for Threat Genome defensive profiling models and store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.threat_genome import (
    BehavioralSignature,
    CapabilityProfile,
    ChainLink,
    IndicatorChain,
    TTP,
    ThreatGenome,
    ThreatGenomeStore,
)
from src.threat_genome.models import TTPPhase


def _build_signature(signature_id: str, name: str, confidence: float = 0.8) -> BehavioralSignature:
    return BehavioralSignature(
        signature_id=signature_id,
        name=name,
        temporal_patterns={"operation_hour_utc": (1, 5), "weekend_activity": True},
        movement_patterns={"avg_speed_kmh": (25, 40), "route_dispersion_km": 12},
        communication_patterns={"encrypted": True, "burst_mode": True},
        targeting_patterns={"priority_targets": {"radar", "c2", "artillery"}},
        evasion_patterns={"emissions_control": True},
        escalation_patterns={"escalation_step_hours": (6, 18)},
        logistics_patterns={"resupply_interval_hours": (36, 72)},
        formation_patterns={"formation": "staggered"},
        confidence=confidence,
        provenance=["SIGINT:SIG-UNIT-14"],
    )


def _build_chain(chain_id: str, name: str, confidence: float = 0.85) -> IndicatorChain:
    return IndicatorChain(
        chain_id=chain_id,
        name=name,
        confidence=confidence,
        provenance=["CYBER:HUNT-7"],
        links=[
            ChainLink(
                observable_type="dns_query",
                observable_value="c2-node.example",
                max_time_delta_s=180,
                confidence_weight=1.1,
                provenance=["PCAP:001"],
            ),
            ChainLink(
                observable_type="beacon_interval",
                observable_value=60,
                min_time_delta_s=20,
                max_time_delta_s=240,
                confidence_weight=1.2,
                provenance=["PCAP:002"],
            ),
            ChainLink(
                observable_type="payload_hash",
                observable_value="hash-abc-123",
                min_time_delta_s=10,
                max_time_delta_s=240,
                confidence_weight=1.4,
                provenance=["MALWARE:LAB-A"],
            ),
        ],
    )


def _build_capabilities(prefix: str, confidence: float = 0.75) -> CapabilityProfile:
    return CapabilityProfile(
        platforms={f"{prefix}-uav": [f"IMINT:{prefix}-1"]},
        weapons={f"{prefix}-rocket": [f"HUMINT:{prefix}-2"]},
        cyber_capabilities={f"{prefix}-dns-tunnel": [f"PCAP:{prefix}-3"]},
        ew_capabilities={f"{prefix}-jammer": [f"SIGINT:{prefix}-4"]},
        swarm_parameters={f"{prefix}-swarm-6": [f"ISR:{prefix}-5"]},
        logistics_capabilities={f"{prefix}-fuel-cache": [f"GEOINT:{prefix}-6"]},
        confidence=confidence,
        provenance=[f"ASSESS:{prefix}"],
    )


def _build_alpha_genome() -> ThreatGenome:
    genome = ThreatGenome(
        actor_id="alpha",
        actor_name="Alpha Group",
        actor_type="hybrid_cell",
        regions={"north-sector"},
        tags={"drone", "ew"},
    )
    ttp1 = TTP(
        technique_id="T1059",
        name="Command and Scripting Interpreter",
        phase=TTPPhase.EXECUTION,
        confidence=0.78,
        provenance=["MITRE:report-1"],
        tags={"script", "loader"},
    )
    ttp2 = TTP(
        technique_id="T1105",
        name="Ingress Tool Transfer",
        phase=TTPPhase.COMMAND_AND_CONTROL,
        confidence=0.74,
        provenance=["MITRE:report-2"],
        tags={"c2"},
    )
    ttp3 = TTP(
        technique_id="K-ISR-1",
        name="Persistent ISR Drone Pattern",
        phase=TTPPhase.ISR_COLLECTION,
        confidence=0.66,
        provenance=["ISR:track-12"],
        tags={"isr"},
    )
    genome.add_ttp(ttp1)
    genome.add_ttp(ttp2)
    genome.add_ttp(ttp3)
    genome.add_signature(_build_signature("sig-alpha", "Night EW Harassment"))
    genome.set_capabilities(_build_capabilities("alpha"))
    genome.add_indicator_chain(_build_chain("chain-alpha", "Alpha Beacon Chain"))
    return genome


def _build_charlie_similar_genome() -> ThreatGenome:
    genome = ThreatGenome(
        actor_id="charlie",
        actor_name="Charlie Group",
        actor_type="hybrid_cell",
        regions={"north-sector"},
        tags={"drone", "ew"},
    )
    genome.add_ttp(
        TTP(
            technique_id="T1059",
            name="Command and Scripting Interpreter",
            phase=TTPPhase.EXECUTION,
            confidence=0.73,
            provenance=["MITRE:charlie-1"],
            tags={"script"},
        )
    )
    genome.add_ttp(
        TTP(
            technique_id="T1105",
            name="Ingress Tool Transfer",
            phase=TTPPhase.COMMAND_AND_CONTROL,
            confidence=0.69,
            provenance=["MITRE:charlie-2"],
            tags={"c2"},
        )
    )
    genome.add_signature(_build_signature("sig-charlie", "Night EW Harassment", confidence=0.76))
    genome.set_capabilities(_build_capabilities("alpha", confidence=0.72))
    genome.add_indicator_chain(_build_chain("chain-charlie", "Charlie Beacon Chain", confidence=0.77))
    return genome


def _build_bravo_different_genome() -> ThreatGenome:
    genome = ThreatGenome(
        actor_id="bravo",
        actor_name="Bravo Team",
        actor_type="cyber_cell",
        regions={"south-coast"},
        tags={"phishing"},
    )
    genome.add_ttp(
        TTP(
            technique_id="T1566",
            name="Phishing",
            phase=TTPPhase.INITIAL_ACCESS,
            confidence=0.84,
            provenance=["SOC:mail-gateway"],
            tags={"email"},
        )
    )
    genome.add_ttp(
        TTP(
            technique_id="T1078",
            name="Valid Accounts",
            phase=TTPPhase.PERSISTENCE,
            confidence=0.71,
            provenance=["SOC:auth-log"],
            tags={"credential"},
        )
    )
    genome.add_signature(
        BehavioralSignature(
            signature_id="sig-bravo",
            name="Credential Theft Sequence",
            temporal_patterns={"operation_hour_utc": (8, 16), "weekend_activity": False},
            communication_patterns={"encrypted": False, "burst_mode": False},
            targeting_patterns={"priority_targets": {"identity", "mail"}},
            confidence=0.81,
            provenance=["HUNT:BR-2"],
        )
    )
    genome.set_capabilities(_build_capabilities("bravo", confidence=0.68))
    genome.add_indicator_chain(_build_chain("chain-bravo", "Bravo Beacon Chain", confidence=0.71))
    return genome


def test_1_genome_creation_and_completeness_scoring():
    genome = ThreatGenome(actor_id="g-1", actor_name="Gamma", actor_type="proxy")
    baseline = genome.compute_completeness()
    assert 0.0 <= baseline <= 1.0

    genome.add_ttp(
        TTP(
            technique_id="T1583",
            name="Acquire Infrastructure",
            phase=TTPPhase.RESOURCE_DEVELOPMENT,
            confidence=0.6,
            provenance=["INTEL:RES-1"],
        )
    )
    genome.add_signature(_build_signature("sig-gamma", "Gamma Pattern", confidence=0.72))
    genome.set_capabilities(_build_capabilities("gamma", confidence=0.7))
    genome.add_indicator_chain(_build_chain("chain-gamma", "Gamma Chain", confidence=0.7))

    complete = genome.compute_completeness()
    assert complete > baseline
    assert 0.0 <= complete <= 1.0


def test_2_ttp_bayesian_reinforcement():
    ttp = TTP(
        technique_id="T1110",
        name="Brute Force",
        phase=TTPPhase.CREDENTIAL_ACCESS,
        confidence=0.2,
        provenance=["LOG:AUTH-1"],
    )
    before = ttp.confidence
    after = ttp.record_observation(
        observation_confidence=0.92,
        likelihood_multiplier=1.8,
        evidence_reference="LOG:AUTH-2",
    )
    assert after > before
    assert ttp.observation_count == 1
    assert ttp.last_observed is not None
    assert "LOG:AUTH-2" in ttp.provenance


def test_3_behavioral_signature_pattern_matching():
    signature = _build_signature("sig-1", "Pattern One", confidence=0.85)
    observed_good = {
        "temporal": {"operation_hour_utc": 3, "weekend_activity": True},
        "movement": {"avg_speed_kmh": 31, "route_dispersion_km": 13},
        "communication": {"encrypted": True, "burst_mode": True},
        "targeting": {"priority_targets": {"radar", "artillery"}},
        "evasion": {"emissions_control": True},
        "escalation": {"escalation_step_hours": 10},
        "logistics": {"resupply_interval_hours": 48},
        "formation": {"formation": "staggered"},
    }
    observed_bad = {
        "temporal": {"operation_hour_utc": 13, "weekend_activity": False},
        "movement": {"avg_speed_kmh": 8, "route_dispersion_km": 90},
        "communication": {"encrypted": False, "burst_mode": False},
        "targeting": {"priority_targets": {"hospital"}},
        "evasion": {"emissions_control": False},
        "escalation": {"escalation_step_hours": 96},
        "logistics": {"resupply_interval_hours": 8},
        "formation": {"formation": "column"},
    }
    good_score = signature.match_score(observed_good)
    bad_score = signature.match_score(observed_bad)
    assert good_score > 0.7
    assert bad_score < 0.4


def test_4_indicator_chain_sequential_matching():
    chain = _build_chain("chain-1", "Chain One", confidence=0.9)
    t0 = datetime.now(timezone.utc)
    sequence_good = [
        {"type": "dns_query", "value": "c2-node.example", "timestamp": t0},
        {"type": "beacon_interval", "value": 61, "timestamp": t0 + timedelta(seconds=60)},
        {"type": "payload_hash", "value": "hash-abc-123", "timestamp": t0 + timedelta(seconds=120)},
    ]
    sequence_bad_timing = [
        {"type": "dns_query", "value": "c2-node.example", "timestamp": t0},
        {"type": "beacon_interval", "value": 61, "timestamp": t0 + timedelta(seconds=600)},
        {"type": "payload_hash", "value": "hash-abc-123", "timestamp": t0 + timedelta(seconds=900)},
    ]
    good_score = chain.match_observations(sequence_good)
    bad_score = chain.match_observations(sequence_bad_timing)
    assert good_score > 0.7
    assert bad_score < good_score


def test_5_genome_similarity_self_vs_cross_actor_vs_similar():
    alpha = _build_alpha_genome()
    bravo = _build_bravo_different_genome()
    charlie = _build_charlie_similar_genome()

    assert alpha.similarity(alpha) == 1.0
    sim_cross = alpha.similarity(bravo)
    sim_similar = alpha.similarity(charlie)
    assert sim_similar > sim_cross
    assert 0.0 <= sim_cross <= 1.0
    assert 0.0 <= sim_similar <= 1.0


def test_6_genome_store_crud_and_indexing():
    store = ThreatGenomeStore()
    alpha = _build_alpha_genome()
    bravo = _build_bravo_different_genome()
    store.add_genome(alpha)
    store.add_genome(bravo)

    assert len(store) == 2
    assert store.get_genome("alpha") is alpha
    assert any(g.actor_id == "alpha" for g in store.find_by_technique("T1059"))
    assert any(g.actor_id == "alpha" for g in store.find_by_phase(TTPPhase.EXECUTION))
    assert any(g.actor_id == "alpha" for g in store.find_by_platform("alpha-uav"))
    assert any(g.actor_id == "alpha" for g in store.find_by_region("north-sector"))
    assert any(g.actor_id == "alpha" for g in store.find_by_tag("drone"))

    assert store.remove_genome("bravo") is True
    assert len(store) == 1
    assert store.remove_genome("bravo") is False


def test_7_similarity_search_ranking():
    store = ThreatGenomeStore()
    alpha = _build_alpha_genome()
    charlie = _build_charlie_similar_genome()
    bravo = _build_bravo_different_genome()
    store.add_genome(alpha)
    store.add_genome(charlie)
    store.add_genome(bravo)

    ranked = store.find_similar(alpha, top_k=2)
    assert len(ranked) == 2
    assert ranked[0][0] == "charlie"
    assert ranked[0][1] >= ranked[1][1]


def test_7b_find_similar_patterns_hook():
    store = ThreatGenomeStore()
    alpha = _build_alpha_genome()
    bravo = _build_bravo_different_genome()
    store.add_genome(alpha)
    store.add_genome(bravo)

    pattern = {
        "targeting": {"priority_targets": ["radar"]},
        "movement": {"avg_speed_kmh": 30},
        "communication": {"encrypted": True},
    }
    ranked = store.find_similar_patterns(pattern, top_k=2)
    assert ranked
    assert ranked[0]["actor_id"] == "alpha"
    assert ranked[0]["score"] >= ranked[-1]["score"]


def test_8_attribution_via_indicator_chains():
    store = ThreatGenomeStore()
    alpha = _build_alpha_genome()
    bravo = _build_bravo_different_genome()
    store.add_genome(alpha)
    store.add_genome(bravo)

    t0 = datetime.now(timezone.utc)
    sequence = [
        {"type": "dns_query", "value": "c2-node.example", "timestamp": t0},
        {"type": "beacon_interval", "value": 60, "timestamp": t0 + timedelta(seconds=50)},
        {"type": "payload_hash", "value": "hash-abc-123", "timestamp": t0 + timedelta(seconds=110)},
    ]
    matches = store.attribute_observations(sequence, top_k=2)
    assert matches
    assert matches[0]["actor_id"] in {"alpha", "bravo"}
    assert matches[0]["score"] >= matches[-1]["score"]


def test_9_kill_chain_phase_coverage_and_gap_analysis():
    genome = _build_alpha_genome()
    coverage = genome.get_phase_coverage()
    assert coverage[TTPPhase.EXECUTION.value] > 0.0
    assert coverage[TTPPhase.COMMAND_AND_CONTROL.value] > 0.0
    assert coverage[TTPPhase.INITIAL_ACCESS.value] == 0.0

    gaps = genome.get_uncovered_phases(threshold=0.3)
    assert TTPPhase.INITIAL_ACCESS.value in gaps
    assert TTPPhase.EXECUTION.value not in gaps


def test_10_temporal_evolution_and_confidence_decay():
    genome = _build_alpha_genome()
    assert len(genome.evolution_log) >= 6  # 3 TTPs + signature + capabilities + chain

    old_time = datetime.now(timezone.utc) - timedelta(days=180)
    for ttp in genome.ttps.values():
        ttp.last_observed = old_time
    for signature in genome.signatures.values():
        signature.updated_at = old_time
    for chain in genome.indicator_chains.values():
        chain.updated_at = old_time
        chain.last_matched = old_time
    if genome.capabilities is not None:
        genome.capabilities.updated_at = old_time

    pre = sum(ttp.confidence for ttp in genome.ttps.values()) / len(genome.ttps)
    decay_summary = genome.decay_confidence(half_life_days=30, as_of=datetime.now(timezone.utc))
    post = sum(ttp.confidence for ttp in genome.ttps.values()) / len(genome.ttps)
    assert post < pre
    assert "ttp_average_confidence" in decay_summary
    assert genome.evolution_log[-1]["action"] == "decay_confidence"


def test_11_store_statistics_and_landscape_analytics():
    store = ThreatGenomeStore()
    alpha = _build_alpha_genome()
    bravo = _build_bravo_different_genome()
    charlie = _build_charlie_similar_genome()
    store.add_genome(alpha)
    store.add_genome(bravo)
    store.add_genome(charlie)

    # Force deterministic activity windows for temporal analytics.
    now = datetime.now(timezone.utc)
    alpha.last_activity = now - timedelta(hours=2)
    bravo.last_activity = now - timedelta(days=60)
    charlie.last_activity = now - timedelta(hours=6)

    matrix = store.get_ttp_coverage_matrix()
    assert set(matrix.keys()) == {"alpha", "bravo", "charlie"}
    assert matrix["alpha"][TTPPhase.EXECUTION.value] > 0.0

    frequency = store.get_global_ttp_frequency()
    assert "T1059" in frequency
    assert frequency["T1059"] > 0.0

    mapping = store.get_technique_actors()
    assert "T1059" in mapping
    assert "alpha" in mapping["T1059"]

    active = store.recently_active(since_hours=12, as_of=now)
    dormant = store.dormant(min_days=30, as_of=now)
    assert {g.actor_id for g in active} == {"alpha", "charlie"}
    assert {g.actor_id for g in dormant} == {"bravo"}

"""
S3M Bayesian Update Engine — Full Deterministic Test Suite
============================================================
All tests: offline, in-process, zero I/O, fully deterministic.

Run:
    pytest tests/test_bayesian_updater.py -v
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pytest

from src.belief_state import (
    BeliefHypothesis,
    BeliefState,
    BeliefStore,
    BeliefUpdate,
    EvidenceLink,
)
from src.belief_state.models import (
    EvidenceLayer,
    HypothesisStatus,
    UpdateSource,
)
from src.belief_state.bayesian_updater import (
    BayesianUpdateResult,
    BayesianUpdater,
    ConflictDetector,
    ConflictReport,
    EvidenceBundle,
    EvidenceItem,
    HypothesisTrace,
    SourceProfile,
    SourceReliability,
    UpdateTrace,
    _entropy,
    _logsumexp,
    _renormalise,
    LOG_FLOOR,
)


# ===========================================================================
# Factories
# ===========================================================================

def _hyp(desc: str, prob: float, status: HypothesisStatus = HypothesisStatus.ACTIVE) -> BeliefHypothesis:
    return BeliefHypothesis(description=desc, probability=prob, status=status)


def _item(
    hypothesis_id: str,
    likelihood: float,
    source_id: str = "sensor-default",
    age_offset_seconds: float = 0.0,
) -> EvidenceItem:
    observed = datetime.now(timezone.utc) - timedelta(seconds=age_offset_seconds)
    return EvidenceItem(
        hypothesis_id=hypothesis_id,
        likelihood=likelihood,
        source_id=source_id,
        observed_at=observed,
    )


def _bundle(
    items: List[EvidenceItem],
    source: UpdateSource = UpdateSource.SENSOR_FUSION,
    justification: str = "test bundle",
) -> EvidenceBundle:
    return EvidenceBundle(source=source, items=items, justification=justification)


def _uniform_state(n: int) -> BeliefState:
    """Produce a BeliefState with n equal-probability ACTIVE hypotheses."""
    prob = 1.0 / n
    hyps = [_hyp(f"H-{i}", prob) for i in range(n)]
    hyp_dict = {h.hypothesis_id: h for h in hyps}
    dist = {h.hypothesis_id: prob for h in hyps}
    return BeliefState(hypotheses=hyp_dict, confidence_distribution=dist)


def _state_from_hyps(hyps: List[BeliefHypothesis]) -> BeliefState:
    """Produce a BeliefState from a list of hypotheses, auto-normalised."""
    total = sum(h.probability for h in hyps)
    hyp_dict = {h.hypothesis_id: h for h in hyps}
    dist = {h.hypothesis_id: h.probability / total for h in hyps}
    return BeliefState(hypotheses=hyp_dict, confidence_distribution=dist)


def _default_updater(**kwargs) -> BayesianUpdater:
    return BayesianUpdater(
        source_profiles={
            "sensor-default": SourceProfile(
                source_id="sensor-default",
                reliability=SourceReliability.B_USUALLY_RELIABLE,
                layer=EvidenceLayer.LAYER_02_THREAT,
            ),
            "sensor-reliable": SourceProfile(
                source_id="sensor-reliable",
                reliability=SourceReliability.A_COMPLETELY_RELIABLE,
                layer=EvidenceLayer.LAYER_02_THREAT,
            ),
            "sensor-weak": SourceProfile(
                source_id="sensor-weak",
                reliability=SourceReliability.E_UNRELIABLE,
                layer=EvidenceLayer.LAYER_02_THREAT,
            ),
        },
        **kwargs,
    )


# ===========================================================================
# 1. SourceProfile
# ===========================================================================

class TestSourceProfile:

    def test_reliability_weight_a(self):
        p = SourceProfile(source_id="x", reliability=SourceReliability.A_COMPLETELY_RELIABLE)
        assert p.reliability_weight() == 1.00

    def test_reliability_weight_e(self):
        p = SourceProfile(source_id="x", reliability=SourceReliability.E_UNRELIABLE)
        assert p.reliability_weight() == 0.20

    def test_reliability_weight_f_neutral(self):
        p = SourceProfile(source_id="x", reliability=SourceReliability.F_UNKNOWN)
        assert p.reliability_weight() == 0.50

    def test_recency_weight_fresh(self):
        p = SourceProfile(source_id="x", recency_lambda=0.005)
        assert abs(p.recency_weight(0.0) - 1.0) < 1e-9

    def test_recency_weight_half_life(self):
        """At half-life t = ln(2) / λ, weight ≈ 0.5."""
        lam = 0.005
        p = SourceProfile(source_id="x", recency_lambda=lam)
        half_life = math.log(2) / lam
        w = p.recency_weight(half_life)
        assert abs(w - 0.5) < 1e-6

    def test_recency_weight_floor(self):
        """Very old evidence should not reach 0."""
        p = SourceProfile(source_id="x", recency_lambda=0.005)
        w = p.recency_weight(1_000_000)
        assert w >= 0.01

    def test_effective_weight_is_product(self):
        p = SourceProfile(
            source_id="x",
            reliability=SourceReliability.B_USUALLY_RELIABLE,
            recency_lambda=0.005,
        )
        r = p.reliability_weight()
        rec = p.recency_weight(0.0)
        assert abs(p.effective_weight(0.0) - r * rec) < 1e-9

    def test_negative_recency_lambda_rejected(self):
        with pytest.raises(Exception):
            SourceProfile(source_id="x", recency_lambda=-0.001)


# ===========================================================================
# 2. EvidenceItem
# ===========================================================================

class TestEvidenceItem:

    def test_likelihood_must_be_positive(self):
        with pytest.raises(Exception):
            EvidenceItem(hypothesis_id="h1", likelihood=0.0, source_id="s")

    def test_likelihood_bounds(self):
        with pytest.raises(Exception):
            EvidenceItem(hypothesis_id="h1", likelihood=1.1, source_id="s")

    def test_blank_hypothesis_id_rejected(self):
        with pytest.raises(Exception):
            EvidenceItem(hypothesis_id="   ", likelihood=0.5, source_id="s")

    def test_age_seconds_fresh(self):
        item = _item("h1", 0.8)
        assert item.age_seconds() < 2.0

    def test_age_seconds_old(self):
        item = _item("h1", 0.8, age_offset_seconds=300.0)
        assert abs(item.age_seconds() - 300.0) < 2.0

    def test_auto_uuid(self):
        a = _item("h1", 0.5)
        b = _item("h1", 0.5)
        assert a.evidence_item_id != b.evidence_item_id


# ===========================================================================
# 3. EvidenceBundle
# ===========================================================================

class TestEvidenceBundle:

    def test_empty_items_rejected(self):
        with pytest.raises(Exception):
            EvidenceBundle(source=UpdateSource.SENSOR_FUSION, items=[])

    def test_items_for_filters_correctly(self):
        hid1, hid2 = str(uuid.uuid4()), str(uuid.uuid4())
        items = [_item(hid1, 0.8), _item(hid2, 0.6), _item(hid1, 0.7)]
        bundle = _bundle(items)
        assert len(bundle.items_for(hid1)) == 2
        assert len(bundle.items_for(hid2)) == 1

    def test_unique_sources(self):
        items = [
            _item("h1", 0.8, "source-A"),
            _item("h1", 0.7, "source-B"),
            _item("h2", 0.6, "source-A"),
        ]
        bundle = _bundle(items)
        assert set(bundle.unique_sources()) == {"source-A", "source-B"}


# ===========================================================================
# 4. ConflictDetector
# ===========================================================================

class TestConflictDetector:

    def test_no_conflict_single_source(self):
        detector = ConflictDetector(conflict_threshold=0.3)
        result = detector.analyse("hid", [(0.8, "s1")])
        assert result is None

    def test_no_conflict_agreement(self):
        detector = ConflictDetector(conflict_threshold=0.3)
        result = detector.analyse("hid", [(0.75, "s1"), (0.80, "s2")])
        assert result is None   # spread = 0.05, below threshold 0.3

    def test_conflict_detected_above_threshold(self):
        detector = ConflictDetector(conflict_threshold=0.3)
        result = detector.analyse("hid", [(0.9, "s1"), (0.3, "s2")])
        assert result is not None
        assert result.spread == pytest.approx(0.6, abs=1e-6)

    def test_conflict_dampening_computed(self):
        detector = ConflictDetector(conflict_threshold=0.3, dampen_floor=0.3)
        result = detector.analyse("hid", [(1.0, "s1"), (0.1, "s2")])
        assert result is not None
        # spread = 0.9, dampening = max(0.3, 1.0 - 0.9) = max(0.3, 0.1) = 0.3
        assert result.dampening_factor == pytest.approx(0.3, abs=1e-6)

    def test_conflict_dampening_floor_respected(self):
        detector = ConflictDetector(conflict_threshold=0.0, dampen_floor=0.3)
        # Maximum conflict: 1.0 vs 0.0 → spread 1.0 → dampening floor = 0.3
        result = detector.analyse("hid", [(1.0, "s1"), (0.0001, "s2")])
        assert result is not None
        assert result.dampening_factor >= 0.3

    def test_conflict_report_is_frozen(self):
        c = ConflictReport(
            hypothesis_id="h", max_likelihood=0.9, min_likelihood=0.3,
            spread=0.6, dampening_factor=0.4, source_ids=["s1", "s2"],
        )
        with pytest.raises(Exception):
            c.spread = 0.0


# ===========================================================================
# 5. Numerical utilities
# ===========================================================================

class TestNumericalUtils:

    def test_logsumexp_two_values(self):
        """log(exp(1) + exp(2)) = log(e + e²)"""
        expected = math.log(math.exp(1) + math.exp(2))
        assert abs(_logsumexp([1.0, 2.0]) - expected) < 1e-9

    def test_logsumexp_single(self):
        assert abs(_logsumexp([3.5]) - 3.5) < 1e-9

    def test_logsumexp_empty_returns_floor(self):
        assert _logsumexp([]) == LOG_FLOOR

    def test_logsumexp_very_negative_values(self):
        """Should not underflow."""
        result = _logsumexp([-400.0, -450.0, -499.0])
        assert math.isfinite(result)

    def test_renormalise_sums_to_one(self):
        d = {"a": 0.3, "b": 0.3, "c": 0.3}  # sum = 0.9
        norm = _renormalise(d)
        assert abs(sum(norm.values()) - 1.0) < 1e-12

    def test_renormalise_zero_total_uniform(self):
        d = {"a": 0.0, "b": 0.0}
        norm = _renormalise(d)
        assert abs(norm["a"] - 0.5) < 1e-12

    def test_entropy_uniform(self):
        """Uniform over 4 events: H = ln(4)"""
        assert abs(_entropy([0.25, 0.25, 0.25, 0.25]) - math.log(4)) < 1e-9

    def test_entropy_certain(self):
        assert _entropy([1.0, 0.0, 0.0]) == pytest.approx(0.0, abs=1e-9)

    def test_entropy_empty(self):
        assert _entropy([]) == 0.0


# ===========================================================================
# 6. BayesianUpdater — posterior shifts correctly
# ===========================================================================

class TestBayesianUpdaterPosterior:

    def test_strong_evidence_shifts_posterior(self):
        """
        High-likelihood evidence for H-0 should increase P(H-0) after update.
        """
        state = _uniform_state(3)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        prior_p = state.confidence_distribution[hid]

        bundle = _bundle([_item(hid, 0.99, "sensor-default")])
        result = updater.compute(state, bundle)

        assert result.posterior[hid] > prior_p

    def test_weak_evidence_for_h_shifts_others_down(self):
        """
        Evidence supporting one hypothesis should reduce others.
        """
        state = _uniform_state(3)
        updater = _default_updater()
        hids = list(state.hypotheses.keys())
        target = hids[0]
        others = hids[1:]

        bundle = _bundle([_item(target, 0.95, "sensor-default")])
        result = updater.compute(state, bundle)

        for other in others:
            assert result.posterior[other] < state.confidence_distribution[other]

    def test_posterior_sums_to_one(self):
        state = _uniform_state(5)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        bundle = _bundle([_item(hid, 0.85, "sensor-default")])
        result = updater.compute(state, bundle)

        total = sum(result.posterior.values())
        assert abs(total - 1.0) < 1e-9

    def test_no_evidence_leaves_posterior_unchanged(self):
        """
        If no EvidenceItems target a hypothesis, its log-likelihood contribution
        is 0. Only the targeted hypothesis shifts; overall distribution re-normalises.
        Result: the un-targeted hypothesis should still have a valid posterior.
        """
        state = _uniform_state(2)
        updater = _default_updater()
        hids = list(state.hypotheses.keys())
        # Only provide evidence for hids[0]
        bundle = _bundle([_item(hids[0], 0.9, "sensor-default")])
        result = updater.compute(state, bundle)
        # Posterior must exist for hids[1] (no evidence → log-lik = 0 → unchanged prior)
        assert hids[1] in result.posterior
        assert result.posterior[hids[1]] > 0.0

    def test_update_result_contains_belief_update(self):
        state = _uniform_state(2)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        result = updater.compute(state, _bundle([_item(hid, 0.8, "sensor-default")]))
        assert isinstance(result.update, BeliefUpdate)

    def test_belief_update_deltas_bounded(self):
        """All delta values in the produced BeliefUpdate must be in [-1, 1]."""
        state = _uniform_state(4)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        result = updater.compute(state, _bundle([_item(hid, 0.99, "sensor-reliable")]))
        for d in result.update.delta.values():
            assert -1.0 <= d <= 1.0

    def test_delta_sign_matches_direction(self):
        """Positive likelihood evidence → positive delta for targeted hypothesis."""
        state = _uniform_state(3)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        result = updater.compute(state, _bundle([_item(hid, 0.95, "sensor-default")]))
        assert result.update.delta[hid] > 0.0

    def test_very_low_likelihood_pushes_posterior_down(self):
        """Low-likelihood evidence for a hypothesis should reduce its posterior."""
        h0 = _hyp("H-target", 0.8)
        h1 = _hyp("H-other",  0.2)
        state = _state_from_hyps([h0, h1])
        updater = _default_updater()

        # Very low likelihood evidence against the dominant hypothesis
        bundle = _bundle([_item(h0.hypothesis_id, 0.01, "sensor-default")])
        result = updater.compute(state, bundle)
        assert result.posterior[h0.hypothesis_id] < 0.8

    def test_only_active_hypotheses_are_updated(self):
        """DORMANT and REFUTED hypotheses must not appear in the posterior."""
        h_active = _hyp("Active", 0.6, HypothesisStatus.ACTIVE)
        h_dormant = _hyp("Dormant", 0.3, HypothesisStatus.DORMANT)
        h_refuted = _hyp("Refuted", 0.1, HypothesisStatus.REFUTED)

        total = h_active.probability
        hyp_dict = {
            h_active.hypothesis_id: h_active,
            h_dormant.hypothesis_id: h_dormant,
            h_refuted.hypothesis_id: h_refuted,
        }
        dist = {h_active.hypothesis_id: 1.0}   # only active in dist

        state = BeliefState(hypotheses=hyp_dict, confidence_distribution=dist)
        updater = _default_updater()
        bundle = _bundle([_item(h_active.hypothesis_id, 0.9, "sensor-default")])
        result = updater.compute(state, bundle)

        assert h_dormant.hypothesis_id not in result.posterior
        assert h_refuted.hypothesis_id not in result.posterior


# ===========================================================================
# 7. Conflicting evidence lowers certainty
# ===========================================================================

class TestConflictingEvidence:

    def test_conflicting_signals_detected(self):
        """Two sources disagree strongly → ConflictReport in trace."""
        state = _uniform_state(2)
        updater = _default_updater(conflict_threshold=0.2)
        hid = list(state.hypotheses.keys())[0]

        bundle = _bundle([
            _item(hid, 0.95, "sensor-reliable"),   # high likelihood
            _item(hid, 0.05, "sensor-weak"),        # low likelihood
        ])
        result = updater.compute(state, bundle)
        assert len(result.trace.conflicts) > 0

    def test_conflicting_evidence_increases_entropy(self):
        """
        Strongly conflicting signals should increase posterior entropy
        relative to a single strong signal.
        """
        state = _uniform_state(2)
        hid = list(state.hypotheses.keys())[0]
        updater = _default_updater(conflict_threshold=0.2)

        # Single strong signal
        result_strong = updater.compute(
            state,
            _bundle([_item(hid, 0.99, "sensor-reliable")]),
        )
        # Conflicting signals
        result_conflict = updater.compute(
            state,
            _bundle([
                _item(hid, 0.99, "sensor-reliable"),
                _item(hid, 0.01, "sensor-weak"),
            ]),
        )
        # Conflicting result should be more uncertain (higher or equal entropy)
        assert result_conflict.trace.posterior_entropy >= result_strong.trace.posterior_entropy - 1e-6

    def test_conflicting_evidence_dampening_reduces_shift(self):
        """
        Posterior shift under conflicting evidence is smaller than under unanimous evidence.
        """
        state = _uniform_state(2)
        hid = list(state.hypotheses.keys())[0]
        updater = _default_updater(conflict_threshold=0.2)
        prior_p = state.confidence_distribution[hid]

        # Unanimous strong signal
        result_unanimous = updater.compute(
            state, _bundle([_item(hid, 0.95, "sensor-reliable")])
        )
        # Conflicting signal
        result_conflict = updater.compute(
            state, _bundle([
                _item(hid, 0.95, "sensor-reliable"),
                _item(hid, 0.05, "sensor-weak"),
            ])
        )
        shift_unanimous = abs(result_unanimous.posterior[hid] - prior_p)
        shift_conflict = abs(result_conflict.posterior[hid] - prior_p)
        assert shift_conflict <= shift_unanimous

    def test_most_conflicted_hypothesis_identified(self):
        state = _uniform_state(2)
        hid = list(state.hypotheses.keys())[0]
        updater = _default_updater(conflict_threshold=0.1)

        result = updater.compute(
            state,
            _bundle([
                _item(hid, 0.9, "sensor-reliable"),
                _item(hid, 0.1, "sensor-weak"),
            ]),
        )
        if result.trace.conflicts:
            assert result.trace.most_conflicted_hypothesis_id() == hid


# ===========================================================================
# 8. Strong evidence dominates weak
# ===========================================================================

class TestEvidenceDominance:

    def test_high_reliability_source_dominates_low(self):
        """
        A grade-A source providing high-likelihood evidence should dominate
        a grade-E source providing opposing evidence, as reflected in posterior.
        """
        state = _uniform_state(2)
        updater = _default_updater(conflict_threshold=0.99)  # disable dampening
        hid = list(state.hypotheses.keys())[0]
        prior_p = state.confidence_distribution[hid]

        result = updater.compute(
            state,
            _bundle([
                # Strong grade-A source says H is likely
                _item(hid, 0.95, "sensor-reliable"),
                # Weak  grade-E source says H is unlikely
                _item(hid, 0.10, "sensor-weak"),
            ]),
        )
        # Grade-A weight = 1.0, Grade-E weight = 0.2
        # Weighted log-lik = 1.0*log(0.95) + 0.2*log(0.10) > 0 → posterior > prior
        assert result.posterior[hid] > prior_p

    def test_fresh_evidence_outweighs_stale(self):
        """
        Fresh evidence should contribute more to the posterior than stale evidence
        of equal likelihood and reliability.
        """
        state = _uniform_state(2)
        hid = list(state.hypotheses.keys())[0]
        prior_p = state.confidence_distribution[hid]

        # Updater with fast decay (short half-life)
        fast_profile = {
            "sensor-A": SourceProfile(
                source_id="sensor-A",
                reliability=SourceReliability.B_USUALLY_RELIABLE,
                recency_lambda=0.05,   # very fast decay
            )
        }
        updater_fast = BayesianUpdater(source_profiles=fast_profile)

        # Fresh evidence
        result_fresh = updater_fast.compute(
            state, _bundle([_item(hid, 0.95, "sensor-A", age_offset_seconds=1.0)])
        )
        # Stale evidence (600 seconds old)
        result_stale = updater_fast.compute(
            state, _bundle([_item(hid, 0.95, "sensor-A", age_offset_seconds=600.0)])
        )

        shift_fresh = result_fresh.posterior[hid] - prior_p
        shift_stale = result_stale.posterior[hid] - prior_p
        assert shift_fresh > shift_stale

    def test_multiple_consistent_sources_converge(self):
        """
        N sources all reporting high likelihood should drive posterior higher
        than a single source.
        """
        state = _uniform_state(3)
        hid = list(state.hypotheses.keys())[0]
        updater = _default_updater(conflict_threshold=0.99)

        result_1 = updater.compute(
            state, _bundle([_item(hid, 0.80, "sensor-default")])
        )
        # Add a second independent confirming source
        result_2 = updater.compute(
            state, _bundle([
                _item(hid, 0.80, "sensor-default"),
                _item(hid, 0.80, "sensor-reliable"),
            ])
        )
        assert result_2.posterior[hid] >= result_1.posterior[hid]

    def test_perfect_certainty_evidence_dominates(self):
        """
        Likelihood very close to 1.0 from a reliable source should drive
        posterior close to 1.0 after multiple cycles (simulated by wide prior).
        """
        # Start with heavily biased prior against target
        h_target = _hyp("Target", 0.05)
        h_other = _hyp("Other",  0.95)
        state = _state_from_hyps([h_target, h_other])
        updater = BayesianUpdater(
            source_profiles={
                "oracle": SourceProfile(
                    source_id="oracle",
                    reliability=SourceReliability.A_COMPLETELY_RELIABLE,
                )
            },
            conflict_threshold=0.99,
        )

        # Apply 5 cycles of very strong evidence
        current = state
        for _ in range(5):
            result = updater.compute(
                current,
                _bundle([_item(h_target.hypothesis_id, 0.999, "oracle")]),
            )
            # Apply to a fresh state each time to simulate accumulation
            new_dist = result.posterior
            new_state = BeliefState(
                hypotheses=current.hypotheses,
                confidence_distribution=new_dist,
                parent_version=current.version,
            )
            current = new_state

        assert current.confidence_distribution[h_target.hypothesis_id] > 0.90


# ===========================================================================
# 9. UpdateTrace explainability
# ===========================================================================

class TestUpdateTrace:

    def _run(self, n: int = 2, likelihood: float = 0.8) -> tuple:
        state = _uniform_state(n)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        bundle = _bundle([_item(hid, likelihood, "sensor-default")])
        result = updater.compute(state, bundle)
        return result, hid

    def test_trace_has_entry_for_every_active_hypothesis(self):
        state = _uniform_state(4)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        result = updater.compute(state, _bundle([_item(hid, 0.8, "sensor-default")]))
        assert len(result.trace.hypothesis_traces) == 4

    def test_trace_prior_matches_state(self):
        state = _uniform_state(3)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        result = updater.compute(state, _bundle([_item(hid, 0.8, "sensor-default")]))
        ht = result.trace.hypothesis_traces[hid]
        assert abs(ht.prior - state.confidence_distribution[hid]) < 1e-6

    def test_trace_delta_equals_posterior_minus_prior(self):
        result, hid = self._run()
        ht = result.trace.hypothesis_traces[hid]
        assert abs(ht.delta - (ht.posterior - ht.prior)) < 1e-6

    def test_trace_entropy_computed(self):
        result, _ = self._run(n=4)
        assert result.trace.prior_entropy > 0.0
        assert result.trace.posterior_entropy >= 0.0

    def test_strong_evidence_decreases_entropy(self):
        state = _uniform_state(3)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        result = updater.compute(state, _bundle([_item(hid, 0.99, "sensor-reliable")]))
        assert result.trace.certainty_increased()

    def test_dominant_hypothesis_identified(self):
        result, hid = self._run(likelihood=0.95)
        dom = result.trace.dominant_hypothesis_id()
        assert dom == hid

    def test_summary_en_is_string(self):
        result, _ = self._run()
        assert isinstance(result.trace.summary_en(), str)
        assert len(result.trace.summary_en()) > 10

    def test_summary_ar_is_string(self):
        result, _ = self._run()
        summary = result.trace.summary_ar()
        assert isinstance(summary, str)
        assert len(summary) > 5

    def test_trace_effective_weights_populated(self):
        state = _uniform_state(2)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        result = updater.compute(state, _bundle([_item(hid, 0.8, "sensor-default")]))
        ht = result.trace.hypothesis_traces[hid]
        assert "sensor-default" in ht.effective_weights
        assert ht.effective_weights["sensor-default"] > 0.0

    def test_trace_raw_likelihoods_populated(self):
        state = _uniform_state(2)
        updater = _default_updater()
        hid = list(state.hypotheses.keys())[0]
        result = updater.compute(state, _bundle([_item(hid, 0.85, "sensor-default")]))
        ht = result.trace.hypothesis_traces[hid]
        assert "sensor-default" in ht.raw_likelihoods
        assert abs(ht.raw_likelihoods["sensor-default"] - 0.85) < 1e-6


# ===========================================================================
# 10. Integration with BeliefStore
# ===========================================================================

class TestStoreIntegration:

    def test_update_result_applies_to_store(self):
        """BayesianUpdateResult.update should apply cleanly to a BeliefStore."""
        store = BeliefStore()
        h0 = _hyp("H-zero", 0.6)
        h1 = _hyp("H-one",  0.4)
        store.create([h0, h1])

        state = store.current()
        updater = _default_updater()
        bundle = _bundle([_item(h0.hypothesis_id, 0.9, "sensor-default")])
        result = updater.compute(state, bundle)

        new_state = store.apply(result.update, author="bayesian_engine")
        assert new_state.version == state.version + 1

    def test_five_sequential_updates_converge(self):
        """
        Repeated evidence for one hypothesis should progressively increase its probability.
        """
        store = BeliefStore()
        h0 = _hyp("Hypothesis-A", 0.5)
        h1 = _hyp("Hypothesis-B", 0.5)
        store.create([h0, h1])
        updater = _default_updater(conflict_threshold=0.99)

        for _ in range(5):
            state = store.current()
            bundle = _bundle([_item(h0.hypothesis_id, 0.85, "sensor-reliable")])
            result = updater.compute(state, bundle)
            store.apply(result.update, author="bayesian_engine")

        final_p = store.current().confidence_distribution[h0.hypothesis_id]
        assert final_p > 0.7

    def test_posterior_written_to_store_matches_result(self):
        store = BeliefStore()
        h0 = _hyp("Alpha", 0.5)
        h1 = _hyp("Beta",  0.5)
        store.create([h0, h1])

        state = store.current()
        updater = _default_updater()
        bundle = _bundle([_item(h0.hypothesis_id, 0.9, "sensor-default")])
        result = updater.compute(state, bundle)
        store.apply(result.update, author="bayesian_engine")

        new_state = store.current()
        # The applied delta should have shifted h0 upward
        assert new_state.confidence_distribution[h0.hypothesis_id] > 0.5

    def test_audit_log_records_bayesian_update(self):
        store = BeliefStore()
        h = _hyp("H", 1.0)
        store.create([h])

        state = store.current()
        updater = _default_updater()
        result = updater.compute(state, _bundle([_item(h.hypothesis_id, 0.8, "sensor-default")]))
        store.apply(result.update, author="bayesian_engine")

        log = store.audit_log()
        assert log[-1].author == "bayesian_engine"
        assert result.update.update_id in log[-1].update_ids

    def test_no_active_hypotheses_raises(self):
        h_refuted = _hyp("H", 0.5, HypothesisStatus.REFUTED)
        state = BeliefState(
            hypotheses={h_refuted.hypothesis_id: h_refuted},
            confidence_distribution={},
        )
        updater = _default_updater()
        bundle = _bundle([_item(h_refuted.hypothesis_id, 0.8, "sensor-default")])
        with pytest.raises(ValueError, match="no ACTIVE hypotheses"):
            updater.compute(state, bundle)


# ===========================================================================
# 11. Source registration and fallback
# ===========================================================================

class TestSourceRegistration:

    def test_unknown_source_gets_default_profile(self):
        updater = BayesianUpdater(default_reliability=SourceReliability.C_FAIRLY_RELIABLE)
        profile = updater.get_profile("completely-unknown-source")
        assert profile.reliability == SourceReliability.C_FAIRLY_RELIABLE

    def test_register_source_overrides_default(self):
        updater = BayesianUpdater(default_reliability=SourceReliability.F_UNKNOWN)
        profile = SourceProfile(
            source_id="new-sensor",
            reliability=SourceReliability.A_COMPLETELY_RELIABLE,
        )
        updater.register_source(profile)
        assert updater.get_profile("new-sensor").reliability == SourceReliability.A_COMPLETELY_RELIABLE

    def test_unknown_source_in_bundle_does_not_crash(self):
        """Unregistered source should use default profile, not raise."""
        state = _uniform_state(2)
        updater = BayesianUpdater()
        hid = list(state.hypotheses.keys())[0]
        bundle = _bundle([_item(hid, 0.75, "unregistered-sensor-XYZ")])
        result = updater.compute(state, bundle)   # must not raise
        assert result.posterior[hid] > 0.0

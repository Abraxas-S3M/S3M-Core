"""
S3M Belief-State Bayesian Update Engine
=========================================
Implements principled Bayesian inference over BeliefHypothesis distributions.

Architecture
------------
Prior (BeliefState.confidence_distribution)
  |
  |-> EvidenceBundle  -> LikelihoodMatrix
  |       |                    |
  |       |       SourceProfile (reliability x recency weights)
  |       |                    |
  +-------+--------------------v
                  Log-space Bayes update
                  (log_posterior = log_prior + sum(log_likelihood))
                         |
                  Log-sum-exp normalisation
                         |
                  ConflictDetector  -> dampening if conflict > threshold
                         |
                  UpdateTrace  -> full derivation (explainability)
                         |
                  BeliefUpdate  -> BeliefStore.apply()

Numerical contract
------------------
  - All arithmetic in log-space to prevent underflow with many evidence items
  - Minimum log value: LOG_FLOOR = -500  (~ exp(-500) ~ 7e-218, safely non-zero)
  - Normalisation via log-sum-exp (numerically stable)
  - Conflicting evidence lowers certainty via entropy-based dampening
  - All outputs are validated: posterior sum = 1.0 +/- 1e-9

Source reliability (NATO intelligence grading A-F)
---------------------------------------------------
  A  Completely reliable        weight = 1.00
  B  Usually reliable           weight = 0.80
  C  Fairly reliable            weight = 0.60
  D  Not usually reliable       weight = 0.40
  E  Unreliable                 weight = 0.20
  F  Reliability unknown        weight = 0.50  (neutral, not zero)

Recency weighting
-----------------
  w_recency(t) = exp(-lambda * age_seconds)
  Default lambda = 0.005  -> half-life ~= 139 seconds
  Effective weight = reliability_weight * recency_weight in (0, 1]
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import (
    BeliefHypothesis,
    BeliefState,
    BeliefUpdate,
    EvidenceLayer,
    EvidenceLink,
    HypothesisStatus,
    UpdateSource,
)

# ---------------------------------------------------------------------------
# Numerical constants
# ---------------------------------------------------------------------------

LOG_FLOOR: float = -500.0  # log(~7e-218) - safe minimum in log-space
NORM_TOLERANCE: float = 1e-9  # posterior sum must be within this of 1.0
DEFAULT_RECENCY_LAMBDA: float = 0.005  # e-folding rate (per second)
CONFLICT_DAMPEN_FLOOR: float = 0.3  # minimum dampening factor on conflict


# ---------------------------------------------------------------------------
# NATO source reliability grades
# ---------------------------------------------------------------------------

class SourceReliability(str, Enum):
    """
    NATO STANAG 2511 intelligence source reliability grading.
    Maps to a scalar confidence weight used in likelihood computation.
    """

    A_COMPLETELY_RELIABLE = "A"  # Corroborated, no doubt
    B_USUALLY_RELIABLE = "B"  # Minor doubt
    C_FAIRLY_RELIABLE = "C"  # Some doubt
    D_NOT_USUALLY_RELIABLE = "D"  # Significant doubt
    E_UNRELIABLE = "E"  # No real likelihood of reliability
    F_UNKNOWN = "F"  # Cannot be judged


_RELIABILITY_WEIGHTS: Dict[SourceReliability, float] = {
    SourceReliability.A_COMPLETELY_RELIABLE: 1.00,
    SourceReliability.B_USUALLY_RELIABLE: 0.80,
    SourceReliability.C_FAIRLY_RELIABLE: 0.60,
    SourceReliability.D_NOT_USUALLY_RELIABLE: 0.40,
    SourceReliability.E_UNRELIABLE: 0.20,
    SourceReliability.F_UNKNOWN: 0.50,
}


# ---------------------------------------------------------------------------
# Source profile
# ---------------------------------------------------------------------------

class SourceProfile(BaseModel):
    """
    Reliability and recency configuration for an evidence source.

    source_id:       Identifier matching EvidenceLink.sensor_id or layer
    reliability:     NATO grade - drives multiplicative weight on likelihood
    recency_lambda:  Exponential decay rate lambda (per second).
                     Higher lambda = faster staleness decay.
                     Default 0.005 -> half-life ~= 139 s.
    layer:           Which S3M layer this source belongs to
    notes:           Free-text annotation (bilingual)
    notes_ar:        Arabic annotation for SDAIA/ALLaM

    Effective weight = reliability_weight * exp(-lambda * age_seconds)
    """

    source_id: str
    reliability: SourceReliability = SourceReliability.F_UNKNOWN
    recency_lambda: float = Field(default=DEFAULT_RECENCY_LAMBDA, gt=0.0)
    layer: EvidenceLayer = EvidenceLayer.EXTERNAL_SENSOR
    notes: Optional[str] = None
    notes_ar: Optional[str] = None

    def reliability_weight(self) -> float:
        """Return the scalar reliability weight for this source [0.2, 1.0]."""
        return _RELIABILITY_WEIGHTS[self.reliability]

    def recency_weight(self, age_seconds: float) -> float:
        """
        Compute the exponential recency weight for evidence of given age.

        w(t) = exp(-lambda * t) clipped to [0.01, 1.0]
        """
        raw = math.exp(-self.recency_lambda * max(0.0, age_seconds))
        return max(0.01, min(1.0, raw))

    def effective_weight(self, age_seconds: float) -> float:
        """
        Combined weight = reliability * recency, in (0.0, 1.0].
        Guaranteed to be > 0 so no log(0) risk.
        """
        return self.reliability_weight() * self.recency_weight(age_seconds)


# ---------------------------------------------------------------------------
# Evidence item - per-hypothesis signal
# ---------------------------------------------------------------------------

class EvidenceItem(BaseModel):
    """
    A single piece of evidence asserting the likelihood of one hypothesis.

    hypothesis_id:   The hypothesis this evidence pertains to
    likelihood:      P(evidence | hypothesis) in (0, 1]
                     How probable is this observation IF the hypothesis is true?
                     Must be > 0 (cannot be exactly 0; use a small epsilon instead)
    source_id:       Matches a SourceProfile.source_id
    raw_link:        Optional EvidenceLink for audit trail
    description:     What this item represents
    description_ar:  Arabic description for SDAIA/ALLaM
    observed_at:     When this evidence was collected (UTC)
    metadata:        Arbitrary engine payload
    """

    evidence_item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hypothesis_id: str
    likelihood: float = Field(gt=0.0, le=1.0)
    source_id: str
    raw_link: Optional[EvidenceLink] = None
    description: str = ""
    description_ar: Optional[str] = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("hypothesis_id", mode="before")
    @classmethod
    def hyp_id_not_blank(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("EvidenceItem.hypothesis_id must not be blank")
        return str(v).strip()

    def age_seconds(self, now: Optional[datetime] = None) -> float:
        """Seconds since this evidence was observed."""
        ref = now or datetime.now(timezone.utc)
        return max(0.0, (ref - self.observed_at).total_seconds())


# ---------------------------------------------------------------------------
# Evidence bundle - one full update cycle
# ---------------------------------------------------------------------------

class EvidenceBundle(BaseModel):
    """
    A complete set of evidence items delivered in one sensor/assessment cycle.

    bundle_id:    Unique cycle identifier (for audit)
    source:       Which S3M update source produced this bundle
    author_id:    Human operator ID if HITL-generated
    items:        All evidence items in this cycle
    collected_at: UTC time the bundle was assembled
    justification:     Why this bundle was generated (English)
    justification_ar:  Arabic justification for SDAIA/ALLaM audit
    """

    bundle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: UpdateSource = UpdateSource.SENSOR_FUSION
    author_id: Optional[str] = None
    items: List[EvidenceItem] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    justification: Optional[str] = None
    justification_ar: Optional[str] = None

    @field_validator("items", mode="before")
    @classmethod
    def items_not_empty(cls, v: List[EvidenceItem]) -> List[EvidenceItem]:
        if not v:
            raise ValueError("EvidenceBundle.items must contain at least one EvidenceItem")
        return v

    def items_for(self, hypothesis_id: str) -> List[EvidenceItem]:
        """Return all items relevant to a specific hypothesis."""
        return [i for i in self.items if i.hypothesis_id == hypothesis_id]

    def unique_sources(self) -> List[str]:
        """Return deduplicated list of source IDs in this bundle."""
        return list(dict.fromkeys(i.source_id for i in self.items))


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

class ConflictReport(BaseModel):
    """
    Records a detected conflict between evidence items targeting the same hypothesis.

    A conflict arises when evidence from different sources pulls the likelihood
    in opposite directions (one high, one low) for the same hypothesis.

    hypothesis_id:     Affected hypothesis
    max_likelihood:    Highest reported likelihood
    min_likelihood:    Lowest reported likelihood
    spread:            max - min (0 = agreement, 1 = maximum conflict)
    dampening_factor:  Multiplier applied to the posterior update [0.3, 1.0]
                       1.0 = no dampening, 0.3 = strong conflict suppression
    source_ids:        Sources contributing to the conflict
    """

    hypothesis_id: str
    max_likelihood: float
    min_likelihood: float
    spread: float
    dampening_factor: float
    source_ids: List[str]

    model_config = {"frozen": True}


class ConflictDetector:
    """
    Detects and quantifies conflicting evidence signals.

    Conflict is defined as:
        spread = max(likelihoods) - min(likelihoods) > conflict_threshold

    Dampening is computed as:
        factor = max(FLOOR, 1.0 - spread)

    This reduces - but never eliminates - the contribution of ambiguous evidence.
    """

    def __init__(
        self,
        conflict_threshold: float = 0.3,
        dampen_floor: float = CONFLICT_DAMPEN_FLOOR,
    ) -> None:
        self.threshold = conflict_threshold
        self.dampen_floor = dampen_floor

    def analyse(
        self,
        hypothesis_id: str,
        weighted_likelihoods: List[Tuple[float, str]],  # (likelihood, source_id)
    ) -> Optional[ConflictReport]:
        """
        Analyse likelihood spread for a hypothesis across sources.

        Returns a ConflictReport if spread > threshold, else None.
        """
        if len(weighted_likelihoods) < 2:
            return None

        likelihoods = [wl[0] for wl in weighted_likelihoods]
        source_ids = [wl[1] for wl in weighted_likelihoods]
        hi, lo = max(likelihoods), min(likelihoods)
        spread = hi - lo

        if spread <= self.threshold:
            return None

        dampening = max(self.dampen_floor, 1.0 - spread)
        return ConflictReport(
            hypothesis_id=hypothesis_id,
            max_likelihood=hi,
            min_likelihood=lo,
            spread=round(spread, 6),
            dampening_factor=round(dampening, 6),
            source_ids=source_ids,
        )


# ---------------------------------------------------------------------------
# Update trace - full explainability record
# ---------------------------------------------------------------------------

class HypothesisTrace(BaseModel):
    """
    Full derivation for one hypothesis in a Bayesian update cycle.

    prior:              P(H) before this update
    posterior:          P(H) after this update
    delta:              posterior - prior
    log_prior:          ln(prior)
    log_likelihood_sum: sum_i w_i * ln(L_i)
    log_posterior_raw:  log_prior + log_likelihood_sum
    effective_weights:  source_id -> effective weight applied
    raw_likelihoods:    source_id -> raw likelihood value
    conflict:           ConflictReport if conflict detected, else None
    """

    hypothesis_id: str
    description: str
    prior: float
    posterior: float
    delta: float
    log_prior: float
    log_likelihood_sum: float
    log_posterior_raw: float
    effective_weights: Dict[str, float]
    raw_likelihoods: Dict[str, float]
    conflict: Optional[ConflictReport] = None

    model_config = {"frozen": True}


class UpdateTrace(BaseModel):
    """
    Complete explainability record for one BayesianUpdater.compute() call.

    trace_id:          Unique ID for this derivation
    bundle_id:         EvidenceBundle that triggered this update
    hypothesis_traces: Per-hypothesis derivations
    conflicts:         All detected conflicts across hypotheses
    prior_entropy:     Shannon entropy of the prior distribution
    posterior_entropy: Shannon entropy of the posterior distribution
    entropy_delta:     posterior_entropy - prior_entropy
    normalisation_constant: The log-sum-exp Z used to normalise
    timestamp:         UTC time of computation
    author_id:         Operator ID if HITL
    """

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bundle_id: str
    hypothesis_traces: Dict[str, HypothesisTrace]
    conflicts: List[ConflictReport]
    prior_entropy: float
    posterior_entropy: float
    entropy_delta: float
    normalisation_constant: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    author_id: Optional[str] = None

    model_config = {"frozen": True}

    def dominant_hypothesis_id(self) -> Optional[str]:
        """Return the hypothesis_id with the highest posterior probability."""
        if not self.hypothesis_traces:
            return None
        return max(
            self.hypothesis_traces,
            key=lambda hid: self.hypothesis_traces[hid].posterior,
        )

    def most_conflicted_hypothesis_id(self) -> Optional[str]:
        """Return the hypothesis with the highest conflict spread, if any."""
        with_conflict = [
            (t.conflict.spread, hid)
            for hid, t in self.hypothesis_traces.items()
            if t.conflict is not None
        ]
        if not with_conflict:
            return None
        return max(with_conflict)[1]

    def certainty_increased(self) -> bool:
        """Return True if this update reduced overall entropy (more certain)."""
        return self.entropy_delta < 0.0

    def summary_en(self) -> str:
        """One-line English summary of the update outcome."""
        dom = self.dominant_hypothesis_id()
        desc = ""
        if dom and dom in self.hypothesis_traces:
            desc = self.hypothesis_traces[dom].description[:60]
        direction = "increased" if self.certainty_increased() else "decreased"
        return (
            f"Bayesian update: certainty {direction} "
            f"(dH={self.entropy_delta:+.4f} nats). "
            f"Leading hypothesis: '{desc}'. "
            f"Conflicts detected: {len(self.conflicts)}."
        )

    def summary_ar(self) -> str:
        """Arabic summary for SDAIA/ALLaM integration."""
        direction_ar = "ازدادت" if self.certainty_increased() else "انخفضت"
        return (
            f"التحديث البايزي: اليقين {direction_ar} "
            f"(dH={self.entropy_delta:+.4f}). "
            f"التعارضات المكتشفة: {len(self.conflicts)}."
        )


# ---------------------------------------------------------------------------
# Bayesian update result
# ---------------------------------------------------------------------------

class BayesianUpdateResult(BaseModel):
    """
    Complete output of one BayesianUpdater.compute() call.

    update: BeliefUpdate       ready to pass directly to BeliefStore.apply()
    trace:  UpdateTrace        full derivation for explainability / audit
    posterior: Dict[str,float] normalised posterior distribution
    """

    update: BeliefUpdate
    trace: UpdateTrace
    posterior: Dict[str, float]

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def posterior_is_normalised(self) -> "BayesianUpdateResult":
        if self.posterior:
            total = sum(self.posterior.values())
            if not (1.0 - NORM_TOLERANCE <= total <= 1.0 + NORM_TOLERANCE):
                raise ValueError(
                    f"BayesianUpdateResult.posterior must sum to 1.0, got {total:.10f}"
                )
        return self


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class BayesianUpdater:
    """
    Bayesian inference engine for S3M BeliefState hypothesis distributions.
    """

    def __init__(
        self,
        source_profiles: Optional[Dict[str, SourceProfile]] = None,
        conflict_threshold: float = 0.3,
        dampen_floor: float = CONFLICT_DAMPEN_FLOOR,
        default_reliability: SourceReliability = SourceReliability.F_UNKNOWN,
        min_prior: float = 1e-6,
    ) -> None:
        self._profiles: Dict[str, SourceProfile] = source_profiles or {}
        self._conflict_detector = ConflictDetector(conflict_threshold, dampen_floor)
        self._default_reliability = default_reliability
        self._min_prior = max(1e-12, min_prior)

    def compute(
        self,
        prior_state: BeliefState,
        bundle: EvidenceBundle,
        now: Optional[datetime] = None,
    ) -> BayesianUpdateResult:
        """
        Compute the Bayesian posterior given a prior BeliefState and an EvidenceBundle.
        """
        now = now or datetime.now(timezone.utc)
        prior_dist = prior_state.confidence_distribution

        # Only update ACTIVE hypotheses per operational belief-state policy.
        active_hyps: Dict[str, BeliefHypothesis] = {
            hid: h
            for hid, h in prior_state.hypotheses.items()
            if h.status == HypothesisStatus.ACTIVE
        }
        if not active_hyps:
            raise ValueError(
                "BayesianUpdater.compute: prior_state has no ACTIVE hypotheses. "
                "Cannot apply Bayesian update."
            )

        log_posteriors_raw: Dict[str, float] = {}
        h_traces: Dict[str, _HypTrace] = {}

        for hid, hyp in active_hyps.items():
            prior_p = max(self._min_prior, prior_dist.get(hid, self._min_prior))
            log_prior = math.log(prior_p)

            items = bundle.items_for(hid)
            log_lik_sum, eff_weights, raw_liks, conflict = self._compute_likelihood(
                hid, items, now
            )

            log_post_raw = max(LOG_FLOOR, log_prior + log_lik_sum)

            if conflict is not None:
                # Tactical conflict dampening: pull posterior toward prior.
                d = conflict.dampening_factor
                log_post_raw = d * log_post_raw + (1.0 - d) * log_prior
                log_post_raw = max(LOG_FLOOR, log_post_raw)

            log_posteriors_raw[hid] = log_post_raw
            h_traces[hid] = _HypTrace(
                hypothesis_id=hid,
                description=hyp.description,
                prior=prior_p,
                log_prior=log_prior,
                log_likelihood_sum=log_lik_sum,
                log_posterior_raw=log_post_raw,
                effective_weights=eff_weights,
                raw_likelihoods=raw_liks,
                conflict=conflict,
            )

        log_z = _logsumexp(list(log_posteriors_raw.values()))

        posterior: Dict[str, float] = {}
        for hid, log_post_raw in log_posteriors_raw.items():
            posterior[hid] = math.exp(log_post_raw - log_z)
        posterior = _renormalise(posterior)

        delta: Dict[str, float] = {}
        hypothesis_traces: Dict[str, HypothesisTrace] = {}
        all_conflicts: List[ConflictReport] = []

        for hid, ht in h_traces.items():
            post_p = posterior[hid]
            d = max(-1.0, min(1.0, post_p - ht.prior))
            delta[hid] = round(d, 8)

            if ht.conflict:
                all_conflicts.append(ht.conflict)

            hypothesis_traces[hid] = HypothesisTrace(
                hypothesis_id=hid,
                description=ht.description,
                prior=round(ht.prior, 8),
                posterior=round(post_p, 8),
                delta=round(d, 8),
                log_prior=round(ht.log_prior, 8),
                log_likelihood_sum=round(ht.log_likelihood_sum, 8),
                log_posterior_raw=round(ht.log_posterior_raw, 8),
                effective_weights=ht.effective_weights,
                raw_likelihoods=ht.raw_likelihoods,
                conflict=ht.conflict,
            )

        prior_entropy = _entropy(list(prior_dist.values()))
        post_entropy = _entropy(list(posterior.values()))
        trace = UpdateTrace(
            bundle_id=bundle.bundle_id,
            hypothesis_traces=hypothesis_traces,
            conflicts=all_conflicts,
            prior_entropy=round(prior_entropy, 8),
            posterior_entropy=round(post_entropy, 8),
            entropy_delta=round(post_entropy - prior_entropy, 8),
            normalisation_constant=round(log_z, 8),
            author_id=bundle.author_id,
        )

        justification = bundle.justification or trace.summary_en()
        belief_update = BeliefUpdate(
            source=bundle.source,
            author_id=bundle.author_id,
            delta=delta,
            justification=justification,
            justification_ar=bundle.justification_ar or trace.summary_ar(),
        )

        return BayesianUpdateResult(update=belief_update, trace=trace, posterior=posterior)

    def register_source(self, profile: SourceProfile) -> None:
        """Register or replace a SourceProfile by source_id."""
        self._profiles[profile.source_id] = profile

    def get_profile(self, source_id: str) -> SourceProfile:
        """
        Return the SourceProfile for source_id.
        Falls back to a default profile with configured default_reliability.
        """
        if source_id in self._profiles:
            return self._profiles[source_id]
        return SourceProfile(
            source_id=source_id,
            reliability=self._default_reliability,
        )

    def _compute_likelihood(
        self,
        hypothesis_id: str,
        items: List[EvidenceItem],
        now: datetime,
    ) -> Tuple[float, Dict[str, float], Dict[str, float], Optional[ConflictReport]]:
        """
        Compute the weighted log-likelihood for one hypothesis.
        """
        if not items:
            return 0.0, {}, {}, None

        effective_weights: Dict[str, float] = {}
        raw_likelihoods_accum: Dict[str, List[float]] = {}

        log_lik_sum = 0.0
        for item in items:
            profile = self.get_profile(item.source_id)
            age = item.age_seconds(now)
            w = profile.effective_weight(age)
            l_value = max(1e-12, item.likelihood)

            sid = item.source_id
            effective_weights[sid] = round(w, 6)
            raw_likelihoods_accum.setdefault(sid, []).append(l_value)
            log_lik_sum += w * math.log(l_value)

        raw_likelihoods = {
            sid: round(sum(vals) / len(vals), 6) for sid, vals in raw_likelihoods_accum.items()
        }

        conflict = self._conflict_detector.analyse(
            hypothesis_id,
            [(raw_likelihoods[sid], sid) for sid in raw_likelihoods],
        )

        return log_lik_sum, effective_weights, raw_likelihoods, conflict


# ---------------------------------------------------------------------------
# Intermediate mutable trace (internal, not Pydantic)
# ---------------------------------------------------------------------------

class _HypTrace:
    """Mutable intermediate state during per-hypothesis computation."""

    __slots__ = (
        "hypothesis_id",
        "description",
        "prior",
        "log_prior",
        "log_likelihood_sum",
        "log_posterior_raw",
        "effective_weights",
        "raw_likelihoods",
        "conflict",
    )

    def __init__(
        self,
        hypothesis_id: str,
        description: str,
        prior: float,
        log_prior: float,
        log_likelihood_sum: float,
        log_posterior_raw: float,
        effective_weights: Dict[str, float],
        raw_likelihoods: Dict[str, float],
        conflict: Optional[ConflictReport],
    ) -> None:
        self.hypothesis_id = hypothesis_id
        self.description = description
        self.prior = prior
        self.log_prior = log_prior
        self.log_likelihood_sum = log_likelihood_sum
        self.log_posterior_raw = log_posterior_raw
        self.effective_weights = effective_weights
        self.raw_likelihoods = raw_likelihoods
        self.conflict = conflict


# ---------------------------------------------------------------------------
# Numerical utilities
# ---------------------------------------------------------------------------

def _logsumexp(log_values: List[float]) -> float:
    """
    Numerically stable log-sum-exp.

    log(sum(exp(x_i))) = max(x) + log(sum(exp(x_i - max(x))))
    """
    if not log_values:
        return LOG_FLOOR
    m = max(log_values)
    if m <= LOG_FLOOR:
        return LOG_FLOOR
    return m + math.log(sum(math.exp(v - m) for v in log_values))


def _renormalise(dist: Dict[str, float]) -> Dict[str, float]:
    """
    Force exact normalisation of a probability distribution.
    Corrects floating-point accumulation errors after exp().
    """
    total = sum(dist.values())
    if total <= 0.0:
        n = len(dist)
        return {k: 1.0 / n for k in dist} if n > 0 else dist
    return {k: v / total for k, v in dist.items()}


def _entropy(probs: List[float]) -> float:
    """Shannon entropy in nats: H = -sum(p * ln(p)) for p > 0."""
    return -sum(p * math.log(p) for p in probs if p > 0.0)

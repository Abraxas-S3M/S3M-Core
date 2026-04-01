"""
S3M Consensus Engine v1.0
Unified decision-making from multiple LLM engines.

This module combines responses from Phi-3, Grok, Mistral, and ALLaM into a
single authoritative recommendation through voting, weighting, and agreement
analysis. The design intentionally stays lightweight (stdlib only) so it can
run offline on Jetson-class tactical edge hardware.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from statistics import pstdev
from typing import Dict, List, Optional, Tuple

from difflib import SequenceMatcher

logger = logging.getLogger("s3m.consensus")


class ConsensusMode(Enum):
    """Consensus resolution modes."""

    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_VOTE = "weighted_vote"
    HIERARCHICAL_RESOLUTION = "hierarchical_resolution"
    ABSTAIN_ON_LOW_CONFIDENCE = "abstain_on_low_confidence"


class AgreementLevel(Enum):
    """Agreement classification bands from pairwise text similarity."""

    FULL_AGREEMENT = "full_agreement"  # similarity >= 0.85
    STRONG_AGREEMENT = "strong_agreement"  # similarity >= 0.70
    MODERATE_AGREEMENT = "moderate_agreement"  # similarity >= 0.50
    WEAK_AGREEMENT = "weak_agreement"  # similarity >= 0.30
    DISAGREEMENT = "disagreement"  # similarity < 0.30


@dataclass
class EngineResponse:
    """Single engine response in consensus."""

    engine_id: str
    text: str
    latency_ms: float
    tokens_generated: int
    confidence_score: Optional[float] = 0.75
    failed: bool = False
    error_message: Optional[str] = None


@dataclass
class ConsensusResult:
    """Output of consensus process."""

    final_text: str
    agreement_score: float
    disagreement_score: float
    winning_strategy: str
    per_engine_weights: Dict[str, float]
    per_engine_scores: Dict[str, float]
    review_status: str
    agreement_level: str
    voting_matrix: Dict[str, int] = field(default_factory=dict)
    engines_used: List[str] = field(default_factory=list)
    engines_failed: List[str] = field(default_factory=list)
    confidence_threshold_met: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""

        return {
            "final_text": self.final_text,
            "agreement_score": self.agreement_score,
            "disagreement_score": self.disagreement_score,
            "winning_strategy": self.winning_strategy,
            "per_engine_weights": self.per_engine_weights,
            "per_engine_scores": self.per_engine_scores,
            "review_status": self.review_status,
            "agreement_level": self.agreement_level,
            "voting_matrix": self.voting_matrix,
            "engines_used": self.engines_used,
            "engines_failed": self.engines_failed,
            "confidence_threshold_met": self.confidence_threshold_met,
        }


class TextSimilarityCalculator:
    """Lightweight text similarity implementation with stdlib primitives."""

    # Tactical context: a lightweight, fixed stop-word list avoids loading
    # heavyweight NLP assets in disconnected field deployments.
    STOP_WORDS = {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }

    # Tactical context: these verbs are common in mission recommendations and
    # help isolate decision-bearing clauses for voting.
    ACTION_KEYWORDS = {
        "recommend",
        "execute",
        "hold",
        "advance",
        "retreat",
        "secure",
        "observe",
        "monitor",
        "engage",
        "disengage",
        "reroute",
        "evacuate",
        "defend",
        "support",
        "resupply",
        "investigate",
        "escalate",
        "deescalate",
        "continue",
        "abort",
        "delay",
        "proceed",
        "stabilize",
        "prioritize",
    }

    TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_/-]+")

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize whitespace and casing for deterministic scoring."""

        normalized = " ".join((text or "").strip().lower().split())
        return normalized

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        """Tokenize text into lightweight lexical units."""

        normalized = cls.normalize_text(text)
        return cls.TOKEN_PATTERN.findall(normalized)

    @classmethod
    def extract_sentences(cls, text: str) -> List[str]:
        """Split text into sentence-like units using punctuation boundaries."""

        normalized = (text or "").strip()
        if not normalized:
            return []
        fragments = re.split(r"[.!?\n]+", normalized)
        return [frag.strip() for frag in fragments if frag.strip()]

    @classmethod
    def extract_keywords(cls, text: str, max_words: int = 20) -> List[str]:
        """Extract significant non-stopword tokens for overlap scoring."""

        keywords: List[str] = []
        for token in cls.tokenize(text):
            if token in cls.STOP_WORDS:
                continue
            keywords.append(token)
            if len(keywords) >= max_words:
                break
        return keywords

    @classmethod
    def extract_action_label(cls, text: str) -> Optional[str]:
        """
        Extract action label/target token from recommendation phrasing.

        Tactical context: this helps distinguish "action X" vs "action Y"
        so disagreement is surfaced even when sentence structure is similar.
        """

        tokens = cls.tokenize(text)
        if not tokens:
            return None

        for idx, token in enumerate(tokens[:-1]):
            if token in {"action", "course", "coa"}:
                candidate = tokens[idx + 1]
                if candidate and candidate not in cls.STOP_WORDS:
                    return candidate
        return None

    @classmethod
    def extract_statement_token(cls, text: str) -> str:
        """
        Extract a compact statement token used by the voting matrix.

        Tactical context: if engines describe alternate courses of action,
        statement tokens provide a stable mission-level vote unit without
        expensive semantic models.
        """

        sentences = cls.extract_sentences(text)
        if not sentences:
            return "empty"

        # Prefer the first sentence containing an action keyword.
        for sentence in sentences:
            tokens = cls.tokenize(sentence)
            if any(tok in cls.ACTION_KEYWORDS for tok in tokens):
                focus = cls.extract_keywords(sentence, max_words=6)
                return " ".join(focus) if focus else cls.normalize_text(sentence)[:72]

        # Fallback to keywords from the first sentence.
        fallback = cls.extract_keywords(sentences[0], max_words=6)
        if fallback:
            return " ".join(fallback)
        return cls.normalize_text(sentences[0])[:72]

    @staticmethod
    def _dice_similarity(tokens_a: List[str], tokens_b: List[str]) -> float:
        """Dice coefficient variant from token-set overlap."""

        set_a = set(tokens_a)
        set_b = set(tokens_b)
        if not set_a or not set_b:
            return 0.0
        overlap = len(set_a & set_b)
        return (2.0 * overlap) / (len(set_a) + len(set_b))

    @staticmethod
    def _cosine_similarity(tokens_a: List[str], tokens_b: List[str]) -> float:
        """Cosine similarity over bag-of-words counters."""

        if not tokens_a or not tokens_b:
            return 0.0

        counter_a = Counter(tokens_a)
        counter_b = Counter(tokens_b)

        vocab = set(counter_a) | set(counter_b)
        dot = sum(counter_a[tok] * counter_b[tok] for tok in vocab)
        norm_a = math.sqrt(sum(counter_a[tok] ** 2 for tok in vocab))
        norm_b = math.sqrt(sum(counter_b[tok] ** 2 for tok in vocab))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _sequence_similarity(text_a: str, text_b: str) -> float:
        """Character-level similarity to capture phrasing alignment."""

        if not text_a or not text_b:
            return 0.0
        return SequenceMatcher(None, text_a, text_b).ratio()

    @classmethod
    def calculate_similarity(cls, text_a: str, text_b: str) -> float:
        """
        Calculate final similarity between two texts (0.0 - 1.0).

        Combines:
        - keyword overlap (Dice)
        - lexical cosine similarity
        - sequence matching ratio
        """

        if not text_a or not text_b:
            return 0.0

        norm_a = cls.normalize_text(text_a)
        norm_b = cls.normalize_text(text_b)
        if not norm_a or not norm_b:
            return 0.0

        keywords_a = cls.extract_keywords(norm_a, max_words=40)
        keywords_b = cls.extract_keywords(norm_b, max_words=40)

        dice = cls._dice_similarity(keywords_a, keywords_b)
        cosine = cls._cosine_similarity(keywords_a, keywords_b)
        sequence = cls._sequence_similarity(norm_a, norm_b)

        # Weighted blend tuned for short recommendation outputs.
        similarity = (dice * 0.5) + (cosine * 0.2) + (sequence * 0.3)
        action_label_a = cls.extract_action_label(norm_a)
        action_label_b = cls.extract_action_label(norm_b)
        if action_label_a and action_label_b:
            if action_label_a != action_label_b:
                similarity *= 0.75
            else:
                similarity = min(1.0, similarity + 0.05)
        return max(0.0, min(1.0, similarity))

    @classmethod
    def calculate_similarity_matrix(
        cls,
        responses: List[EngineResponse],
    ) -> Dict[Tuple[str, str], float]:
        """Calculate pairwise similarities between all valid responses."""

        similarities: Dict[Tuple[str, str], float] = {}
        for idx, response_a in enumerate(responses):
            for response_b in responses[idx + 1 :]:
                pair_score = cls.calculate_similarity(response_a.text, response_b.text)
                similarities[(response_a.engine_id, response_b.engine_id)] = pair_score
        return similarities


class AgreementAnalyzer:
    """Utility methods for mission-level agreement and disagreement metrics."""

    @staticmethod
    def build_voting_matrix(responses: List[EngineResponse]) -> Dict[str, int]:
        """Build statement vote counts using extracted statement tokens."""

        statement_votes: Dict[str, int] = defaultdict(int)
        for response in responses:
            statement = TextSimilarityCalculator.extract_statement_token(response.text)
            statement_votes[statement] += 1

        # Keep all statements for observability and debugging.
        return dict(statement_votes)

    @staticmethod
    def assess_agreement(
        similarities: Dict[Tuple[str, str], float],
        responses: List[EngineResponse],
        voting_matrix: Optional[Dict[str, int]] = None,
    ) -> Tuple[float, float, str]:
        """
        Assess overall agreement and disagreement.

        disagreement_score = (1 - avg_similarity)
                           + variance_penalty
                           + minority_penalty
        """

        if not responses:
            return 0.0, 1.0, AgreementLevel.DISAGREEMENT.value

        if not similarities:
            # A single valid response is operationally accepted as full agreement.
            return 1.0, 0.0, AgreementLevel.FULL_AGREEMENT.value

        sim_values = list(similarities.values())
        avg_similarity = sum(sim_values) / len(sim_values)
        similarity_stddev = pstdev(sim_values) if len(sim_values) > 1 else 0.0

        # Cap variance contribution to avoid drowning base disagreement signal.
        variance_penalty = min(0.2, similarity_stddev)

        minority_penalty = 0.0
        if voting_matrix:
            total_votes = sum(voting_matrix.values())
            if total_votes > 0:
                top_votes = max(voting_matrix.values())
                top_ratio = top_votes / total_votes
                # Tactical context: fragmented votes indicate divergent
                # recommendations and should bias toward manual review.
                if top_ratio < 0.5:
                    minority_penalty = min(0.2, (0.5 - top_ratio) * 0.5)

        agreement_score = max(0.0, min(1.0, avg_similarity))
        disagreement_score = (1.0 - agreement_score) + variance_penalty + minority_penalty
        disagreement_score = max(0.0, min(1.0, disagreement_score))

        if agreement_score >= 0.85:
            level = AgreementLevel.FULL_AGREEMENT.value
        elif agreement_score >= 0.70:
            level = AgreementLevel.STRONG_AGREEMENT.value
        elif agreement_score >= 0.50:
            level = AgreementLevel.MODERATE_AGREEMENT.value
        elif agreement_score >= 0.30:
            level = AgreementLevel.WEAK_AGREEMENT.value
        else:
            level = AgreementLevel.DISAGREEMENT.value

        return agreement_score, disagreement_score, level


class ConsensusEngine:
    """
    Synchronize multiple engine responses into one operational recommendation.

    Tactical context: this component acts as the mission arbitration layer when
    multiple engine outputs diverge under contested or ambiguous situations.
    """

    def __init__(
        self,
        disagreement_threshold: float = 0.35,
        confidence_threshold: float = 0.60,
        auto_mode_selection: bool = True,
    ) -> None:
        self.disagreement_threshold = disagreement_threshold
        self.confidence_threshold = confidence_threshold
        self.auto_mode_selection = auto_mode_selection

        logger.info(
            "ConsensusEngine initialized "
            "(disagreement_threshold=%.2f, confidence_threshold=%.2f, auto=%s)",
            disagreement_threshold,
            confidence_threshold,
            auto_mode_selection,
        )

    def synthesize(
        self,
        responses: List[EngineResponse],
        mode: Optional[ConsensusMode] = None,
    ) -> ConsensusResult:
        """Synthesize final consensus result from raw engine responses."""

        logger.info("Synthesize consensus called with %d responses", len(responses))

        if not responses:
            return self._handle_empty_responses()

        valid_responses = [response for response in responses if not response.failed]
        failed_responses = [response for response in responses if response.failed]

        if not valid_responses:
            return self._handle_all_failed(failed_responses)

        similarities = TextSimilarityCalculator.calculate_similarity_matrix(valid_responses)
        voting_matrix = AgreementAnalyzer.build_voting_matrix(valid_responses)
        agreement_score, disagreement_score, agreement_level = AgreementAnalyzer.assess_agreement(
            similarities=similarities,
            responses=valid_responses,
            voting_matrix=voting_matrix,
        )

        chosen_mode = mode
        if chosen_mode is None:
            chosen_mode = (
                self._select_mode(disagreement_score=disagreement_score, responses=valid_responses)
                if self.auto_mode_selection
                else ConsensusMode.MAJORITY_VOTE
            )

        final_text = self._apply_resolution(
            mode=chosen_mode,
            responses=valid_responses,
            agreement_score=agreement_score,
            voting_matrix=voting_matrix,
        )

        review_status = self._determine_review_status(
            disagreement_score=disagreement_score,
            agreement_level=agreement_level,
            responses=valid_responses,
        )

        per_engine_weights = self._calculate_per_engine_weights(valid_responses)
        per_engine_scores = self._calculate_per_engine_scores(final_text, valid_responses)

        result = ConsensusResult(
            final_text=final_text,
            agreement_score=agreement_score,
            disagreement_score=disagreement_score,
            winning_strategy=chosen_mode.value,
            per_engine_weights=per_engine_weights,
            per_engine_scores=per_engine_scores,
            review_status=review_status,
            agreement_level=agreement_level,
            voting_matrix=voting_matrix,
            engines_used=[response.engine_id for response in valid_responses],
            engines_failed=[response.engine_id for response in failed_responses],
            confidence_threshold_met=all(
                (response.confidence_score is not None)
                and (response.confidence_score >= self.confidence_threshold)
                for response in valid_responses
            ),
        )

        logger.info(
            "Consensus complete (agreement=%.3f, disagreement=%.3f, mode=%s, review=%s)",
            agreement_score,
            disagreement_score,
            chosen_mode.value,
            review_status,
        )
        return result

    def _select_mode(
        self,
        disagreement_score: float,
        responses: List[EngineResponse],
    ) -> ConsensusMode:
        """
        Auto-select consensus mode from disagreement and confidence signals.

        Decision tree:
        - disagreement > threshold -> hierarchical resolution
        - any low-confidence engine -> abstain-on-low-confidence
        - moderate disagreement -> weighted vote
        - low disagreement -> majority vote
        """

        if disagreement_score > self.disagreement_threshold:
            logger.debug("Mode selection: disagreement %.3f -> hierarchical", disagreement_score)
            return ConsensusMode.HIERARCHICAL_RESOLUTION

        low_confidence = any(
            (response.confidence_score is None) or (response.confidence_score < self.confidence_threshold)
            for response in responses
        )
        if low_confidence:
            logger.debug("Mode selection: low confidence present -> abstain")
            return ConsensusMode.ABSTAIN_ON_LOW_CONFIDENCE

        if disagreement_score > max(0.15, self.disagreement_threshold / 2):
            logger.debug("Mode selection: moderate disagreement %.3f -> weighted", disagreement_score)
            return ConsensusMode.WEIGHTED_VOTE

        logger.debug("Mode selection: low disagreement %.3f -> majority", disagreement_score)
        return ConsensusMode.MAJORITY_VOTE

    def _apply_resolution(
        self,
        mode: ConsensusMode,
        responses: List[EngineResponse],
        agreement_score: float,
        voting_matrix: Dict[str, int],
    ) -> str:
        """Apply selected consensus strategy."""

        logger.debug(
            "Applying resolution mode=%s with agreement=%.3f and %d votes",
            mode.value,
            agreement_score,
            len(voting_matrix),
        )

        if mode == ConsensusMode.MAJORITY_VOTE:
            return self._majority_vote_resolution(responses, voting_matrix)
        if mode == ConsensusMode.WEIGHTED_VOTE:
            return self._weighted_vote_resolution(responses)
        if mode == ConsensusMode.HIERARCHICAL_RESOLUTION:
            return self._hierarchical_resolution(responses)
        if mode == ConsensusMode.ABSTAIN_ON_LOW_CONFIDENCE:
            return self._abstain_resolution(responses)
        return self._majority_vote_resolution(responses, voting_matrix)

    def _majority_vote_resolution(
        self,
        responses: List[EngineResponse],
        voting_matrix: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        Majority vote resolution.

        Tactical context: majority chooses the dominant recommendation cluster,
        then confidence breaks ties within that cluster.
        """

        if not responses:
            return "[ERROR] No valid responses for majority vote"

        statement_to_responses: Dict[str, List[EngineResponse]] = defaultdict(list)
        for response in responses:
            statement = TextSimilarityCalculator.extract_statement_token(response.text)
            statement_to_responses[statement].append(response)

        winning_statement = max(
            statement_to_responses.items(),
            key=lambda item: (len(item[1]), max((r.confidence_score or 0.0) for r in item[1])),
        )[0]
        candidate_pool = statement_to_responses[winning_statement]

        selected = max(candidate_pool, key=lambda response: response.confidence_score or 0.0)
        logger.debug(
            "Majority selected engine=%s statement=%s votes=%d",
            selected.engine_id,
            winning_statement,
            len(candidate_pool),
        )
        return selected.text

    def _weighted_vote_resolution(self, responses: List[EngineResponse]) -> str:
        """Weighted vote resolution with top-2 response fusion."""

        if not responses:
            return "[ERROR] No valid responses for weighted vote"
        if len(responses) == 1:
            return responses[0].text

        sorted_responses = sorted(
            responses,
            key=lambda response: response.confidence_score or 0.0,
            reverse=True,
        )
        primary = sorted_responses[0]
        secondary = sorted_responses[1]

        # Tactical context: include an alternate course-of-action summary to
        # keep commander visibility when confidence split is moderate.
        fused = (
            f"{primary.text}\n\n"
            f"[Alternative from {secondary.engine_id}: {secondary.text[:120].strip()}]"
        )
        logger.debug(
            "Weighted selected primary=%s secondary=%s",
            primary.engine_id,
            secondary.engine_id,
        )
        return fused

    def _hierarchical_resolution(self, responses: List[EngineResponse]) -> str:
        """Hierarchical resolution prefers confidence, then engine tier."""

        if not responses:
            return "[ERROR] No valid responses for hierarchical resolution"

        # Tactical context: fixed tie-breaker favors historically stable engines
        # under mission ambiguity if confidence values are equal.
        hierarchy = {"grok": 4, "mistral": 3, "phi3": 2, "allam": 1}

        def canonical_engine_id(engine_id: str) -> str:
            normalized = (engine_id or "").lower()
            if "grok" in normalized:
                return "grok"
            if "mistral" in normalized:
                return "mistral"
            if "phi3" in normalized or "phi-3" in normalized:
                return "phi3"
            if "allam" in normalized:
                return "allam"
            return normalized

        def response_key(response: EngineResponse) -> Tuple[float, int]:
            confidence = response.confidence_score if response.confidence_score is not None else 0.0
            tier = hierarchy.get(canonical_engine_id(response.engine_id), 0)
            return confidence, tier

        selected = max(responses, key=response_key)
        logger.debug(
            "Hierarchical selected engine=%s confidence=%.3f",
            selected.engine_id,
            selected.confidence_score or 0.0,
        )
        return selected.text

    def _abstain_resolution(self, responses: List[EngineResponse]) -> str:
        """Abstain mode returns best candidate with explicit low-confidence marker."""

        if not responses:
            return "[ERROR] No valid responses for abstain resolution"

        high_confidence = [
            response
            for response in responses
            if (response.confidence_score is not None)
            and (response.confidence_score >= self.confidence_threshold)
        ]
        selected_pool = high_confidence if high_confidence else responses
        selected = max(selected_pool, key=lambda response: response.confidence_score or 0.0)
        logger.debug(
            "Abstain selected engine=%s confidence=%.3f",
            selected.engine_id,
            selected.confidence_score or 0.0,
        )
        return f"[LOW CONFIDENCE] {selected.text}"

    def _determine_review_status(
        self,
        disagreement_score: float,
        agreement_level: str,
        responses: List[EngineResponse],
    ) -> str:
        """Return ACCEPT, REVIEW, or REJECT based on risk heuristics."""

        if disagreement_score > self.disagreement_threshold:
            return "REVIEW"

        if agreement_level in {
            AgreementLevel.WEAK_AGREEMENT.value,
            AgreementLevel.DISAGREEMENT.value,
        }:
            return "REVIEW"

        low_confidence_count = sum(
            1
            for response in responses
            if (response.confidence_score is None)
            or (response.confidence_score < self.confidence_threshold)
        )
        if low_confidence_count > 0:
            return "REVIEW"

        return "ACCEPT"

    def _calculate_per_engine_weights(self, responses: List[EngineResponse]) -> Dict[str, float]:
        """Calculate normalized confidence-based engine weights."""

        if not responses:
            return {}

        confidence_values = [
            response.confidence_score if response.confidence_score is not None else 0.5
            for response in responses
        ]
        total_confidence = sum(confidence_values)
        if total_confidence <= 0:
            uniform_weight = 1.0 / len(responses)
            return {response.engine_id: uniform_weight for response in responses}

        weights = {}
        for response in responses:
            confidence = response.confidence_score if response.confidence_score is not None else 0.5
            weights[response.engine_id] = confidence / total_confidence
        return weights

    def _calculate_per_engine_scores(
        self,
        final_text: str,
        responses: List[EngineResponse],
    ) -> Dict[str, float]:
        """Calculate each engine's similarity to final synthesized response."""

        scores: Dict[str, float] = {}
        for response in responses:
            similarity = TextSimilarityCalculator.calculate_similarity(final_text, response.text)
            scores[response.engine_id] = similarity
        return scores

    def _handle_empty_responses(self) -> ConsensusResult:
        """Handle no-input edge case."""

        logger.error("No responses received for consensus synthesis")
        return ConsensusResult(
            final_text="[ERROR] No responses received from engines",
            agreement_score=0.0,
            disagreement_score=1.0,
            winning_strategy="none",
            per_engine_weights={},
            per_engine_scores={},
            review_status="REJECT",
            agreement_level=AgreementLevel.DISAGREEMENT.value,
            voting_matrix={},
            engines_used=[],
            engines_failed=[],
            confidence_threshold_met=False,
        )

    def _handle_all_failed(self, failed_responses: List[EngineResponse]) -> ConsensusResult:
        """Handle complete multi-engine failure edge case."""

        logger.error("All engines failed in consensus (%d failures)", len(failed_responses))
        error_parts = []
        for failed_response in failed_responses:
            detail = failed_response.error_message or "unknown_error"
            error_parts.append(f"{failed_response.engine_id}: {detail}")

        return ConsensusResult(
            final_text="[ERROR] All engines failed. " + " | ".join(error_parts),
            agreement_score=0.0,
            disagreement_score=1.0,
            winning_strategy="none",
            per_engine_weights={},
            per_engine_scores={},
            review_status="REJECT",
            agreement_level=AgreementLevel.DISAGREEMENT.value,
            voting_matrix={},
            engines_used=[],
            engines_failed=[response.engine_id for response in failed_responses],
            confidence_threshold_met=False,
        )

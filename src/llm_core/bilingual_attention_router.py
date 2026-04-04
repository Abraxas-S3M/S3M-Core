"""
S3M Bilingual Attention Router (BAR)
ORIGINAL ALGORITHM — Language-aware prompt routing for Arabic/English operations

Problem: Tactical communications in Saudi sovereign context mix Arabic and English.
A single model handles one language well but not both equally.

Solution: Segment prompts by language at the token level, route segments to the
most capable engine, fuse responses with coherence-aware blending.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("s3m.llm_core.bilingual_router")


class Language(str, Enum):
    ARABIC = "ar"
    ENGLISH = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class LanguageSegment:
    text: str
    language: Language
    confidence: float  # 0-1
    start_char: int
    end_char: int
    token_count: int


@dataclass
class RoutingDecision:
    strategy: str  # "single_allam", "single_phi3", "parallel_fuse"
    primary_engine: str  # engine_id
    secondary_engine: Optional[str]
    arabic_fraction: float
    english_fraction: float
    segments: List[LanguageSegment]
    context_hints: Dict[str, str]  # hints to pass to the non-primary engine


@dataclass
class FusedResponse:
    text: str
    primary_source: str  # which engine contributed most
    fusion_confidence: float
    per_segment_sources: List[Tuple[str, str]]  # (text_segment, source_engine)
    coherence_score: float  # 0-1, internal consistency of fused response


class BilingualAttentionRouter:
    """
    Routes mixed Arabic/English prompts to optimal engines.

    The language detector uses Unicode script detection (fast, no ML needed):
    - Arabic script: U+0600–U+06FF, U+0750–U+077F, U+08A0-U+08FF, U+FB50–U+FDFF, U+FE70–U+FEFF
    - Latin script: U+0041–U+005A, U+0061–U+007A, extended Latin blocks
    - Digits and punctuation: neutral (assigned to surrounding language)

    Tactical context:
    - The classifier is deterministic and offline so edge deployments on sovereign
      hardware can route mixed-language mission prompts with minimal latency.
    """

    _WORD_RE = re.compile(r"\S+")
    _ARABIC_TRANSLIT_MAP = {
        "ا": "a",
        "أ": "a",
        "إ": "i",
        "آ": "aa",
        "ب": "b",
        "ت": "t",
        "ث": "th",
        "ج": "j",
        "ح": "h",
        "خ": "kh",
        "د": "d",
        "ذ": "dh",
        "ر": "r",
        "ز": "z",
        "س": "s",
        "ش": "sh",
        "ص": "s",
        "ض": "d",
        "ط": "t",
        "ظ": "z",
        "ع": "a",
        "غ": "gh",
        "ف": "f",
        "ق": "q",
        "ك": "k",
        "ل": "l",
        "م": "m",
        "ن": "n",
        "ه": "h",
        "و": "w",
        "ؤ": "w",
        "ي": "y",
        "ى": "a",
        "ئ": "y",
        "ة": "h",
        "ء": "'",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "َ": "a",
        "ُ": "u",
        "ِ": "i",
        "ّ": "",
        "ْ": "",
        "ً": "an",
        "ٌ": "un",
        "ٍ": "in",
    }

    def __init__(
        self,
        arabic_engine_id: str = "allam-7b",
        english_engine_id: str = "phi3-mini",
        parallel_threshold: float = 0.3,
    ):
        """
        parallel_threshold: if minority language fraction > this,
        use parallel inference + fusion instead of single engine
        """
        if not 0.0 <= parallel_threshold <= 0.5:
            raise ValueError("parallel_threshold must be in [0.0, 0.5]")
        self.arabic_engine_id = arabic_engine_id
        self.english_engine_id = english_engine_id
        self.parallel_threshold = parallel_threshold

    def detect_language_segments(self, text: str) -> List[LanguageSegment]:
        """
        Segment text by language using Unicode script detection.

        Algorithm:
        1. Classify each character as Arabic, Latin, or neutral
        2. Merge consecutive same-language characters into segments
        3. Assign neutral characters to the language of surrounding text
        4. Merge tiny segments (< 3 chars) into neighbors
        5. Compute confidence for each segment
        """
        if not text:
            return []

        labels: List[Language] = [self._classify_char(char) for char in text]
        self._assign_neutral_labels(labels)

        raw_segments: List[LanguageSegment] = []
        start = 0
        current = labels[0]
        for idx in range(1, len(text)):
            if labels[idx] != current:
                raw_segments.append(self._build_segment(text, current, start, idx))
                start = idx
                current = labels[idx]
        raw_segments.append(self._build_segment(text, current, start, len(text)))

        merged_segments = self._merge_tiny_segments(raw_segments)
        return self._reindex_segments(merged_segments)

    def make_routing_decision(self, text: str) -> RoutingDecision:
        """
        Decide how to route a mixed-language prompt.

        Rules:
        1. If arabic_fraction > 0.7: single_allam
           - Add English segments as context hints in the system prompt
        2. If english_fraction > 0.7: single_phi3
           - Add Arabic segments as transliterated context hints
        3. If 0.3 ≤ minority_fraction ≤ 0.7: parallel_fuse
           - Both engines process the full prompt
           - Results fused with language-aware confidence weighting
        """
        segments = self.detect_language_segments(text)
        arabic_weight = sum(segment.token_count for segment in segments if segment.language == Language.ARABIC)
        english_weight = sum(segment.token_count for segment in segments if segment.language == Language.ENGLISH)
        total = arabic_weight + english_weight

        if total <= 0:
            arabic_fraction = 0.0
            english_fraction = 1.0
        else:
            arabic_fraction = arabic_weight / total
            english_fraction = english_weight / total

        minority_fraction = min(arabic_fraction, english_fraction)

        if arabic_fraction > 0.7:
            strategy = "single_allam"
            primary = self.arabic_engine_id
            secondary = None
            hints = self.build_context_hints(segments, primary_language=Language.ARABIC)
        elif english_fraction > 0.7:
            strategy = "single_phi3"
            primary = self.english_engine_id
            secondary = None
            hints = self.build_context_hints(segments, primary_language=Language.ENGLISH)
        elif minority_fraction >= self.parallel_threshold:
            strategy = "parallel_fuse"
            if arabic_fraction >= english_fraction:
                primary = self.arabic_engine_id
                secondary = self.english_engine_id
            else:
                primary = self.english_engine_id
                secondary = self.arabic_engine_id
            hints = {
                "arabic_hint_for_english_engine": self.build_context_hints(
                    segments, primary_language=Language.ENGLISH
                ).get("minority_segments", ""),
                "english_hint_for_arabic_engine": self.build_context_hints(
                    segments, primary_language=Language.ARABIC
                ).get("minority_segments", ""),
            }
        elif arabic_fraction >= english_fraction:
            strategy = "single_allam"
            primary = self.arabic_engine_id
            secondary = None
            hints = self.build_context_hints(segments, primary_language=Language.ARABIC)
        else:
            strategy = "single_phi3"
            primary = self.english_engine_id
            secondary = None
            hints = self.build_context_hints(segments, primary_language=Language.ENGLISH)

        return RoutingDecision(
            strategy=strategy,
            primary_engine=primary,
            secondary_engine=secondary,
            arabic_fraction=arabic_fraction,
            english_fraction=english_fraction,
            segments=segments,
            context_hints=hints,
        )

    def build_context_hints(
        self,
        segments: List[LanguageSegment],
        primary_language: Language,
    ) -> Dict[str, str]:
        """
        Build context hints from minority-language segments.

        For Arabic primary: extract English technical terms, keep as-is in prompt
        For English primary: extract Arabic named entities, add transliteration
        """
        if primary_language not in (Language.ARABIC, Language.ENGLISH):
            return {}

        minority = Language.ENGLISH if primary_language == Language.ARABIC else Language.ARABIC
        terms: List[str] = []
        for segment in segments:
            if segment.language != minority:
                continue
            cleaned = segment.text.strip()
            if cleaned and cleaned not in terms:
                terms.append(cleaned)

        if not terms:
            return {"minority_language": minority.value, "minority_segments": ""}

        if primary_language == Language.ARABIC:
            return {
                "minority_language": minority.value,
                "minority_segments": " | ".join(terms),
                "tactical_instruction": (
                    "Preserve English tactical terms exactly to keep cross-unit interoperability."
                ),
            }

        transliterated = [self._transliterate_arabic(term) for term in terms]
        return {
            "minority_language": minority.value,
            "minority_segments": " | ".join(terms),
            "transliteration_hints": " | ".join(transliterated),
            "tactical_instruction": (
                "Maintain Arabic named entities and their transliteration for mission continuity."
            ),
        }

    def fuse_responses(
        self,
        arabic_response: str,
        english_response: str,
        routing: RoutingDecision,
    ) -> FusedResponse:
        """
        Fuse parallel responses into a coherent bilingual output.

        Algorithm:
        1. Segment both responses by language
        2. For Arabic segments: prefer ALLaM's version
        3. For English segments: prefer Phi-3's version
        4. For mixed segments: use the engine whose response has higher
           internal coherence (measured by bigram consistency)
        5. Stitch segments together with transition smoothing
        6. Compute overall coherence score
        7. If coherence < 0.6: fall back to single best response
        """
        ar_segments = self.detect_language_segments(arabic_response)
        en_segments = self.detect_language_segments(english_response)

        coherence_ar = self._compute_coherence(arabic_response)
        coherence_en = self._compute_coherence(english_response)

        primary_source = routing.primary_engine
        if primary_source == self.arabic_engine_id:
            base_text = arabic_response
            base_segments = ar_segments
            secondary_source = self.english_engine_id
        else:
            base_text = english_response
            base_segments = en_segments
            secondary_source = self.arabic_engine_id

        preferred_pools = {
            Language.ARABIC: [segment for segment in ar_segments if segment.language == Language.ARABIC],
            Language.ENGLISH: [segment for segment in en_segments if segment.language == Language.ENGLISH],
        }
        pool_idx = {Language.ARABIC: 0, Language.ENGLISH: 0}

        per_segment_sources: List[Tuple[str, str]] = []
        output_chunks: List[str] = []
        weighted_confidence = 0.0
        seen_weight = 0.0
        contribution_chars = {
            self.arabic_engine_id: 0,
            self.english_engine_id: 0,
        }

        for segment in base_segments:
            chosen_text = segment.text
            chosen_engine = primary_source
            chosen_conf = segment.confidence

            if segment.language in (Language.ARABIC, Language.ENGLISH):
                preferred_engine = (
                    self.arabic_engine_id if segment.language == Language.ARABIC else self.english_engine_id
                )
                if preferred_engine != primary_source:
                    idx = pool_idx[segment.language]
                    pool = preferred_pools[segment.language]
                    if idx < len(pool):
                        candidate = pool[idx]
                        pool_idx[segment.language] += 1
                        if candidate.confidence >= 0.45:
                            chosen_text = candidate.text
                            chosen_conf = candidate.confidence
                            chosen_engine = preferred_engine
            elif segment.language == Language.MIXED:
                if coherence_ar >= coherence_en:
                    chosen_engine = self.arabic_engine_id
                else:
                    chosen_engine = self.english_engine_id
            else:
                chosen_engine = primary_source if coherence_ar == coherence_en else (
                    self.arabic_engine_id if coherence_ar > coherence_en else self.english_engine_id
                )

            # Keep original Unicode order and codepoints to preserve RTL/LTR directionality.
            output_chunks.append(chosen_text)
            per_segment_sources.append((chosen_text, chosen_engine))
            contribution_chars[chosen_engine] = contribution_chars.get(chosen_engine, 0) + len(chosen_text.strip())

            seg_weight = max(segment.token_count, 1)
            weighted_confidence += chosen_conf * seg_weight
            seen_weight += seg_weight

        fused_text = "".join(output_chunks).strip() or base_text
        coherence_fused = self._compute_coherence(fused_text)
        fusion_confidence = weighted_confidence / seen_weight if seen_weight else 0.0

        if coherence_fused < 0.6:
            ar_score = (0.6 * coherence_ar) + (0.4 * routing.arabic_fraction)
            en_score = (0.6 * coherence_en) + (0.4 * routing.english_fraction)
            if ar_score >= en_score:
                return FusedResponse(
                    text=arabic_response,
                    primary_source=self.arabic_engine_id,
                    fusion_confidence=ar_score,
                    per_segment_sources=[(arabic_response, self.arabic_engine_id)],
                    coherence_score=coherence_ar,
                )
            return FusedResponse(
                text=english_response,
                primary_source=self.english_engine_id,
                fusion_confidence=en_score,
                per_segment_sources=[(english_response, self.english_engine_id)],
                coherence_score=coherence_en,
            )

        if not fused_text:
            fused_text = base_text
            coherence_fused = self._compute_coherence(fused_text)

        if contribution_chars:
            primary_source = max(contribution_chars, key=contribution_chars.get)
        elif primary_source not in (self.arabic_engine_id, self.english_engine_id):
            primary_source = secondary_source

        return FusedResponse(
            text=fused_text,
            primary_source=primary_source,
            fusion_confidence=min(max(fusion_confidence, 0.0), 1.0),
            per_segment_sources=per_segment_sources,
            coherence_score=coherence_fused,
        )

    def _classify_char(self, char: str) -> Language:
        """Classify a single character by Unicode codepoint."""
        if not char:
            return Language.UNKNOWN
        codepoint = ord(char)
        category = unicodedata.category(char)
        is_letter_or_mark = category.startswith("L") or category in {"Mn", "Mc"}

        # Arabic letters and diacritics (tashkeel) across Arabic blocks.
        if (
            0x0600 <= codepoint <= 0x06FF
            or 0x0750 <= codepoint <= 0x077F
            or 0x08A0 <= codepoint <= 0x08FF
            or 0xFB50 <= codepoint <= 0xFDFF
            or 0xFE70 <= codepoint <= 0xFEFF
        ) and is_letter_or_mark:
            return Language.ARABIC

        # Basic and extended Latin alphabets.
        if (
            0x0041 <= codepoint <= 0x005A
            or 0x0061 <= codepoint <= 0x007A
            or 0x00C0 <= codepoint <= 0x024F
            or 0x1E00 <= codepoint <= 0x1EFF
        ) and is_letter_or_mark:
            return Language.ENGLISH

        # Digits (ASCII and Arabic-Indic), punctuation, symbols and whitespace
        # remain neutral and are assigned to surrounding script.
        return Language.UNKNOWN

    def _compute_coherence(self, text: str) -> float:
        """
        Simple coherence metric: character-level bigram consistency.
        High coherence: bigrams are consistent with a single language model.
        Low coherence: frequent script switches within words.
        """
        if not text or len(text) < 2:
            return 1.0 if text else 0.0

        transitions = 0
        comparable_pairs = 0
        stable_pairs = 0
        labels = [self._classify_char(char) for char in text]
        for idx in range(len(labels) - 1):
            left = labels[idx]
            right = labels[idx + 1]
            if left == Language.UNKNOWN or right == Language.UNKNOWN:
                continue
            comparable_pairs += 1
            if left == right:
                stable_pairs += 1
            else:
                transitions += 1

        if comparable_pairs == 0:
            return 0.75

        stability = stable_pairs / comparable_pairs
        transition_penalty = min(transitions / comparable_pairs, 1.0) * 0.5
        return min(max(stability - transition_penalty, 0.0), 1.0)

    def _assign_neutral_labels(self, labels: List[Language]) -> None:
        """Assign neutral chars to nearest surrounding language in linear time."""
        n_chars = len(labels)
        prev_known: List[Language] = [Language.UNKNOWN] * n_chars
        next_known: List[Language] = [Language.UNKNOWN] * n_chars

        last = Language.UNKNOWN
        for idx in range(n_chars):
            if labels[idx] != Language.UNKNOWN:
                last = labels[idx]
            prev_known[idx] = last

        next_lang = Language.UNKNOWN
        for idx in range(n_chars - 1, -1, -1):
            if labels[idx] != Language.UNKNOWN:
                next_lang = labels[idx]
            next_known[idx] = next_lang

        for idx, current in enumerate(labels):
            if current != Language.UNKNOWN:
                continue
            left = prev_known[idx]
            right = next_known[idx]
            if left == right and left != Language.UNKNOWN:
                labels[idx] = left
            elif left != Language.UNKNOWN and right == Language.UNKNOWN:
                labels[idx] = left
            elif right != Language.UNKNOWN and left == Language.UNKNOWN:
                labels[idx] = right
            elif left != Language.UNKNOWN and right != Language.UNKNOWN:
                # Tactical intent: keep separators attached to previous unit to
                # preserve phrase boundaries used by command-and-control prompts.
                labels[idx] = left
            else:
                labels[idx] = Language.UNKNOWN

    def _build_segment(self, text: str, language: Language, start: int, end: int) -> LanguageSegment:
        fragment = text[start:end]
        return LanguageSegment(
            text=fragment,
            language=language,
            confidence=self._segment_confidence(fragment, language),
            start_char=start,
            end_char=end,
            token_count=len(self._WORD_RE.findall(fragment)),
        )

    def _merge_tiny_segments(self, segments: List[LanguageSegment]) -> List[LanguageSegment]:
        if len(segments) <= 1:
            return segments

        merged: List[LanguageSegment] = []
        idx = 0
        while idx < len(segments):
            current = segments[idx]
            visible_length = len(current.text.strip())
            if current.language in (Language.ARABIC, Language.ENGLISH) and visible_length < 3:
                prev_seg = merged[-1] if merged else None
                next_seg = segments[idx + 1] if idx + 1 < len(segments) else None

                if prev_seg and next_seg:
                    if len(prev_seg.text) >= len(next_seg.text):
                        prev_seg.text += current.text
                    else:
                        next_seg.text = current.text + next_seg.text
                elif prev_seg:
                    prev_seg.text += current.text
                elif next_seg:
                    next_seg.text = current.text + next_seg.text
                else:
                    merged.append(current)
            else:
                merged.append(current)
            idx += 1

        compacted: List[LanguageSegment] = []
        for segment in merged:
            if compacted and compacted[-1].language == segment.language:
                compacted[-1].text += segment.text
                compacted[-1].end_char = segment.end_char
            else:
                compacted.append(segment)
        return compacted

    def _reindex_segments(self, segments: List[LanguageSegment]) -> List[LanguageSegment]:
        output: List[LanguageSegment] = []
        cursor = 0
        for segment in segments:
            end = cursor + len(segment.text)
            output.append(
                LanguageSegment(
                    text=segment.text,
                    language=segment.language,
                    confidence=self._segment_confidence(segment.text, segment.language),
                    start_char=cursor,
                    end_char=end,
                    token_count=len(self._WORD_RE.findall(segment.text)),
                )
            )
            cursor = end
        return output

    def _segment_confidence(self, text: str, language: Language) -> float:
        if not text:
            return 0.0
        if language == Language.UNKNOWN:
            return 0.5

        total_script = 0
        matching_script = 0
        for char in text:
            label = self._classify_char(char)
            if label == Language.UNKNOWN:
                continue
            total_script += 1
            if label == language:
                matching_script += 1

        if total_script == 0:
            return 0.55

        confidence = matching_script / total_script
        if len(text.strip()) < 3:
            confidence *= 0.9
        return min(max(confidence, 0.0), 1.0)

    def _transliterate_arabic(self, text: str) -> str:
        output_chars: List[str] = []
        for char in text:
            output_chars.append(self._ARABIC_TRANSLIT_MAP.get(char, char))
        return "".join(output_chars)

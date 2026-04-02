"""
S3M Data Value Assessor & Self-Cleaning Engine
UNCLASSIFIED - FOUO

Implements automatic data triage for Ministry of Defense (MoD) mission sets.
Every data item is tagged as "valuable" or "non_valuable" using pluggable
assessment strategies. Non-valuable data can then be purged based on the
selected self-cleaning mode.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("s3m.edge.data_value")


class DataItem:
    """A single data item with value tag and metadata."""

    __slots__ = ("item_id", "value", "tag", "confidence", "source", "timestamp", "metadata")

    def __init__(
        self,
        value: Any,
        tag: str = "unassessed",
        confidence: float = 0.0,
        source: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.item_id = id(value)
        self.value = value
        self.tag = tag
        self.confidence = float(confidence)
        self.source = source
        self.timestamp = time.time()
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "timestamp": self.timestamp,
        }


class TaggedDataStore:
    """
    In-memory data store with tag-based partitioning and cleanup accounting.
    """

    def __init__(self, max_size: int = 100000):
        if max_size <= 0:
            raise ValueError("max_size must be > 0")
        self.max_size = int(max_size)
        self._items: List[DataItem] = []
        self._clean_count = 0
        self._total_ingested = 0
        self._total_cleaned = 0

    def add(self, item: DataItem) -> None:
        if len(self._items) >= self.max_size:
            # Tactical context: discard stale low-value data first under
            # constrained edge storage budgets.
            non_val_indices = [i for i, d in enumerate(self._items) if d.tag == "non_valuable"]
            self._items.pop(non_val_indices[0] if non_val_indices else 0)
        self._items.append(item)
        self._total_ingested += 1

    def get_valuable(self) -> List[Any]:
        return [d.value for d in self._items if d.tag == "valuable"]

    def get_non_valuable(self) -> List[Any]:
        return [d.value for d in self._items if d.tag == "non_valuable"]

    def get_all_values(self) -> List[Any]:
        return [d.value for d in self._items]

    def get_all_items(self) -> List[DataItem]:
        return list(self._items)

    def clean_non_valuable(self) -> int:
        before = len(self._items)
        self._items = [d for d in self._items if d.tag != "non_valuable"]
        cleaned = before - len(self._items)
        self._total_cleaned += cleaned
        self._clean_count += 1
        if cleaned > 0:
            logger.info(
                "[Self-Clean] Disposed of %d non-valuable items (cycle=%d)",
                cleaned,
                self._clean_count,
            )
        return cleaned

    def stats(self) -> Dict[str, Any]:
        tag_counts = Counter(d.tag for d in self._items)
        return {
            "total_items": len(self._items),
            "valuable": tag_counts.get("valuable", 0),
            "non_valuable": tag_counts.get("non_valuable", 0),
            "unassessed": tag_counts.get("unassessed", 0),
            "total_ingested": self._total_ingested,
            "total_cleaned": self._total_cleaned,
            "clean_cycles": self._clean_count,
            "max_size": self.max_size,
        }


class RuleBasedAssessor:
    """MoD domain-specific keyword and heuristic rules."""

    def __init__(self):
        self._valuable_keywords: List[str] = [
            "threat",
            "hostile",
            "target",
            "enemy",
            "weapon",
            "missile",
            "uav",
            "drone",
            "convoy",
            "insurgent",
            "artillery",
            "radar",
            "sigint",
            "comint",
            "elint",
            "surveillance",
            "reconnaissance",
            "logistics",
            "supply",
            "ammunition",
            "fuel",
            "medevac",
            "chemical",
            "biological",
            "nuclear",
            "explosive",
            "ied",
            # Arabic mission keywords
            "تهديد",
            "عدو",
            "هدف",
            "سلاح",
            "صاروخ",
            "طائرة",
            "رادار",
            "استطلاع",
            "لوجستيات",
            "ذخيرة",
            "وقود",
        ]
        self._custom_rules: List[Callable[[Any], bool]] = []

    def add_keyword(self, keyword: str) -> None:
        self._valuable_keywords.append(str(keyword).lower())

    def add_keywords(self, keywords: List[str]) -> None:
        self._valuable_keywords.extend(str(k).lower() for k in keywords)

    def add_custom_rule(self, rule: Callable[[Any], bool]) -> None:
        self._custom_rules.append(rule)

    def assess(self, data: Any) -> Tuple[bool, float]:
        # String/text data: keyword match.
        if isinstance(data, str):
            text_lower = data.lower()
            matches = sum(1 for kw in self._valuable_keywords if kw in text_lower)
            if matches > 0:
                return True, min(1.0, matches * 0.25)
            return False, 0.9

        # Numeric/array anomaly heuristic.
        if isinstance(data, (int, float)):
            return (True, 0.6) if abs(float(data)) > 3.0 else (False, 0.5)

        if isinstance(data, np.ndarray):
            if not np.isfinite(data).all():
                return False, 0.95
            return (True, 0.55) if np.any(np.abs(data) > 3.0) else (False, 0.5)

        # Dict/object textual projection for keyword scan.
        if isinstance(data, dict):
            try:
                text_repr = json.dumps(data, default=str, ensure_ascii=False).lower()
            except Exception:
                text_repr = str(data).lower()
            matches = sum(1 for kw in self._valuable_keywords if kw in text_repr)
            if matches > 0:
                return True, min(1.0, matches * 0.2)
            return False, 0.7

        for rule in self._custom_rules:
            try:
                if rule(data):
                    return True, 0.7
            except Exception:
                continue

        return False, 0.3


class StatisticalAssessor:
    """
    High-entropy predictions are treated as more valuable for training,
    because uncertainty marks potential mission-relevant blind spots.
    """

    def __init__(self, entropy_threshold: float = 0.7):
        if not 0.0 <= entropy_threshold <= 1.0:
            raise ValueError("entropy_threshold must be in [0, 1]")
        self.entropy_threshold = float(entropy_threshold)

    def assess_from_probs(self, probs: np.ndarray) -> Tuple[bool, float]:
        p = np.asarray(probs, dtype=np.float64).ravel()
        if p.size < 2:
            raise ValueError("probs must contain at least two classes")
        if not np.isfinite(p).all():
            raise ValueError("probs must be finite")
        total = float(p.sum())
        if total <= 0.0:
            raise ValueError("probs must sum to a positive value")
        p = p / total

        entropy = -np.sum(p * np.log(p + 1e-12))
        max_entropy = np.log(float(p.size))
        normalized_entropy = float(entropy / (max_entropy + 1e-12))

        is_valuable = normalized_entropy >= self.entropy_threshold
        confidence = min(1.0, abs(normalized_entropy - self.entropy_threshold) + 0.5)
        return is_valuable, confidence


class DataValueEngine:
    """Orchestrates value assessment and self-cleaning for edge nodes."""

    VALID_CLEANING_MODES = {"immediate", "post_cycle", "manual"}

    def __init__(
        self,
        cleaning_mode: str = "post_cycle",
        store_max_size: int = 100000,
        entropy_threshold: float = 0.7,
        composite_weights: Optional[Tuple[float, float]] = None,
    ):
        if cleaning_mode not in self.VALID_CLEANING_MODES:
            raise ValueError(f"cleaning_mode must be one of {sorted(self.VALID_CLEANING_MODES)}")

        self.cleaning_mode = cleaning_mode
        self.store = TaggedDataStore(max_size=store_max_size)
        self.rule_assessor = RuleBasedAssessor()
        self.stat_assessor = StatisticalAssessor(entropy_threshold=entropy_threshold)
        self._cycle_count = 0

        # (rule_weight, stat_weight) for composite vote when both are present.
        self._weights = composite_weights or (0.7, 0.3)
        if self._weights[0] < 0 or self._weights[1] < 0:
            raise ValueError("composite weights must be non-negative")
        if (self._weights[0] + self._weights[1]) <= 0:
            raise ValueError("composite weights must sum to > 0")

        logger.info("DataValueEngine initialized (mode=%s, max_store=%d)", cleaning_mode, store_max_size)

    def _composite_decision(
        self,
        rule_valuable: bool,
        rule_conf: float,
        stat_valuable: Optional[bool],
        stat_conf: Optional[float],
    ) -> Tuple[bool, float]:
        # Rule strategy priority as requested: positive rule hit always wins.
        if rule_valuable:
            return True, float(max(rule_conf, stat_conf or 0.0))

        if stat_valuable is None or stat_conf is None:
            return False, float(rule_conf)

        rule_vote = (1.0 if rule_valuable else 0.0) * self._weights[0]
        stat_vote = (1.0 if stat_valuable else 0.0) * self._weights[1]
        denom = self._weights[0] + self._weights[1]
        score = (rule_vote + stat_vote) / denom
        is_valuable = score >= 0.5
        confidence = max(float(rule_conf), float(stat_conf))
        return is_valuable, confidence

    def ingest(
        self,
        data: Any,
        source: str = "external",
        model_probs: Optional[np.ndarray] = None,
    ) -> DataItem:
        rule_valuable, rule_conf = self.rule_assessor.assess(data)

        stat_valuable: Optional[bool] = None
        stat_conf: Optional[float] = None
        if model_probs is not None:
            stat_valuable, stat_conf = self.stat_assessor.assess_from_probs(model_probs)

        is_valuable, confidence = self._composite_decision(
            rule_valuable=rule_valuable,
            rule_conf=rule_conf,
            stat_valuable=stat_valuable,
            stat_conf=stat_conf,
        )

        tag = "valuable" if is_valuable else "non_valuable"
        item = DataItem(value=data, tag=tag, confidence=confidence, source=source)
        self.store.add(item)

        if self.cleaning_mode == "immediate" and tag == "non_valuable":
            self.store.clean_non_valuable()

        return item

    def ingest_batch(
        self,
        data_list: List[Any],
        source: str = "external",
        model_probs_batch: Optional[np.ndarray] = None,
    ) -> Dict[str, int]:
        counts = {"valuable": 0, "non_valuable": 0}
        for i, data in enumerate(data_list):
            probs = model_probs_batch[i] if model_probs_batch is not None else None
            item = self.ingest(data, source=source, model_probs=probs)
            counts[item.tag] = counts.get(item.tag, 0) + 1

        if self.cleaning_mode == "immediate":
            self.store.clean_non_valuable()

        return counts

    def get_training_data(self) -> List[Any]:
        return self.store.get_valuable()

    def get_all_data(self) -> List[Any]:
        return self.store.get_all_values()

    def post_cycle_clean(self) -> int:
        self._cycle_count += 1
        if self.cleaning_mode == "post_cycle":
            return self.store.clean_non_valuable()
        return 0

    def manual_clean(self) -> int:
        return self.store.clean_non_valuable()

    def reassess_all(self, model_forward: Optional[Callable[[np.ndarray], np.ndarray]] = None) -> Dict[str, int]:
        counts = {"promoted": 0, "demoted": 0, "unchanged": 0}
        for item in self.store.get_all_items():
            old_tag = item.tag
            rule_val, rule_conf = self.rule_assessor.assess(item.value)

            stat_val: Optional[bool] = None
            stat_conf: Optional[float] = None
            if model_forward and isinstance(item.value, np.ndarray):
                try:
                    probs = model_forward(item.value.reshape(1, -1))[0]
                    stat_val, stat_conf = self.stat_assessor.assess_from_probs(probs)
                except Exception:
                    stat_val, stat_conf = None, None

            is_valuable, confidence = self._composite_decision(
                rule_valuable=rule_val,
                rule_conf=rule_conf,
                stat_valuable=stat_val,
                stat_conf=stat_conf,
            )

            item.tag = "valuable" if is_valuable else "non_valuable"
            item.confidence = confidence

            if old_tag == item.tag:
                counts["unchanged"] += 1
            elif item.tag == "valuable":
                counts["promoted"] += 1
            else:
                counts["demoted"] += 1

        return counts

    def health_check(self) -> Dict[str, Any]:
        return {
            "cleaning_mode": self.cleaning_mode,
            "cycle_count": self._cycle_count,
            "store": self.store.stats(),
            "rule_keywords": len(self.rule_assessor._valuable_keywords),
            "entropy_threshold": self.stat_assessor.entropy_threshold,
        }

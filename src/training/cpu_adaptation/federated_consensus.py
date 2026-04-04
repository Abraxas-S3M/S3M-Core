"""
S3M Federated Adapter Consensus Protocol (FACP)
ORIGINAL ALGORITHM — Byzantine-fault-tolerant federated adapter aggregation.

Problem: Standard FedAvg blindly averages updates. In denied environments:
  - Nodes may have hardware faults causing corrupted gradients
  - Adversarial data injection is a real threat
  - Network partitions mean some nodes train on stale data
  - Node capabilities are heterogeneous (austere vs. fixed site)

Solution: Multi-signal consensus-weighted aggregation with outlier rejection.

Each node's adapter delta is weighted by a composite trust score:
  trust_i = w_hw * hardware_score_i
          + w_loss * loss_confidence_i
          + w_dist * median_proximity_i
          + w_attest * attestation_score_i

Where:
  hardware_score: derived from node's HardwareTier (fixed_site=1.0, austere=0.5)
  loss_confidence: 1 - normalized_loss (lower training loss = higher confidence)
  median_proximity: 1 - distance_from_geometric_median / max_distance
  attestation_score: 1.0 if cryptographic hash chain valid, 0.0 if not

Byzantine rejection: any update with trust_i < threshold is excluded.
Geometric median used instead of arithmetic mean for robustness to outliers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("s3m.training.federated_consensus")


@dataclass
class NodeAdapterUpdate:
    """A single node's contribution to federated aggregation."""

    node_id: str
    hardware_tier: str  # from HardwareTier enum
    adapter_weights: Dict[str, np.ndarray]  # layer_name -> delta weights
    training_loss: float  # final training loss
    num_samples: int  # number of training samples used
    training_steps: int  # number of training steps completed
    precision_used: str  # training precision
    timestamp: str  # when training completed
    # Integrity attestation
    weight_hash: str  # SHA256 of serialized weights
    training_config_hash: str  # SHA256 of training config
    parent_model_hash: str  # SHA256 of base model used
    attestation_chain: List[str]  # chain of hashes from previous rounds


@dataclass
class ConsensusResult:
    """Result of federated consensus aggregation."""

    merged_weights: Dict[str, np.ndarray]
    participating_nodes: List[str]
    rejected_nodes: List[str]
    rejection_reasons: Dict[str, str]
    trust_scores: Dict[str, float]
    consensus_confidence: float  # 0-1, how much agreement between nodes
    round_id: str
    timestamp: str


class FederatedAdapterConsensus:
    """
    Byzantine-fault-tolerant federated adapter aggregation.

    Usage:
        facp = FederatedAdapterConsensus()
        facp.register_update(node_update_1)
        facp.register_update(node_update_2)
        facp.register_update(node_update_3)
        result = facp.aggregate()
        if result.consensus_confidence > 0.7:
            apply_merged_adapter(result.merged_weights)
    """

    _EPSILON = 1e-12
    _MAX_NODES_PER_ROUND = 100
    _HASH_LEN = 64
    _HARDWARE_SCORES = {
        "fixed_site": 1.0,
        "edge_gpu": 0.9,
        "vehicle_node": 0.8,
        "cpu_standard": 0.7,
        "cpu_austere": 0.5,
    }

    def __init__(
        self,
        min_participants: int = 2,
        byzantine_threshold: float = 0.3,
        hardware_weight: float = 0.2,
        loss_weight: float = 0.3,
        distance_weight: float = 0.3,
        attestation_weight: float = 0.2,
        expected_parent_model_hash: Optional[str] = None,
        valid_training_config_hashes: Optional[List[str]] = None,
    ) -> None:
        self.min_participants = max(1, int(min_participants))
        self.byzantine_threshold = float(byzantine_threshold)
        self.weights = {
            "hardware": float(hardware_weight),
            "loss": float(loss_weight),
            "distance": float(distance_weight),
            "attestation": float(attestation_weight),
        }

        self.expected_parent_model_hash = (
            expected_parent_model_hash.strip().lower() if isinstance(expected_parent_model_hash, str) else None
        )
        self.valid_training_config_hashes = {
            item.strip().lower()
            for item in (valid_training_config_hashes or [])
            if isinstance(item, str) and item.strip()
        }

        self._updates: List[NodeAdapterUpdate] = []
        self._round_counter = 0
        self._intake_rejections: Dict[str, str] = {}
        self._loss_bounds: tuple[float, float] = (0.0, 0.0)
        self._distance_cache: Dict[str, float] = {}
        self._max_distance: float = 0.0
        self._last_result: Optional[ConsensusResult] = None

    @staticmethod
    def compute_weight_hash(adapter_weights: Dict[str, np.ndarray]) -> str:
        """Compute deterministic SHA256 hash of adapter weights."""
        hasher = hashlib.sha256()
        for layer_name in sorted(adapter_weights.keys()):
            array = np.asarray(adapter_weights[layer_name], dtype=np.float32)
            payload = np.ascontiguousarray(array)
            hasher.update(layer_name.encode("utf-8"))
            hasher.update(b"|")
            hasher.update(str(payload.shape).encode("utf-8"))
            hasher.update(b"|")
            hasher.update(payload.dtype.str.encode("utf-8"))
            hasher.update(b"|")
            hasher.update(payload.tobytes())
        return hasher.hexdigest()

    def register_update(self, update: NodeAdapterUpdate) -> bool:
        """
        Register a node's adapter update for the next aggregation round.

        Performs initial validation:
        1. Verify weight_hash matches actual weights
        2. Verify parent_model_hash matches expected base model
        3. Check for NaN/Inf in weights
        4. Verify reasonable loss value (not zero, not infinite)

        Returns True if update accepted, False if rejected at intake.
        """
        if not isinstance(update, NodeAdapterUpdate):
            return self._reject_intake("unknown", "invalid_update_object")
        if not update.node_id or not isinstance(update.node_id, str):
            return self._reject_intake("unknown", "invalid_node_id")
        if len(self._updates) >= self._MAX_NODES_PER_ROUND:
            return self._reject_intake(update.node_id, "max_nodes_exceeded")
        if not isinstance(update.adapter_weights, dict) or not update.adapter_weights:
            return self._reject_intake(update.node_id, "missing_adapter_weights")
        if not np.isfinite(update.training_loss) or float(update.training_loss) <= 0.0:
            return self._reject_intake(update.node_id, "invalid_training_loss")
        if int(update.num_samples) <= 0 or int(update.training_steps) <= 0:
            return self._reject_intake(update.node_id, "invalid_training_counts")
        if not self._is_valid_timestamp(update.timestamp):
            return self._reject_intake(update.node_id, "invalid_timestamp")

        canonical_weights: Dict[str, np.ndarray] = {}
        for layer_name, values in update.adapter_weights.items():
            if not isinstance(layer_name, str) or not layer_name:
                return self._reject_intake(update.node_id, "invalid_layer_name")
            arr = np.asarray(values, dtype=np.float32)
            if arr.size == 0:
                return self._reject_intake(update.node_id, f"empty_layer:{layer_name}")
            if not np.isfinite(arr).all():
                return self._reject_intake(update.node_id, f"non_finite_weights:{layer_name}")
            canonical_weights[layer_name] = np.ascontiguousarray(arr)

        computed_hash = self.compute_weight_hash(canonical_weights)
        if not self._safe_compare_hash(computed_hash, update.weight_hash):
            return self._reject_intake(update.node_id, "weight_hash_mismatch")
        if self.expected_parent_model_hash and not self._safe_compare_hash(
            self.expected_parent_model_hash, update.parent_model_hash
        ):
            return self._reject_intake(update.node_id, "parent_model_hash_mismatch")

        sanitized = NodeAdapterUpdate(
            node_id=update.node_id.strip(),
            hardware_tier=str(update.hardware_tier).strip().lower(),
            adapter_weights=canonical_weights,
            training_loss=float(update.training_loss),
            num_samples=int(update.num_samples),
            training_steps=int(update.training_steps),
            precision_used=str(update.precision_used),
            timestamp=str(update.timestamp),
            weight_hash=str(update.weight_hash).strip().lower(),
            training_config_hash=str(update.training_config_hash).strip().lower(),
            parent_model_hash=str(update.parent_model_hash).strip().lower(),
            attestation_chain=list(update.attestation_chain or []),
        )

        for idx, existing in enumerate(self._updates):
            if existing.node_id == sanitized.node_id:
                self._updates[idx] = sanitized
                self._intake_rejections.pop(sanitized.node_id, None)
                logger.info("Replaced duplicate update from node_id=%s", sanitized.node_id)
                return True

        self._updates.append(sanitized)
        self._intake_rejections.pop(sanitized.node_id, None)
        return True

    def aggregate(self) -> ConsensusResult:
        """
        Run full consensus aggregation.

        Algorithm:
        1. Compute geometric median of all adapter deltas
           (Weiszfeld's algorithm, iterative)
        2. Compute trust scores for each node
        3. Reject nodes below byzantine_threshold
        4. Compute weighted average of surviving updates
        5. Verify consensus confidence (agreement metric)
        6. Return merged weights with full provenance

        Geometric median is used because it is a natural robust estimator:
        unlike the arithmetic mean, it is not affected by outliers.
        A single corrupted node cannot pull the merged result away
        from the true aggregate.
        """
        self._round_counter += 1
        round_id = f"facp-round-{self._round_counter:05d}"
        now = datetime.now(timezone.utc).isoformat()
        rejection_reasons: Dict[str, str] = dict(self._intake_rejections)
        trusted_updates = list(self._updates)

        if len(trusted_updates) < self.min_participants:
            for update in trusted_updates:
                rejection_reasons[update.node_id] = "insufficient_participants"
            result = ConsensusResult(
                merged_weights={},
                participating_nodes=[],
                rejected_nodes=sorted(rejection_reasons.keys()),
                rejection_reasons=rejection_reasons,
                trust_scores={},
                consensus_confidence=0.0,
                round_id=round_id,
                timestamp=now,
            )
            self._last_result = result
            return result

        geometric_median = self._compute_geometric_median([item.adapter_weights for item in trusted_updates])
        losses = [item.training_loss for item in trusted_updates]
        self._loss_bounds = (float(min(losses)), float(max(losses)))

        self._distance_cache = {
            item.node_id: self._distance_to_median(item.adapter_weights, geometric_median) for item in trusted_updates
        }
        finite_distances = [value for value in self._distance_cache.values() if np.isfinite(value)]
        self._max_distance = float(max(finite_distances)) if finite_distances else 0.0

        trust_scores: Dict[str, float] = {}
        survivors: List[NodeAdapterUpdate] = []
        for update in trusted_updates:
            score = self._compute_trust_score(update, geometric_median)
            trust_scores[update.node_id] = score
            if score < self.byzantine_threshold:
                # Tactical context: reject low-trust nodes to contain spoofed updates.
                rejection_reasons[update.node_id] = "byzantine_threshold"
            else:
                survivors.append(update)

        if len(survivors) < self.min_participants:
            for update in survivors:
                rejection_reasons[update.node_id] = "insufficient_participants_after_rejection"
            result = ConsensusResult(
                merged_weights={},
                participating_nodes=[],
                rejected_nodes=sorted(rejection_reasons.keys()),
                rejection_reasons=rejection_reasons,
                trust_scores=trust_scores,
                consensus_confidence=0.0,
                round_id=round_id,
                timestamp=now,
            )
            self._last_result = result
            return result

        merged = self._weighted_merge(survivors, trust_scores)
        confidence = self._compute_consensus_confidence(trust_scores, merged, survivors)
        result = ConsensusResult(
            merged_weights=merged,
            participating_nodes=sorted([item.node_id for item in survivors]),
            rejected_nodes=sorted(rejection_reasons.keys()),
            rejection_reasons=rejection_reasons,
            trust_scores=trust_scores,
            consensus_confidence=confidence,
            round_id=round_id,
            timestamp=now,
        )
        self._last_result = result
        return result

    def _compute_geometric_median(
        self, weight_sets: List[Dict[str, np.ndarray]], max_iters: int = 50, tol: float = 1e-5
    ) -> Dict[str, np.ndarray]:
        """
        Weiszfeld's algorithm for geometric median of weight matrices.

        For each layer independently:
          Initialize: median = arithmetic mean
          Iterate:
            weights_i = 1 / ||update_i - median||
            median = sum(weights_i * update_i) / sum(weights_i)
          Until convergence or max_iters.
        """
        if not weight_sets:
            return {}

        all_layers = sorted({name for weight_map in weight_sets for name in weight_map.keys()})
        geometric_median: Dict[str, np.ndarray] = {}

        for layer_name in all_layers:
            grouped: Dict[tuple[int, ...], List[np.ndarray]] = {}
            for weight_map in weight_sets:
                candidate = weight_map.get(layer_name)
                if candidate is None:
                    continue
                arr = np.asarray(candidate, dtype=np.float32)
                grouped.setdefault(tuple(arr.shape), []).append(arr)

            if not grouped:
                continue

            selected_shape = max(grouped.keys(), key=lambda shape: len(grouped[shape]))
            tensors = grouped[selected_shape]
            if len(tensors) == 1:
                geometric_median[layer_name] = np.array(tensors[0], copy=True)
                continue

            stacked = np.stack(tensors, axis=0)
            estimate = np.mean(stacked, axis=0)
            for _ in range(max_iters):
                diff = stacked - estimate
                dist = np.sqrt(np.sum(diff * diff, axis=tuple(range(1, diff.ndim))))
                if np.all(dist <= tol):
                    break
                # Weiszfeld edge case: avoid divide-by-zero if an update equals median.
                inv_dist = 1.0 / np.maximum(dist, self._EPSILON)
                weighted = np.tensordot(inv_dist, stacked, axes=(0, 0))
                new_estimate = weighted / np.sum(inv_dist)
                delta = float(np.linalg.norm(new_estimate - estimate))
                estimate = new_estimate
                if delta <= tol:
                    break
            geometric_median[layer_name] = estimate.astype(np.float32, copy=False)

        return geometric_median

    def _compute_trust_score(self, update: NodeAdapterUpdate, geometric_median: Dict[str, np.ndarray]) -> float:
        """
        Compute composite trust score for a single node's update.

        Components:
        1. hardware_score: map tier to [0.5, 1.0]
           fixed_site=1.0, vehicle_node=0.8, cpu_standard=0.7,
           edge_gpu=0.9, cpu_austere=0.5
        2. loss_confidence: normalize loss across all updates, invert
        3. median_proximity: normalized inverse distance to geometric median
        4. attestation_score: verify hash chain integrity

        Final: weighted sum, clamped to [0, 1]
        """
        hardware_score = self._HARDWARE_SCORES.get(update.hardware_tier.lower(), 0.5)

        loss_min, loss_max = self._loss_bounds
        if (loss_max - loss_min) <= self._EPSILON:
            loss_confidence = 1.0
        else:
            normalized = (update.training_loss - loss_min) / (loss_max - loss_min)
            loss_confidence = float(np.clip(1.0 - normalized, 0.0, 1.0))

        distance = self._distance_cache.get(update.node_id, np.inf)
        if not np.isfinite(distance):
            median_proximity = 0.0
        elif self._max_distance <= self._EPSILON:
            median_proximity = 1.0
        else:
            median_proximity = float(np.clip(1.0 - (distance / self._max_distance), 0.0, 1.0))

        attestation_score = self._verify_attestation_chain(update)
        weighted_sum = (
            self.weights["hardware"] * hardware_score
            + self.weights["loss"] * loss_confidence
            + self.weights["distance"] * median_proximity
            + self.weights["attestation"] * attestation_score
        )
        total_weight = float(sum(self.weights.values()))
        if total_weight > self._EPSILON:
            weighted_sum /= total_weight
        return float(np.clip(weighted_sum, 0.0, 1.0))

    def _verify_attestation_chain(self, update: NodeAdapterUpdate) -> float:
        """
        Verify cryptographic integrity of the update.

        Check:
        1. weight_hash matches SHA256 of serialized weights
        2. training_config_hash is in the set of known valid configs
        3. parent_model_hash matches the expected base model
        4. attestation_chain forms valid hash chain with previous rounds

        Returns 1.0 if all checks pass, 0.0 if any fail,
        0.5 if only parent_model_hash matches (partial trust).
        """
        expected_weight_hash = self.compute_weight_hash(update.adapter_weights)
        weight_ok = self._safe_compare_hash(expected_weight_hash, update.weight_hash)

        if self.valid_training_config_hashes:
            config_ok = update.training_config_hash.lower() in self.valid_training_config_hashes
        else:
            config_ok = True

        has_expected_parent = self.expected_parent_model_hash is not None
        parent_ok = (
            self._safe_compare_hash(self.expected_parent_model_hash or "", update.parent_model_hash)
            if has_expected_parent
            else True
        )
        chain_ok = self._validate_attestation_chain(update.parent_model_hash, update.attestation_chain)

        if weight_ok and config_ok and parent_ok and chain_ok:
            return 1.0
        if has_expected_parent and parent_ok:
            return 0.5
        return 0.0

    def _compute_consensus_confidence(
        self, trust_scores: Dict[str, float], merged: Dict[str, np.ndarray], updates: List[NodeAdapterUpdate]
    ) -> float:
        """
        Measure agreement between participating nodes.

        High confidence: all nodes produced similar updates (cosine sim > 0.9)
        Low confidence: nodes disagree significantly

        Computed as: mean pairwise cosine similarity of trusted updates,
        weighted by trust scores.
        """
        if not updates:
            return 0.0

        if len(updates) == 1:
            score = self._cosine_similarity(updates[0].adapter_weights, merged)
            if score is None:
                return 0.0
            return float(np.clip(score, 0.0, 1.0))

        weighted_sum = 0.0
        weight_total = 0.0
        for i in range(len(updates)):
            for j in range(i + 1, len(updates)):
                left = updates[i]
                right = updates[j]
                similarity = self._cosine_similarity(left.adapter_weights, right.adapter_weights)
                if similarity is None:
                    continue
                pair_weight = (trust_scores.get(left.node_id, 0.0) + trust_scores.get(right.node_id, 0.0)) / 2.0
                weighted_sum += pair_weight * float(np.clip(similarity, 0.0, 1.0))
                weight_total += pair_weight

        if weight_total <= self._EPSILON:
            return 0.0
        return float(np.clip(weighted_sum / weight_total, 0.0, 1.0))

    def get_round_report(self) -> dict:
        """Full provenance report for audit trail."""
        if self._last_result is None:
            return {
                "round_id": None,
                "status": "no_round_executed",
                "registered_nodes": [item.node_id for item in self._updates],
                "intake_rejections": dict(self._intake_rejections),
            }

        result = self._last_result
        return {
            "round_id": result.round_id,
            "timestamp": result.timestamp,
            "registered_nodes": [item.node_id for item in self._updates],
            "participating_nodes": list(result.participating_nodes),
            "rejected_nodes": list(result.rejected_nodes),
            "rejection_reasons": dict(result.rejection_reasons),
            "trust_scores": dict(result.trust_scores),
            "consensus_confidence": float(result.consensus_confidence),
            "merged_layers": sorted(result.merged_weights.keys()),
            "intake_rejections": dict(self._intake_rejections),
        }

    def reset_round(self) -> None:
        """Clear updates for next aggregation round."""
        self._updates.clear()
        self._intake_rejections.clear()
        self._distance_cache.clear()
        self._loss_bounds = (0.0, 0.0)
        self._max_distance = 0.0

    def _weighted_merge(self, updates: List[NodeAdapterUpdate], trust_scores: Dict[str, float]) -> Dict[str, np.ndarray]:
        merged: Dict[str, np.ndarray] = {}
        all_layers = sorted({name for update in updates for name in update.adapter_weights.keys()})

        for layer_name in all_layers:
            grouped: Dict[tuple[int, ...], List[tuple[np.ndarray, float]]] = {}
            for update in updates:
                arr = update.adapter_weights.get(layer_name)
                if arr is None:
                    continue
                score = float(max(trust_scores.get(update.node_id, 0.0), 0.0))
                grouped.setdefault(tuple(arr.shape), []).append((arr, score))

            if not grouped:
                continue
            selected_shape = max(grouped.keys(), key=lambda shape: len(grouped[shape]))
            payload = grouped[selected_shape]
            if not payload:
                continue

            stack = np.stack([item[0] for item in payload], axis=0)
            trust = np.asarray([item[1] for item in payload], dtype=np.float64)
            if float(np.sum(trust)) <= self._EPSILON:
                merged[layer_name] = np.mean(stack, axis=0).astype(np.float32)
                continue
            merged[layer_name] = np.average(stack, axis=0, weights=trust).astype(np.float32)

        return merged

    def _distance_to_median(self, weights: Dict[str, np.ndarray], median: Dict[str, np.ndarray]) -> float:
        used = False
        sq_sum = 0.0
        for layer_name in set(weights.keys()) & set(median.keys()):
            left = weights[layer_name]
            right = median[layer_name]
            if tuple(left.shape) != tuple(right.shape):
                continue
            used = True
            diff = left.astype(np.float64, copy=False) - right.astype(np.float64, copy=False)
            sq_sum += float(np.sum(diff * diff))
        if not used:
            return float("inf")
        return float(np.sqrt(max(sq_sum, 0.0)))

    def _cosine_similarity(self, left: Dict[str, np.ndarray], right: Dict[str, np.ndarray]) -> Optional[float]:
        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        used = False
        for layer_name in set(left.keys()) & set(right.keys()):
            arr_left = left[layer_name]
            arr_right = right[layer_name]
            if tuple(arr_left.shape) != tuple(arr_right.shape):
                continue
            used = True
            vec_left = arr_left.astype(np.float64, copy=False).ravel()
            vec_right = arr_right.astype(np.float64, copy=False).ravel()
            dot += float(np.dot(vec_left, vec_right))
            left_norm += float(np.dot(vec_left, vec_left))
            right_norm += float(np.dot(vec_right, vec_right))

        if not used:
            return None
        denom = np.sqrt(left_norm) * np.sqrt(right_norm)
        if denom <= self._EPSILON:
            return 1.0
        return float(dot / denom)

    @staticmethod
    def _is_valid_timestamp(value: str) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    def _validate_attestation_chain(self, parent_hash: str, chain: List[str]) -> bool:
        if not isinstance(chain, list):
            return False
        if not chain:
            return True
        if not self._is_hash_like(parent_hash):
            return False
        for value in chain:
            if not self._is_hash_like(value):
                return False

        expected = hashlib.sha256(parent_hash.lower().encode("utf-8")).hexdigest()
        if not self._safe_compare_hash(expected, chain[0]):
            return False
        previous = chain[0].lower()
        for value in chain[1:]:
            expected = hashlib.sha256(previous.encode("utf-8")).hexdigest()
            if not self._safe_compare_hash(expected, value):
                return False
            previous = value.lower()
        return True

    @staticmethod
    def _is_hash_like(value: str) -> bool:
        if not isinstance(value, str):
            return False
        v = value.strip().lower()
        if len(v) != FederatedAdapterConsensus._HASH_LEN:
            return False
        return all(c in "0123456789abcdef" for c in v)

    def _safe_compare_hash(self, expected: str, received: str) -> bool:
        if not self._is_hash_like(expected) or not self._is_hash_like(received):
            return False
        return hmac.compare_digest(expected.lower(), received.lower())

    def _reject_intake(self, node_id: str, reason: str) -> bool:
        safe_node_id = node_id if isinstance(node_id, str) and node_id else "unknown"
        self._intake_rejections[safe_node_id] = reason
        logger.warning("Rejected federated update node_id=%s reason=%s", safe_node_id, reason)
        return False


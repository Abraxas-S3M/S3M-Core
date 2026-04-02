"""
S3M Autonomous Data Generation Engine
UNCLASSIFIED - FOUO

Enables edge nodes to autonomously generate novel datasets, discover
entity relationships, and build knowledge graphs without central services.

All operations are CPU-native (numpy + sqlite3).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

from src.edge_compute.models import DataGenStrategy, GeneratedDataset

logger = logging.getLogger("s3m.edge.datagen")


class ContrastiveAugmentor:
    """
    Generates hard-negative pairs via embedding-space perturbation.

    Tactical context: harder negatives improve fine-grained separation of
    visually/sensor-similar targets in contested environments.
    """

    def __init__(
        self,
        positive_radius: float = 0.05,
        negative_radius: float = 0.3,
        temperature: float = 0.07,
    ) -> None:
        if positive_radius < 0 or negative_radius < 0:
            raise ValueError("radii must be non-negative")
        if temperature <= 0:
            raise ValueError("temperature must be > 0")
        self.positive_radius = float(positive_radius)
        self.negative_radius = float(negative_radius)
        self.temperature = float(temperature)

    def generate_pairs(self, data: np.ndarray, n_pairs: int = 1000) -> Dict[str, np.ndarray]:
        """Generate contrastive triplets (anchor, positive, negative)."""
        if not isinstance(data, np.ndarray) or data.ndim != 2:
            raise ValueError("data must be a 2D numpy array")
        if len(data) == 0:
            raise ValueError("data must contain at least one sample")
        if not isinstance(n_pairs, int) or n_pairs <= 0:
            raise ValueError("n_pairs must be a positive integer")

        n = len(data)
        indices = np.random.randint(0, n, size=n_pairs)
        anchors = data[indices].astype(np.float32, copy=False)

        pos_noise = np.random.randn(*anchors.shape).astype(np.float32) * self.positive_radius
        positives = anchors + pos_noise

        neg_noise = np.random.randn(*anchors.shape).astype(np.float32) * self.negative_radius
        swap_indices = np.random.randint(0, n, size=n_pairs)
        swap_mask = np.random.binomial(1, 0.3, size=anchors.shape).astype(np.float32)
        negatives = anchors + neg_noise
        negatives = negatives * (1.0 - swap_mask) + data[swap_indices].astype(np.float32) * swap_mask

        return {"anchors": anchors, "positives": positives, "negatives": negatives}

    def contrastive_loss(self, anchors: np.ndarray, positives: np.ndarray, negatives: np.ndarray) -> float:
        """Compute InfoNCE loss as a quality monitor for pair generation."""
        if anchors.shape != positives.shape or anchors.shape != negatives.shape:
            raise ValueError("anchors, positives, and negatives must have matching shapes")
        if anchors.ndim != 2:
            raise ValueError("inputs must be 2D arrays")

        def cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
            a_norm = a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-8)
            b_norm = b / (np.linalg.norm(b, axis=-1, keepdims=True) + 1e-8)
            return (a_norm * b_norm).sum(axis=-1)

        pos_sim = cosine_sim(anchors, positives) / self.temperature
        neg_sim = cosine_sim(anchors, negatives) / self.temperature
        logits = np.stack([pos_sim, neg_sim], axis=-1)
        logits -= logits.max(axis=-1, keepdims=True)
        exp_logits = np.exp(logits)
        loss = -np.log((exp_logits[:, 0] / exp_logits.sum(axis=-1)) + 1e-8)
        return float(loss.mean())


class GenerativeReplay:
    """
    Gaussian-mixture replay to mitigate catastrophic forgetting.

    Tactical context: replay preserves prior adversary signatures while
    adapting to new local edge observations.
    """

    def __init__(self, n_components: int = 5, reg_covar: float = 1e-4) -> None:
        if not isinstance(n_components, int) or n_components <= 0:
            raise ValueError("n_components must be a positive integer")
        if reg_covar <= 0:
            raise ValueError("reg_covar must be > 0")
        self.n_components = n_components
        self.reg_covar = float(reg_covar)
        self._class_stats: Dict[int, Dict[str, Any]] = {}

    def fit_class(self, class_id: int, features: np.ndarray) -> None:
        """Fit a diagonal-covariance GMM approximation for one class."""
        if not isinstance(class_id, int):
            raise ValueError("class_id must be an integer")
        if not isinstance(features, np.ndarray) or features.ndim != 2:
            raise ValueError("features must be a 2D numpy array")
        n_samples, dim = features.shape
        if n_samples == 0 or dim == 0:
            raise ValueError("features must be non-empty")

        k = min(self.n_components, n_samples)
        centroids_idx = np.random.choice(n_samples, size=k, replace=False)
        means = features[centroids_idx].astype(np.float64, copy=True)

        assignments = np.zeros(n_samples, dtype=np.int64)
        for _ in range(20):
            dists = np.array([np.linalg.norm(features - m, axis=-1) for m in means])
            assignments = dists.argmin(axis=0)
            for j in range(k):
                mask = assignments == j
                if mask.any():
                    means[j] = features[mask].mean(axis=0)

        covs: List[np.ndarray] = []
        weights: List[float] = []
        for j in range(k):
            mask = assignments == j
            count = int(mask.sum())
            if count > 1:
                covs.append(features[mask].var(axis=0) + self.reg_covar)
            else:
                covs.append(np.full((dim,), self.reg_covar, dtype=np.float64))
            weights.append(float(count))

        total = float(sum(weights))
        if total <= 0:
            weights = [1.0 / k] * k
        else:
            weights = [w / total for w in weights]

        self._class_stats[class_id] = {
            "means": [m.tolist() for m in means],
            "covs": [c.tolist() for c in covs],
            "weights": weights,
        }

    def replay(self, class_id: int, n_samples: int) -> np.ndarray:
        """Generate synthetic samples for one class."""
        if class_id not in self._class_stats:
            raise ValueError(f"class {class_id} is not fitted")
        if not isinstance(n_samples, int) or n_samples <= 0:
            raise ValueError("n_samples must be a positive integer")

        stats = self._class_stats[class_id]
        means = [np.asarray(m, dtype=np.float64) for m in stats["means"]]
        covs = [np.asarray(c, dtype=np.float64) for c in stats["covs"]]
        weights = np.asarray(stats["weights"], dtype=np.float64)
        weights = weights / weights.sum()

        components = np.random.choice(len(weights), size=n_samples, p=weights)
        samples = [np.random.normal(means[idx], np.sqrt(covs[idx])) for idx in components]
        return np.asarray(samples, dtype=np.float32)

    def replay_all(self, n_per_class: int = 100) -> Tuple[np.ndarray, np.ndarray]:
        """Replay all fitted classes into a balanced synthetic batch."""
        if not self._class_stats:
            raise ValueError("no classes fitted")
        if not isinstance(n_per_class, int) or n_per_class <= 0:
            raise ValueError("n_per_class must be a positive integer")

        all_features: List[np.ndarray] = []
        all_labels: List[int] = []
        for class_id in sorted(self._class_stats.keys()):
            features = self.replay(class_id, n_per_class)
            all_features.append(features)
            all_labels.extend([class_id] * n_per_class)
        return np.concatenate(all_features, axis=0), np.asarray(all_labels, dtype=np.int64)

    @property
    def fitted_classes(self) -> List[int]:
        return sorted(self._class_stats.keys())


class ActiveLearner:
    """
    Active sampling engine with Expected Model Change (EMC) support.

    Tactical context: prioritize labels expected to shift mission model
    behavior the most when bandwidth for human review is limited.
    """

    def __init__(self, strategy: str = "uncertainty") -> None:
        self.strategy = strategy

    def select(
        self,
        unlabeled_x: np.ndarray,
        model_probs: np.ndarray,
        batch_size: int = 500,
        model_gradients: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Select most informative sample indices from unlabeled pool."""
        if not isinstance(unlabeled_x, np.ndarray) or unlabeled_x.ndim != 2:
            raise ValueError("unlabeled_x must be a 2D numpy array")
        if not isinstance(model_probs, np.ndarray) or model_probs.ndim != 2:
            raise ValueError("model_probs must be a 2D numpy array")
        if len(unlabeled_x) != len(model_probs):
            raise ValueError("unlabeled_x and model_probs must have same row count")
        if not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if model_gradients is not None:
            if not isinstance(model_gradients, np.ndarray) or model_gradients.ndim != 2:
                raise ValueError("model_gradients must be a 2D numpy array when provided")
            if len(model_gradients) != len(unlabeled_x):
                raise ValueError("model_gradients row count must match unlabeled_x")

        n = len(unlabeled_x)
        if n == 0:
            return np.array([], dtype=np.int64)
        batch_size = min(batch_size, n)

        if self.strategy == "uncertainty":
            scores = self._uncertainty_scores(model_probs)
        elif self.strategy == "diversity":
            scores = self._diversity_scores(unlabeled_x)
        elif self.strategy == "expected_model_change":
            if model_gradients is not None:
                scores = np.linalg.norm(model_gradients, axis=-1)
            else:
                # Tactical EMC approximation: combine uncertainty and margin gap.
                entropy = self._uncertainty_scores(model_probs)
                sorted_probs = np.sort(model_probs, axis=-1)
                margin = sorted_probs[:, -1] - sorted_probs[:, -2] if model_probs.shape[1] > 1 else sorted_probs[:, -1]
                scores = entropy * (1.0 - margin)
        else:
            scores = self._uncertainty_scores(model_probs)

        selected = np.argsort(scores)[-batch_size:]
        return selected.astype(np.int64)

    @staticmethod
    def _uncertainty_scores(probs: np.ndarray) -> np.ndarray:
        clipped = np.clip(probs, 1e-10, 1.0)
        return -np.sum(clipped * np.log(clipped), axis=-1)

    @staticmethod
    def _diversity_scores(features: np.ndarray) -> np.ndarray:
        n = len(features)
        subset_size = min(500, n)
        subset_idx = np.random.choice(n, size=subset_size, replace=False)
        subset = features[subset_idx]
        diffs = features[:, None, :] - subset[None, :, :]
        return np.linalg.norm(diffs, axis=-1).mean(axis=-1)


class KnowledgeGraphBuilder:
    """
    SQLite-backed knowledge graph with PMI-based edge discovery.

    Tactical context: links entities and co-occurrence relations locally so
    edge nodes can build actionable intelligence without external APIs.
    """

    def __init__(self, db_path: str = "data/edge/knowledge.db") -> None:
        if not isinstance(db_path, str) or not db_path.strip():
            raise ValueError("db_path must be a non-empty string")
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'unknown',
                embedding_hash TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, entity_type)
            );
            CREATE INDEX IF NOT EXISTS idx_entity_name ON entities(name);
            CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type);

            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES entities(id),
                target_id TEXT NOT NULL REFERENCES entities(id),
                relation_type TEXT NOT NULL DEFAULT 'co_occurs',
                confidence REAL DEFAULT 0.0,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_edge_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edge_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edge_relation ON edges(relation_type);

            CREATE TABLE IF NOT EXISTS co_occurrence (
                entity_a TEXT NOT NULL,
                entity_b TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (entity_a, entity_b)
            );
            """
        )
        self._conn.commit()

    def add_entity(
        self,
        name: str,
        entity_type: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, bool]:
        """Insert or retrieve an entity. Returns (entity_id, created_new)."""
        clean_name = str(name).strip()
        clean_type = str(entity_type).strip() or "unknown"
        if not clean_name:
            raise ValueError("name must be non-empty")

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id FROM entities WHERE name = ? AND entity_type = ?",
            (clean_name, clean_type),
        )
        row = cursor.fetchone()
        if row:
            return row[0], False

        entity_id = str(uuid4())
        cursor.execute(
            "INSERT INTO entities (id, name, entity_type, metadata) VALUES (?, ?, ?, ?)",
            (entity_id, clean_name, clean_type, json.dumps(metadata or {})),
        )
        self._conn.commit()
        return entity_id, True

    def _edge_exists(self, source_id: str, target_id: str, relation_type: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM edges
            WHERE source_id = ? AND target_id = ? AND relation_type = ?
            LIMIT 1
            """,
            (source_id, target_id, relation_type),
        )
        return cursor.fetchone() is not None

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str = "co_occurs",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create a directed edge between entities, skipping duplicates."""
        if not source_id or not target_id:
            raise ValueError("source_id and target_id are required")
        if source_id == target_id:
            return None
        if not relation_type:
            raise ValueError("relation_type must be non-empty")
        if self._edge_exists(source_id, target_id, relation_type):
            return None

        edge_id = str(uuid4())
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO edges (id, source_id, target_id, relation_type, confidence, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (edge_id, source_id, target_id, relation_type, float(confidence), json.dumps(metadata or {})),
        )
        self._conn.commit()
        return edge_id

    def record_co_occurrence(self, entity_a: str, entity_b: str) -> None:
        """Increment co-occurrence count for a pair."""
        a = str(entity_a).strip()
        b = str(entity_b).strip()
        if not a or not b or a == b:
            return
        a, b = sorted([a, b])
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO co_occurrence (entity_a, entity_b, count)
            VALUES (?, ?, 1)
            ON CONFLICT(entity_a, entity_b) DO UPDATE SET count = count + 1
            """,
            (a, b),
        )
        self._conn.commit()

    def compute_pmi_edges(self, min_count: int = 3, min_pmi: float = 1.0) -> int:
        """Discover new PMI edges and return count created."""
        if not isinstance(min_count, int) or min_count <= 0:
            raise ValueError("min_count must be a positive integer")
        if not isinstance(min_pmi, (int, float)):
            raise ValueError("min_pmi must be numeric")

        cursor = self._conn.cursor()
        cursor.execute("SELECT SUM(count) FROM co_occurrence")
        total = float(cursor.fetchone()[0] or 1.0)

        cursor.execute(
            """
            SELECT entity, SUM(cnt) FROM (
                SELECT entity_a AS entity, count AS cnt FROM co_occurrence
                UNION ALL
                SELECT entity_b AS entity, count AS cnt FROM co_occurrence
            ) GROUP BY entity
            """
        )
        marginals = {str(row[0]): float(row[1]) for row in cursor.fetchall()}

        cursor.execute(
            "SELECT entity_a, entity_b, count FROM co_occurrence WHERE count >= ?",
            (min_count,),
        )
        new_edges = 0
        for entity_a, entity_b, count_value in cursor.fetchall():
            count = float(count_value)
            p_ab = count / total
            p_a = marginals.get(entity_a, 1.0) / total
            p_b = marginals.get(entity_b, 1.0) / total
            pmi = float(np.log2((p_ab / (p_a * p_b + 1e-10)) + 1e-10))
            if pmi < float(min_pmi):
                continue

            cursor.execute("SELECT id FROM entities WHERE name = ?", (entity_a,))
            row_a = cursor.fetchone()
            cursor.execute("SELECT id FROM entities WHERE name = ?", (entity_b,))
            row_b = cursor.fetchone()
            if not row_a or not row_b:
                continue

            # Directed edge is sufficient for graph traversal; reverse duplication
            # is intentionally avoided to limit tactical memory growth on edge nodes.
            edge_id = self.add_edge(
                row_a[0],
                row_b[0],
                relation_type="pmi_association",
                confidence=pmi,
                metadata={"co_occurrence_count": int(count), "pmi": pmi},
            )
            if edge_id:
                new_edges += 1

        logger.info("PMI discovery created %d edges", new_edges)
        return new_edges

    def query_neighbors(self, entity_name: str, max_hops: int = 1) -> List[Dict[str, Any]]:
        """Return neighboring entities up to max_hops from entity_name."""
        if not isinstance(entity_name, str) or not entity_name.strip():
            return []
        if not isinstance(max_hops, int) or max_hops <= 0:
            raise ValueError("max_hops must be a positive integer")

        cursor = self._conn.cursor()
        cursor.execute("SELECT id FROM entities WHERE name = ?", (entity_name.strip(),))
        row = cursor.fetchone()
        if not row:
            return []

        visited = {row[0]}
        frontier = [row[0]]
        results: List[Dict[str, Any]] = []

        for hop in range(max_hops):
            next_frontier: List[str] = []
            for entity_id in frontier:
                cursor.execute(
                    """
                    SELECT e.id, e.name, e.entity_type, ed.relation_type, ed.confidence
                    FROM edges ed JOIN entities e ON e.id = ed.target_id
                    WHERE ed.source_id = ?
                    UNION
                    SELECT e.id, e.name, e.entity_type, ed.relation_type, ed.confidence
                    FROM edges ed JOIN entities e ON e.id = ed.source_id
                    WHERE ed.target_id = ?
                    """,
                    (entity_id, entity_id),
                )
                for neighbor_id, name, entity_type, relation_type, confidence in cursor.fetchall():
                    if neighbor_id in visited:
                        continue
                    visited.add(neighbor_id)
                    next_frontier.append(neighbor_id)
                    results.append(
                        {
                            "id": neighbor_id,
                            "name": name,
                            "entity_type": entity_type,
                            "relation": relation_type,
                            "confidence": float(confidence),
                            "hops": hop + 1,
                        }
                    )
            frontier = next_frontier
            if not frontier:
                break

        return results

    def stats(self) -> Dict[str, int]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entities")
        entities = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM edges")
        edges = int(cursor.fetchone()[0])
        return {"entities": entities, "edges": edges}

    def close(self) -> None:
        self._conn.close()


class DataGenerationEngine:
    """
    Orchestrates autonomous data generation strategies on edge nodes.
    """

    def __init__(
        self,
        output_dir: str = "data/edge/generated/",
        kg_db_path: str = "data/edge/knowledge.db",
    ) -> None:
        if not isinstance(output_dir, str) or not output_dir.strip():
            raise ValueError("output_dir must be a non-empty string")
        if not isinstance(kg_db_path, str) or not kg_db_path.strip():
            raise ValueError("kg_db_path must be a non-empty string")

        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.contrastive = ContrastiveAugmentor()
        self.replay = GenerativeReplay()
        self.active_learner = ActiveLearner(strategy="expected_model_change")
        self.knowledge_graph = KnowledgeGraphBuilder(db_path=kg_db_path)
        self._generated: List[GeneratedDataset] = []
        logger.info("DataGenerationEngine initialized output=%s", output_dir)

    def generate_contrastive_dataset(self, data: np.ndarray, n_pairs: int = 5000) -> GeneratedDataset:
        """Generate contrastive triplets and persist to .npz."""
        pairs = self.contrastive.generate_pairs(data, n_pairs)
        loss = self.contrastive.contrastive_loss(pairs["anchors"], pairs["positives"], pairs["negatives"])

        file_name = f"contrastive_{uuid4().hex[:8]}.npz"
        file_path = os.path.join(self.output_dir, file_name)
        np.savez_compressed(file_path, **pairs)

        dataset = GeneratedDataset(
            strategy=DataGenStrategy.CONTRASTIVE,
            record_count=n_pairs,
            file_path=file_path,
            file_size_bytes=os.path.getsize(file_path),
            schema={"anchors": "float32", "positives": "float32", "negatives": "float32"},
        )
        self._generated.append(dataset)
        logger.info("Contrastive dataset generated pairs=%d infonce=%.4f", n_pairs, loss)
        return dataset

    def generate_replay_dataset(
        self,
        class_features: Dict[int, np.ndarray],
        n_per_class: int = 500,
    ) -> GeneratedDataset:
        """Fit per-class replay model and persist synthetic class-balanced data."""
        if not isinstance(class_features, dict) or not class_features:
            raise ValueError("class_features must be a non-empty dictionary")
        for class_id, features in class_features.items():
            self.replay.fit_class(int(class_id), features)

        features, labels = self.replay.replay_all(n_per_class)
        file_name = f"replay_{uuid4().hex[:8]}.npz"
        file_path = os.path.join(self.output_dir, file_name)
        np.savez_compressed(file_path, features=features, labels=labels)

        dataset = GeneratedDataset(
            strategy=DataGenStrategy.GENERATIVE_REPLAY,
            record_count=int(len(features)),
            file_path=file_path,
            file_size_bytes=os.path.getsize(file_path),
            schema={"features": "float32", "labels": "int64"},
        )
        self._generated.append(dataset)
        logger.info("Replay dataset generated samples=%d classes=%d", len(features), len(class_features))
        return dataset

    def run_active_learning_selection(
        self,
        unlabeled_x: np.ndarray,
        model_probs: np.ndarray,
        batch_size: int = 500,
        model_gradients: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Select sample indices for high-value labeling."""
        return self.active_learner.select(
            unlabeled_x=unlabeled_x,
            model_probs=model_probs,
            batch_size=batch_size,
            model_gradients=model_gradients,
        )

    def ingest_entities(
        self,
        entity_records: List[Dict[str, str]],
        co_occurrence_window: int = 5,
    ) -> int:
        """Ingest entities and update sliding-window co-occurrence stats."""
        if not isinstance(entity_records, list):
            raise ValueError("entity_records must be a list")
        if not isinstance(co_occurrence_window, int) or co_occurrence_window <= 0:
            raise ValueError("co_occurrence_window must be a positive integer")

        added = 0
        names_window: List[str] = []
        for record in entity_records:
            if not isinstance(record, dict):
                continue
            name = str(record.get("name", "")).strip()
            entity_type = str(record.get("type", "unknown")).strip() or "unknown"
            if not name:
                continue
            _, is_new = self.knowledge_graph.add_entity(name, entity_type, metadata=record)
            if is_new:
                added += 1
            for prev_name in names_window[-co_occurrence_window:]:
                if prev_name != name:
                    self.knowledge_graph.record_co_occurrence(name, prev_name)
            names_window.append(name)

        logger.info("Ingested entity records=%d newly_added=%d", len(entity_records), added)
        return added

    def discover_relationships(self, min_count: int = 3, min_pmi: float = 1.0) -> int:
        """Create PMI-based entity relationship edges."""
        return self.knowledge_graph.compute_pmi_edges(min_count=min_count, min_pmi=min_pmi)

    def list_generated(self) -> List[GeneratedDataset]:
        return list(self._generated)

    def health_check(self) -> Dict[str, Any]:
        return {
            "datasets_generated": len(self._generated),
            "knowledge_graph": self.knowledge_graph.stats(),
            "replay_classes_fitted": len(self.replay.fitted_classes),
            "output_dir": self.output_dir,
        }

    def close(self) -> None:
        self.knowledge_graph.close()


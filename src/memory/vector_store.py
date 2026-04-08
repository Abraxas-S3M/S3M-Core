"""
FAISS-backed vector store for offline semantic retrieval workflows.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import faiss  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - dependency may be missing in minimal test images
    faiss = None


class FaissVectorStore:
    """Thread-safe FAISS wrapper using inner-product search on normalized vectors."""

    def __init__(self, dimension: int, training_log_path: Optional[str | Path] = None) -> None:
        if faiss is None:
            raise RuntimeError("faiss is not available; install faiss-cpu or faiss-gpu")
        if not isinstance(dimension, int) or dimension <= 0:
            raise ValueError("dimension must be a positive integer")
        self._dimension = int(dimension)
        self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(self._dimension))
        self._lock = Lock()
        self._id_to_numeric: Dict[str, int] = {}
        self._numeric_to_id: Dict[int, str] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._next_numeric_id = 1
        self._training_log_path = Path(training_log_path) if training_log_path else None

    @property
    def dimension(self) -> int:
        return self._dimension

    def add(self, id: str, embedding: np.ndarray) -> None:
        """Insert or replace one embedding by external id."""
        external_id = self._validate_id(id)
        vector = self._normalize_vector(embedding)
        with self._lock:
            numeric_id = self._id_to_numeric.get(external_id)
            if numeric_id is None:
                numeric_id = self._next_numeric_id
                self._next_numeric_id += 1
                self._id_to_numeric[external_id] = numeric_id
                self._numeric_to_id[numeric_id] = external_id
            else:
                self._index.remove_ids(np.asarray([numeric_id], dtype=np.int64))

            self._index.add_with_ids(vector.reshape(1, -1), np.asarray([numeric_id], dtype=np.int64))
            self._metadata[external_id] = {"id": external_id}
            self._log_training_sample(external_id, vector, self._metadata[external_id])

    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search nearest vectors by normalized inner product."""
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        vector = self._normalize_vector(query_embedding)
        with self._lock:
            if int(self._index.ntotal) <= 0:
                return []
            k = min(top_k, int(self._index.ntotal))
            scores, ids = self._index.search(vector.reshape(1, -1), k)
            results: List[Dict[str, Any]] = []
            for score, numeric_id in zip(scores[0], ids[0]):
                if int(numeric_id) < 0:
                    continue
                external_id = self._numeric_to_id.get(int(numeric_id))
                if not external_id:
                    continue
                results.append(
                    {
                        "id": external_id,
                        "score": float(score),
                        "metadata": dict(self._metadata.get(external_id, {})),
                    }
                )
            return results

    def save(self, path: str | Path) -> None:
        """Persist FAISS index and sidecar metadata to local disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            faiss.write_index(self._index, str(target))
            payload = {
                "dimension": self._dimension,
                "id_to_numeric": self._id_to_numeric,
                "metadata": self._metadata,
                "next_numeric_id": self._next_numeric_id,
                "training_log_path": str(self._training_log_path) if self._training_log_path else None,
            }
            self._sidecar_path(target).write_text(
                json.dumps(payload, ensure_ascii=True, sort_keys=True),
                encoding="utf-8",
            )

    @classmethod
    def load(cls, path: str | Path) -> "FaissVectorStore":
        """Load a persisted FAISS index and associated metadata sidecar."""
        if faiss is None:
            raise RuntimeError("faiss is not available; install faiss-cpu or faiss-gpu")
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"index file not found: {target}")

        index = faiss.read_index(str(target))
        sidecar_path = cls._sidecar_path(target)
        sidecar: Dict[str, Any] = {}
        if sidecar_path.exists():
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

        store = cls(
            dimension=int(getattr(index, "d", sidecar.get("dimension", 0))),
            training_log_path=sidecar.get("training_log_path"),
        )
        with store._lock:
            store._index = index
            id_to_numeric = {
                str(key): int(value)
                for key, value in dict(sidecar.get("id_to_numeric", {})).items()
            }
            store._id_to_numeric = id_to_numeric
            store._numeric_to_id = {int(value): str(key) for key, value in id_to_numeric.items()}
            store._metadata = {
                str(key): dict(value) if isinstance(value, dict) else {"id": str(key)}
                for key, value in dict(sidecar.get("metadata", {})).items()
            }
            store._next_numeric_id = int(
                sidecar.get("next_numeric_id", max([0, *store._numeric_to_id.keys()]) + 1)
            )
        return store

    @staticmethod
    def _sidecar_path(index_path: Path) -> Path:
        suffix = index_path.suffix or ".index"
        return index_path.with_suffix(f"{suffix}.meta.json")

    @staticmethod
    def _validate_id(id: str) -> str:
        if not isinstance(id, str) or not id.strip():
            raise ValueError("id must be a non-empty string")
        return id.strip()

    def _normalize_vector(self, embedding: np.ndarray) -> np.ndarray:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if vector.shape[0] != self._dimension:
            raise ValueError(
                f"embedding dimension mismatch: expected {self._dimension}, got {vector.shape[0]}"
            )
        norm = float(np.linalg.norm(vector))
        if norm <= 0.0:
            raise ValueError("embedding norm must be greater than zero")
        return vector / norm

    def _log_training_sample(
        self,
        sample_id: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record embedding samples for CPU adaptation training pipelines."""
        try:
            from src.training.cpu_adaptation.stream_learner import (
                log_embedding_training_sample,
            )

            log_embedding_training_sample(
                sample_id=sample_id,
                embedding=embedding.tolist(),
                metadata=dict(metadata or {}),
                output_path=self._training_log_path,
            )
        except Exception:
            # Tactical continuity: retrieval must continue even if logging fails.
            return

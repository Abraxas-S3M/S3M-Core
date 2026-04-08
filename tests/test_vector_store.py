from __future__ import annotations

import json

import numpy as np
import pytest

faiss = pytest.importorskip("faiss")

from src.memory.vector_store import FaissVectorStore


def test_faiss_vector_store_add_search_save_load(tmp_path) -> None:
    store = FaissVectorStore(dimension=3)
    store.add("alpha", np.array([1.0, 0.0, 0.0], dtype=np.float32))
    store.add("bravo", np.array([0.0, 1.0, 0.0], dtype=np.float32))

    hits = store.search(np.array([0.9, 0.1, 0.0], dtype=np.float32), top_k=2)
    assert hits
    assert hits[0]["id"] == "alpha"
    assert hits[0]["score"] >= hits[-1]["score"]

    index_path = tmp_path / "memory.index"
    store.save(index_path)
    loaded = FaissVectorStore.load(index_path)
    loaded_hits = loaded.search(np.array([0.0, 1.0, 0.0], dtype=np.float32), top_k=1)
    assert loaded_hits[0]["id"] == "bravo"


def test_faiss_vector_store_logs_training_samples(tmp_path) -> None:
    log_path = tmp_path / "embedding_stream.jsonl"
    store = FaissVectorStore(dimension=3, training_log_path=log_path)
    store.add("concept-1", np.array([0.0, 0.4, 0.9], dtype=np.float32))
    assert log_path.exists()
    rows = log_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["sampleId"] == "concept-1"
    assert payload["metadata"]["id"] == "concept-1"

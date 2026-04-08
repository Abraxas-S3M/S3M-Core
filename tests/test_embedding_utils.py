from __future__ import annotations

import numpy as np

from src.memory import embedding_utils


def test_generate_embeddings_tfidf_fallback_shape_and_norm(monkeypatch) -> None:
    monkeypatch.setattr(embedding_utils, "_augment_with_llm_core", lambda texts, model: None)
    matrix = embedding_utils.generate_embeddings(
        ["armored convoy moved north", "drone swarm observed near coast"]
    )
    assert matrix.shape[0] == 2
    assert matrix.shape[1] >= 1
    norms = np.linalg.norm(matrix, axis=1)
    assert np.allclose(norms, np.ones_like(norms), atol=1e-5)


def test_generate_embedding_single_vector(monkeypatch) -> None:
    monkeypatch.setattr(embedding_utils, "_augment_with_llm_core", lambda texts, model: list(texts))
    vector = embedding_utils.generate_embedding("counter-battery radar activation")
    assert vector.ndim == 1
    assert vector.shape[0] >= 64
    assert abs(float(np.linalg.norm(vector)) - 1.0) < 1e-5

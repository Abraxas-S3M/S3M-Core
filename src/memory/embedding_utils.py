"""
Offline embedding utilities for semantic retrieval and fusion workflows.
"""

from __future__ import annotations

import re
from threading import Lock
from typing import Any, List, Optional, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


_LLM_LOCK = Lock()
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def generate_embedding(text: str, model: str = "phi3-medium") -> np.ndarray:
    """Generate a single normalized embedding vector for one text."""
    matrix = generate_embeddings([text], model=model)
    return matrix[0]


def generate_embeddings(
    texts: Sequence[str],
    model: str = "phi3-medium",
    max_features: int = 512,
) -> np.ndarray:
    """
    Generate normalized embeddings for a batch of texts.

    Tactical context: batched numpy operations reduce CPU overhead so edge
    systems can maintain semantic recall under constrained compute budgets.
    """
    if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes)):
        raise ValueError("texts must be a sequence of strings")
    if not texts:
        raise ValueError("texts must contain at least one item")
    clean_texts = [_validate_text(text) for text in texts]

    augmented = _augment_with_llm_core(clean_texts, model=model)
    if augmented is not None:
        dense = _hashing_embeddings(augmented, dim=max(64, int(max_features)))
        return _normalize_rows(dense)

    return _tfidf_embeddings(clean_texts, max_features=max(64, int(max_features)))


def _augment_with_llm_core(texts: Sequence[str], model: str) -> Optional[List[str]]:
    try:
        from src.llm_core.engine_registry import TaskDomain
        from src.llm_core.orchestrator import Orchestrator, QueryRequest
    except Exception:
        return None

    orchestrator = Orchestrator()
    augmented: List[str] = []
    any_success = False
    for text in texts:
        keywords = _extract_tactical_keywords(
            orchestrator=orchestrator,
            query_request_cls=QueryRequest,
            task_domain=TaskDomain,
            text=text,
            model=model,
        )
        if keywords:
            any_success = True
            augmented.append(f"{text}\n{' '.join(keywords)}")
        else:
            augmented.append(text)
    if not any_success:
        return None
    return augmented


def _extract_tactical_keywords(
    orchestrator: Any,
    query_request_cls: Any,
    task_domain: Any,
    text: str,
    model: str,
) -> List[str]:
    prompt = (
        f"Model hint: {model}. Extract up to 24 tactical semantic tags from the text. "
        "Return only comma-separated lowercase tokens without explanation.\n"
        f"Text:\n{text[:2000]}"
    )
    with _LLM_LOCK:
        response = orchestrator.process(
            query_request_cls(prompt=prompt, domain=task_domain.REASONING)
        )
    raw = str(getattr(response, "text", "") or "").strip()
    lowered = raw.lower()
    if not raw or "pending" in lowered or "not yet loaded" in lowered or "[error]" in lowered:
        return []
    tokens: List[str] = []
    for piece in re.split(r"[,;\n|]+", raw):
        token = re.sub(r"[^a-z0-9_\- ]+", "", piece.lower()).strip()
        if token and token not in tokens:
            tokens.append(token.replace(" ", "_"))
        if len(tokens) >= 24:
            break
    return tokens


def _hashing_embeddings(texts: Sequence[str], dim: int) -> np.ndarray:
    matrix = np.zeros((len(texts), dim), dtype=np.float32)
    for row, text in enumerate(texts):
        tokens = _TOKEN_PATTERN.findall(text.lower())
        if not tokens:
            continue
        hashed = np.fromiter((hash(token) % dim for token in tokens), dtype=np.int64)
        np.add.at(matrix[row], hashed, 1.0)
    return matrix


def _tfidf_embeddings(texts: Sequence[str], max_features: int) -> np.ndarray:
    """
    Build TF-IDF fallback vectors when llm_core engines are unavailable.

    Tactical context: this sparse lexical fallback keeps semantic tooling
    operational in fully air-gapped deployments with no loaded LLM engine.
    """
    vectorizer = TfidfVectorizer(
        max_features=max_features,
        ngram_range=(1, 2),
        lowercase=True,
        dtype=np.float32,
    )
    try:
        sparse = vectorizer.fit_transform(texts)
    except ValueError:
        return _normalize_rows(_hashing_embeddings(texts, dim=max(64, max_features)))
    dense = sparse.toarray().astype(np.float32, copy=False)
    return _normalize_rows(dense)


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    if matrix.ndim != 2:
        raise ValueError("embedding matrix must be 2-dimensional")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms > 0.0, norms, 1.0)
    return matrix / norms


def _validate_text(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("each text item must be a string")
    cleaned = text.strip()
    return cleaned if cleaned else "__empty__"

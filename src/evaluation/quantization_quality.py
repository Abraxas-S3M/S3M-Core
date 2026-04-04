"""Quantization quality checks for edge-ready tactical model deployment."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .latency_bench import _invoke_backend_generate

try:
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    from sklearn.metrics.pairwise import cosine_similarity  # type: ignore

    SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency path
    SKLEARN_AVAILABLE = False
    TfidfVectorizer = None
    cosine_similarity = None

LOGGER = logging.getLogger("s3m.evaluation.quantization_quality")


def _normalize(text: str) -> str:
    return " ".join(str(text).strip().split()).casefold()


def _tokens(text: str) -> list[str]:
    return _normalize(text).split()


def _lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[len(a)][len(b)]


def _rouge_l_f1(candidate: str, reference: str) -> float:
    cand_toks = _tokens(candidate)
    ref_toks = _tokens(reference)
    if not cand_toks and not ref_toks:
        return 1.0
    if not cand_toks or not ref_toks:
        return 0.0

    lcs = _lcs_len(cand_toks, ref_toks)
    precision = lcs / len(cand_toks)
    recall = lcs / len(ref_toks)
    if precision + recall == 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def _safe_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        out: list[float] = []
        for item in value:
            try:
                out.append(float(item))
            except (TypeError, ValueError):
                continue
        return out if out else None
    return None


def _extract_log_probs(backend: Any, model_id: str, prompt: str, output: str) -> list[float] | None:
    method_candidates = ("get_logprobs", "log_probs", "logprobs")
    signatures = (
        ((), {"model_id": model_id, "prompt": prompt, "output": output}),
        ((prompt, output), {"model_id": model_id}),
        ((prompt, output), {}),
        ((), {"prompt": prompt, "output": output}),
    )
    for method_name in method_candidates:
        if not hasattr(backend, method_name):
            continue
        method = getattr(backend, method_name)
        for args, kwargs in signatures:
            try:
                payload = method(*args, **kwargs)
            except TypeError:
                continue
            if isinstance(payload, dict):
                nested = payload.get("log_probs", payload.get("logprobs"))
                values = _safe_float_list(nested)
                if values:
                    return values
            values = _safe_float_list(payload)
            if values:
                return values
    return None


def _perplexity(log_probs: list[float] | None) -> float | None:
    if not log_probs:
        return None
    arr = np.array(log_probs, dtype=float)
    return float(math.exp(-float(np.mean(arr))))


def _cosine_pairs(quant_outputs: list[str], fp16_outputs: list[str]) -> list[float]:
    if not quant_outputs or len(quant_outputs) != len(fp16_outputs):
        return []

    if SKLEARN_AVAILABLE and TfidfVectorizer is not None and cosine_similarity is not None:
        docs: list[str] = []
        for quant_text, fp16_text in zip(quant_outputs, fp16_outputs):
            docs.extend([quant_text, fp16_text])
        matrix = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b").fit_transform(docs)
        sims: list[float] = []
        for idx in range(0, matrix.shape[0], 2):
            sims.append(float(cosine_similarity(matrix[idx], matrix[idx + 1])[0][0]))
        return sims

    all_docs = quant_outputs + fp16_outputs
    tokenized = [_tokens(doc) for doc in all_docs]
    vocab = sorted({token for doc in tokenized for token in doc})
    if not vocab:
        return [1.0 for _ in quant_outputs]
    idx_map = {tok: i for i, tok in enumerate(vocab)}

    df = np.zeros(len(vocab), dtype=float)
    for doc in tokenized:
        for token in set(doc):
            df[idx_map[token]] += 1.0
    idf = np.log((1.0 + len(tokenized)) / (1.0 + df)) + 1.0

    vectors: list[np.ndarray] = []
    for doc in tokenized:
        vec = np.zeros(len(vocab), dtype=float)
        if doc:
            for token in doc:
                vec[idx_map[token]] += 1.0
            vec /= len(doc)
            vec *= idf
        vectors.append(vec)

    sims: list[float] = []
    n = len(quant_outputs)
    for i in range(n):
        a = vectors[i]
        b = vectors[n + i]
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        sims.append(float(np.dot(a, b) / denom) if denom > 0 else 0.0)
    return sims


@dataclass(slots=True)
class QuantQualityResult:
    rouge_l_vs_fp16: float
    cosine_sim_vs_fp16: float
    perplexity_increase_pct: float | None
    sample_count: int
    passed: bool
    violations: list[str] = field(default_factory=list)


class QuantizationQualityBenchmark:
    """Check quantized output fidelity against an fp16 tactical reference."""

    def run(
        self,
        model_id: str,
        quant_backend: Any,
        fp16_backend: Any,
        prompts: list[str],
        thresholds: dict[str, float],
    ) -> QuantQualityResult:
        prompt_list = [p for p in prompts if isinstance(p, str)]
        if not prompt_list:
            return QuantQualityResult(
                rouge_l_vs_fp16=0.0,
                cosine_sim_vs_fp16=0.0,
                perplexity_increase_pct=None,
                sample_count=0,
                passed=False,
                violations=["No prompts provided for quantization-quality benchmark"],
            )

        quant_outputs: list[str] = []
        fp16_outputs: list[str] = []
        rouge_scores: list[float] = []
        ppl_increases: list[float] = []

        for prompt in prompt_list:
            quant_text = _invoke_backend_generate(quant_backend, model_id, prompt)
            fp16_text = _invoke_backend_generate(fp16_backend, model_id, prompt)
            quant_outputs.append(quant_text)
            fp16_outputs.append(fp16_text)
            rouge_scores.append(_rouge_l_f1(quant_text, fp16_text))

            quant_ppl = _perplexity(_extract_log_probs(quant_backend, model_id, prompt, quant_text))
            fp16_ppl = _perplexity(_extract_log_probs(fp16_backend, model_id, prompt, fp16_text))
            if quant_ppl is not None and fp16_ppl is not None and fp16_ppl > 0:
                ppl_increases.append(((quant_ppl - fp16_ppl) / fp16_ppl) * 100.0)

        rouge_l_vs_fp16 = float(np.mean(rouge_scores))
        cosine_scores = _cosine_pairs(quant_outputs, fp16_outputs)
        cosine_sim_vs_fp16 = float(np.mean(cosine_scores)) if cosine_scores else 0.0
        perplexity_increase_pct = float(np.mean(ppl_increases)) if ppl_increases else None

        violations: list[str] = []
        min_rouge = float(thresholds.get("min_rouge_l_vs_fp16", 0.0))
        min_cosine = float(thresholds.get("min_cosine_sim_vs_fp16", 0.0))
        max_perplexity_increase = float(thresholds.get("max_perplexity_increase_pct", float("inf")))

        if rouge_l_vs_fp16 < min_rouge:
            violations.append(
                f"rouge_l_vs_fp16 below threshold ({rouge_l_vs_fp16:.4f} < {min_rouge:.4f})"
            )
        if cosine_sim_vs_fp16 < min_cosine:
            violations.append(
                f"cosine_sim_vs_fp16 below threshold ({cosine_sim_vs_fp16:.4f} < {min_cosine:.4f})"
            )
        if perplexity_increase_pct is not None and perplexity_increase_pct > max_perplexity_increase:
            violations.append(
                "perplexity_increase_pct exceeded threshold "
                f"({perplexity_increase_pct:.2f} > {max_perplexity_increase:.2f})"
            )

        return QuantQualityResult(
            rouge_l_vs_fp16=rouge_l_vs_fp16,
            cosine_sim_vs_fp16=cosine_sim_vs_fp16,
            perplexity_increase_pct=perplexity_increase_pct,
            sample_count=len(prompt_list),
            passed=not violations,
            violations=violations,
        )

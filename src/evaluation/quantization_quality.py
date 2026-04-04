"""Quantization quality benchmark for edge model deployment."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import logging
import math
from typing import Any

try:  # pragma: no cover - optional dependency
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity
except ImportError:  # pragma: no cover - optional dependency
    TfidfVectorizer = None
    sklearn_cosine_similarity = None

logger = logging.getLogger("s3m.evaluation.quantization_quality")


@dataclass(slots=True)
class QuantQualityResult:
    """Quality deltas between quantized and FP16 reference backends."""

    rouge_l_vs_fp16: float
    cosine_sim_vs_fp16: float
    perplexity_increase_pct: float | None
    samples: int
    passed: bool
    violations: list[str] = field(default_factory=list)


def _extract_output_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in ("response", "text", "output", "final_answer", "generated_text"):
            value = output.get(key)
            if isinstance(value, str):
                return value
        return str(output)
    for attr in ("response", "text", "output", "final_answer", "generated_text"):
        value = getattr(output, attr, None)
        if isinstance(value, str):
            return value
    return str(output)


def _invoke_backend(backend: Any, prompt: str) -> str:
    for method_name in ("infer", "generate"):
        method = getattr(backend, method_name, None)
        if callable(method):
            return _extract_output_text(method(prompt))
    if callable(backend):
        return _extract_output_text(backend(prompt))
    raise AttributeError("Backend must implement infer(prompt), generate(prompt), or __call__(prompt)")


def _lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for token_a in a:
        curr = [0]
        for j, token_b in enumerate(b, start=1):
            if token_a == token_b:
                curr.append(prev[j - 1] + 1)
            else:
                curr.append(max(curr[-1], prev[j]))
        prev = curr
    return prev[-1]


def _rouge_l(prediction: str, reference: str) -> float:
    pred_tokens = prediction.strip().split()
    ref_tokens = reference.strip().split()
    if not ref_tokens and not pred_tokens:
        return 1.0
    if not ref_tokens:
        return 0.0
    return float(_lcs_len(pred_tokens, ref_tokens)) / float(len(ref_tokens))


def _manual_cosine_similarity(text_a: str, text_b: str) -> float:
    counts_a = Counter(text_a.split())
    counts_b = Counter(text_b.split())
    if not counts_a and not counts_b:
        return 1.0
    if not counts_a or not counts_b:
        return 0.0
    dot = sum(counts_a[token] * counts_b.get(token, 0) for token in counts_a)
    norm_a = math.sqrt(sum(value * value for value in counts_a.values()))
    norm_b = math.sqrt(sum(value * value for value in counts_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot) / (norm_a * norm_b)


def _cosine_similarity(text_a: str, text_b: str) -> float:
    if TfidfVectorizer is None or sklearn_cosine_similarity is None:
        return _manual_cosine_similarity(text_a, text_b)
    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform([text_a, text_b])
    return float(sklearn_cosine_similarity(matrix[0], matrix[1])[0][0])


def _extract_log_probs(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "log_probs" in value and isinstance(value["log_probs"], list):
            return [float(v) for v in value["log_probs"]]
        if "token_logprobs" in value and isinstance(value["token_logprobs"], list):
            return [float(v) for v in value["token_logprobs"]]
    if isinstance(value, list):
        return [float(v) for v in value]
    return None


def _estimate_perplexity(backend: Any, prompt: str, output: str) -> float | None:
    direct_ppl = getattr(backend, "perplexity", None)
    if callable(direct_ppl):
        return float(direct_ppl(prompt, output))

    for method_name in ("score_log_probs", "log_probs", "score_sequence"):
        method = getattr(backend, method_name, None)
        if callable(method):
            log_probs = _extract_log_probs(method(prompt, output))
            if log_probs:
                return float(math.exp(-sum(log_probs) / len(log_probs)))
    return None


class QuantizationQualityBenchmark:
    """Compare quantized quality against FP16 for tactical output integrity."""

    def __init__(self, thresholds: dict[str, float] | None = None):
        self.thresholds = thresholds or {}

    def run(
        self,
        model_id: str,
        quant_backend: Any,
        fp16_backend: Any,
        prompts: list[str],
    ) -> QuantQualityResult:
        if not prompts:
            raise ValueError("prompts must contain at least one prompt")

        logger.info("Starting quantization quality benchmark for model_id=%s", model_id)

        rouge_scores: list[float] = []
        cosine_scores: list[float] = []
        perplexity_increases: list[float] = []

        for prompt in prompts:
            quant_text = _invoke_backend(quant_backend, prompt)
            fp16_text = _invoke_backend(fp16_backend, prompt)

            rouge_scores.append(_rouge_l(quant_text, fp16_text))
            cosine_scores.append(_cosine_similarity(quant_text, fp16_text))

            quant_ppl = _estimate_perplexity(quant_backend, prompt, quant_text)
            fp16_ppl = _estimate_perplexity(fp16_backend, prompt, fp16_text)
            if quant_ppl is not None and fp16_ppl is not None and fp16_ppl > 0:
                increase_pct = ((quant_ppl - fp16_ppl) / fp16_ppl) * 100.0
                perplexity_increases.append(increase_pct)

        rouge_l_vs_fp16 = sum(rouge_scores) / len(rouge_scores)
        cosine_sim_vs_fp16 = sum(cosine_scores) / len(cosine_scores)
        perplexity_increase_pct = (
            sum(perplexity_increases) / len(perplexity_increases) if perplexity_increases else None
        )

        violations: list[str] = []
        min_rouge = self.thresholds.get("min_rouge_l_vs_fp16")
        min_cosine = self.thresholds.get("min_cosine_sim_vs_fp16")
        max_ppl_increase = self.thresholds.get("max_perplexity_increase_pct")

        if min_rouge is not None and rouge_l_vs_fp16 < float(min_rouge):
            violations.append(
                f"rouge_l_vs_fp16 below minimum: {rouge_l_vs_fp16:.4f} < {float(min_rouge):.4f}"
            )
        if min_cosine is not None and cosine_sim_vs_fp16 < float(min_cosine):
            violations.append(
                f"cosine_sim_vs_fp16 below minimum: {cosine_sim_vs_fp16:.4f} < {float(min_cosine):.4f}"
            )
        if (
            max_ppl_increase is not None
            and perplexity_increase_pct is not None
            and perplexity_increase_pct > float(max_ppl_increase)
        ):
            violations.append(
                "perplexity_increase_pct exceeded maximum: "
                f"{perplexity_increase_pct:.2f} > {float(max_ppl_increase):.2f}"
            )

        passed = not violations
        logger.info(
            "Quantization benchmark finished model_id=%s passed=%s rouge_l=%.4f cosine=%.4f",
            model_id,
            passed,
            rouge_l_vs_fp16,
            cosine_sim_vs_fp16,
        )

        return QuantQualityResult(
            rouge_l_vs_fp16=rouge_l_vs_fp16,
            cosine_sim_vs_fp16=cosine_sim_vs_fp16,
            perplexity_increase_pct=perplexity_increase_pct,
            samples=len(prompts),
            passed=passed,
            violations=violations,
        )

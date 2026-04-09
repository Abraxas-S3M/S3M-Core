"""Grok validation oracle for promotion decisions.

Military/tactical context:
This validation layer prevents low-quality adapters from being promoted to
production. Grok's high-capacity judgment augments deterministic checks on
doctrinal compliance, Arabic fidelity, and structured-report quality.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

from src.storage.b2_connector import B2Connector

logger = logging.getLogger("s3m.training.grok_oracle")

_ARABIC_REGEX = re.compile(r"[\u0600-\u06FF]")
_CODE_FENCE_REGEX = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.IGNORECASE | re.MULTILINE)
_RATING_REGEX = re.compile(r"(?:rating|score)\D*(10|[1-9](?:\.\d+)?)", flags=re.IGNORECASE)


@dataclass
class VerdictRequest:
    artifact_id: str
    engine_id: str
    track: str
    artifact_type: str  # "adapter" | "eval_result" | "generated_text"
    b2_key: str  # BackBlaze object key
    session_id: str
    created_at: str


@dataclass
class Verdict:
    artifact_id: str
    passed: bool
    score: float  # 0.0 to 1.0
    reason: str
    criteria_scores: Dict[str, float]  # per-criterion breakdown
    evaluated_at: str
    oracle_mode: str  # "api" or "offline"


class GrokValidationOracle:
    """Reviews training artifacts using Grok as a quality oracle.

    Military/tactical context:
    This validation layer prevents low-quality adapters from being promoted
    to production. Grok's massive parameter count gives it superior judgment
    on output quality, doctrinal compliance, and Arabic language fidelity.

    IMPORTANT: Grok does NOT run on Hetzner or RunPod. This oracle can
    operate in two modes:
    1. API mode — calls xAI's Grok API (when internet-connected)
    2. Offline mode — uses rule-based heuristics + smaller model scoring
    """

    PENDING_PREFIX = "grok-verdicts/pending/"
    APPROVED_PREFIX = "grok-verdicts/approved/"
    REJECTED_PREFIX = "grok-verdicts/rejected/"

    def __init__(
        self,
        mode: str = "offline",  # "api" or "offline"
        xai_api_key: Optional[str] = None,
        b2_connector: Optional[B2Connector] = None,
    ) -> None:
        normalized_mode = str(mode or "offline").strip().lower()
        if normalized_mode not in {"api", "offline"}:
            raise ValueError("mode must be either 'api' or 'offline'")

        self.mode = normalized_mode
        self.xai_api_key = xai_api_key
        self.b2_connector = b2_connector or B2Connector()
        self.xai_api_url = "https://api.x.ai/v1/chat/completions"
        self.xai_model = "grok-beta"

        self._pending_manifest_keys: dict[str, str] = {}
        self._request_payload_cache: dict[str, dict[str, Any]] = {}
        self._track_cfg_cache: dict[str, dict[str, Any]] = {}

    def scan_pending(self) -> List[VerdictRequest]:
        """Scan grok-verdicts/pending/ in BackBlaze for unreviewed artifacts."""
        requests_found: list[VerdictRequest] = []
        self._pending_manifest_keys.clear()
        self._request_payload_cache.clear()

        for key in self._list_keys(self.PENDING_PREFIX):
            if not key.lower().endswith(".json"):
                continue
            try:
                payload = self._read_json(key)
            except Exception as exc:  # pragma: no cover - defensive parsing
                logger.warning("Skipping unreadable pending payload %s: %s", key, exc)
                continue
            if not isinstance(payload, dict):
                continue
            request = self._payload_to_request(payload, fallback_key=key)
            self._pending_manifest_keys[request.artifact_id] = key
            self._request_payload_cache[request.artifact_id] = payload
            requests_found.append(request)

        requests_found.sort(key=lambda item: item.created_at)
        logger.info("Found %d pending Grok verdict requests", len(requests_found))
        return requests_found

    def evaluate_artifact(self, request: VerdictRequest) -> Verdict:
        """Score a single training artifact.

        Evaluation criteria:
        - Factual consistency (does the output contradict the prompt?)
        - Language quality (Arabic fidelity for saudi_mod track)
        - Format compliance (structured output validity)
        - Doctrinal alignment (for nato track)
        - Degraded-input handling (for ukraine_mod track)

        Returns Verdict with: passed (bool), score (0-1), reason (str)
        """
        if self.mode == "api" and self.xai_api_key:
            try:
                return self._evaluate_api(request)
            except Exception as exc:
                logger.warning("API evaluation failed for %s, falling back offline: %s", request.artifact_id, exc)
        return self._evaluate_offline(request)

    def process_all_pending(self) -> List[Verdict]:
        """Process all pending verdicts and move to approved/rejected."""
        verdicts: list[Verdict] = []
        for request in self.scan_pending():
            verdict = self.evaluate_artifact(request)
            verdicts.append(verdict)
            if verdict.passed:
                self.move_to_approved(request, verdict)
            else:
                self.move_to_rejected(request, verdict)
        return verdicts

    def move_to_approved(self, request: VerdictRequest, verdict: Verdict):
        """Move artifact from pending/ to approved/ in BackBlaze."""
        self._move_request_to_lane(request=request, verdict=verdict, lane="approved")

    def move_to_rejected(self, request: VerdictRequest, verdict: Verdict):
        """Move artifact from pending/ to rejected/ in BackBlaze."""
        self._move_request_to_lane(request=request, verdict=verdict, lane="rejected")

    def promote_approved_adapters(self):
        """Copy approved adapters to the live adapters/ path in BackBlaze.
        This is what Hetzner pulls during its next sync cycle.
        """
        promoted_count = 0
        for key in self._list_keys(self.APPROVED_PREFIX):
            if not key.endswith(".verdict.json"):
                continue
            payload = self._read_json(key)
            if not isinstance(payload, dict):
                continue
            request_payload = payload.get("request", {})
            verdict_payload = payload.get("verdict", {})
            if not isinstance(request_payload, dict) or not isinstance(verdict_payload, dict):
                continue
            if str(request_payload.get("artifact_type", "")) != "adapter":
                continue
            if not bool(verdict_payload.get("passed", False)):
                continue

            source_key = str(request_payload.get("b2_key", ""))
            if "/pending/" in source_key:
                source_key = source_key.replace("/pending/", "/approved/", 1)
            if not source_key:
                continue

            artifact_id = str(request_payload.get("artifact_id", Path(source_key).stem))
            track = str(request_payload.get("track", "shared"))
            engine_id = str(request_payload.get("engine_id", "unknown"))
            filename = Path(source_key).name or f"{artifact_id}.adapter"
            destination_key = f"adapters/{track}/{engine_id}/{filename}"
            self._copy_object(source_key, destination_key)
            promoted_count += 1

        logger.info("Promoted %d approved adapters to live path", promoted_count)

    def _evaluate_offline(self, request: VerdictRequest) -> Verdict:
        track_cfg = self._load_track_config(request.track)
        thresholds = self._extract_thresholds(track_cfg)
        metadata = self._load_session_metadata(request)
        eval_scores = self._extract_eval_scores(metadata)
        sample_text = self._load_sample_text(request, metadata)

        criteria_scores: dict[str, float] = {
            "adapter_integrity": self._score_adapter_integrity(request),
            "factual_consistency": self._score_metric(eval_scores, ("factual_consistency", "consistency", "overall"), 0.55),
            "language_quality": self._score_language_quality(request.track, sample_text, eval_scores),
            "format_compliance": self._score_format_compliance(sample_text, eval_scores),
            "doctrinal_alignment": self._score_doctrinal_alignment(request.track, sample_text, eval_scores),
            "degraded_input_handling": self._score_degraded_input_handling(request.track, sample_text, eval_scores),
            "threshold_compliance": self._score_threshold_compliance(eval_scores, thresholds),
        }

        weights = {
            "adapter_integrity": 0.15,
            "factual_consistency": 0.2,
            "language_quality": 0.15,
            "format_compliance": 0.15,
            "doctrinal_alignment": 0.15,
            "degraded_input_handling": 0.1,
            "threshold_compliance": 0.1,
        }
        score = self._weighted_average(criteria_scores, weights)

        required_score = self._score_metric(thresholds, ("overall",), 0.70)
        critical_failures: list[str] = []
        if request.artifact_type == "adapter" and criteria_scores["adapter_integrity"] < 0.5:
            critical_failures.append("adapter_integrity")
        if request.track == "saudi_mod" and criteria_scores["language_quality"] < 0.45:
            critical_failures.append("language_quality")
        if request.track == "nato" and criteria_scores["doctrinal_alignment"] < 0.45:
            critical_failures.append("doctrinal_alignment")
        if request.track == "ukraine_mod" and criteria_scores["degraded_input_handling"] < 0.45:
            critical_failures.append("degraded_input_handling")

        passed = score >= required_score and criteria_scores["threshold_compliance"] >= 0.5 and not critical_failures
        if passed:
            reason = (
                f"Offline checks passed with score {score:.3f} "
                f"(required {required_score:.3f}) for track {request.track}"
            )
        else:
            reasons = [f"score {score:.3f} below required {required_score:.3f}" if score < required_score else ""]
            if criteria_scores["threshold_compliance"] < 0.5:
                reasons.append("insufficient promotion-threshold compliance from eval metadata")
            if critical_failures:
                reasons.append(f"critical checks failed: {', '.join(sorted(set(critical_failures)))}")
            compact_reason = "; ".join(item for item in reasons if item)
            reason = compact_reason or "Offline quality checks failed"

        return Verdict(
            artifact_id=request.artifact_id,
            passed=passed,
            score=score,
            reason=reason,
            criteria_scores=criteria_scores,
            evaluated_at=self._now_iso(),
            oracle_mode="offline",
        )

    def _evaluate_api(self, request: VerdictRequest) -> Verdict:
        track_cfg = self._load_track_config(request.track)
        thresholds = self._extract_thresholds(track_cfg)
        metadata = self._load_session_metadata(request)
        sample_text = self._load_sample_text(request, metadata)
        prompt = self._build_api_prompt(request, sample_text)

        response = requests.post(
            self.xai_api_url,
            headers={
                "Authorization": f"Bearer {self.xai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.xai_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a strict quality oracle for military training artifacts. "
                            "Return only JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
            },
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        content = self._extract_api_content(body)
        parsed = self._parse_api_payload(content)

        rating = self._clamp(float(parsed.get("rating", 0.0)), 0.0, 10.0)
        score = round(rating / 10.0, 4)
        required_score = self._score_metric(thresholds, ("overall",), 0.70)

        criteria_payload = parsed.get("criteria", {})
        criteria_scores = self._normalize_api_criteria(criteria_payload, score)
        passed = score >= required_score
        reason = str(parsed.get("reason", "")).strip() or "No reasoning returned by Grok API"

        return Verdict(
            artifact_id=request.artifact_id,
            passed=passed,
            score=score,
            reason=reason,
            criteria_scores=criteria_scores,
            evaluated_at=self._now_iso(),
            oracle_mode="api",
        )

    def _build_api_prompt(self, request: VerdictRequest, sample_text: str) -> str:
        sample = sample_text[:2500]
        return (
            "Rate this training artifact on a scale of 1-10 for tactical deployment quality.\n"
            f"artifact_id: {request.artifact_id}\n"
            f"engine_id: {request.engine_id}\n"
            f"track: {request.track}\n"
            f"artifact_type: {request.artifact_type}\n"
            "Criteria: factual consistency, language quality, format compliance, doctrinal alignment,"
            " degraded-input handling.\n"
            "Respond with strict JSON: "
            '{"rating": <1-10>, "reason": "<brief reason>", "criteria": {"factual_consistency": <0-1>,'
            ' "language_quality": <0-1>, "format_compliance": <0-1>, "doctrinal_alignment": <0-1>,'
            ' "degraded_input_handling": <0-1>}}\n'
            f"Sample output:\n{sample}"
        )

    def _move_request_to_lane(self, request: VerdictRequest, verdict: Verdict, lane: str) -> None:
        if lane not in {"approved", "rejected"}:
            raise ValueError("lane must be approved or rejected")

        lane_prefix = self.APPROVED_PREFIX if lane == "approved" else self.REJECTED_PREFIX
        manifest_key = self._pending_manifest_keys.get(request.artifact_id)

        if manifest_key and "/pending/" in manifest_key:
            destination_manifest = manifest_key.replace("/pending/", f"/{lane}/", 1)
            self._move_object(manifest_key, destination_manifest)
        else:
            destination_manifest = f"{lane_prefix}{request.artifact_id}.request.json"
            request_payload = self._request_payload_cache.get(request.artifact_id, asdict(request))
            self._write_json(destination_manifest, request_payload)

        if request.b2_key and "/pending/" in request.b2_key:
            destination_artifact = request.b2_key.replace("/pending/", f"/{lane}/", 1)
            try:
                self._move_object(request.b2_key, destination_artifact)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Unable to move artifact %s to %s lane: %s",
                    request.b2_key,
                    lane,
                    exc,
                )

        verdict_key = f"{lane_prefix}{request.artifact_id}.verdict.json"
        self._write_json(
            verdict_key,
            {
                "request": asdict(request),
                "verdict": asdict(verdict),
            },
        )

    def _payload_to_request(self, payload: dict[str, Any], fallback_key: str) -> VerdictRequest:
        artifact_id = str(payload.get("artifact_id", "")).strip() or Path(fallback_key).stem
        return VerdictRequest(
            artifact_id=artifact_id,
            engine_id=str(payload.get("engine_id", "unknown")),
            track=str(payload.get("track", "shared")),
            artifact_type=str(payload.get("artifact_type", "generated_text")),
            b2_key=str(payload.get("b2_key", fallback_key)),
            session_id=str(payload.get("session_id", "unknown")),
            created_at=str(payload.get("created_at", self._now_iso())),
        )

    def _load_track_config(self, track: str) -> dict[str, Any]:
        if track in self._track_cfg_cache:
            return self._track_cfg_cache[track]
        cfg_path = Path("configs/training") / f"{track}.yaml"
        if not cfg_path.exists():
            self._track_cfg_cache[track] = {}
            return {}
        with cfg_path.open("r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle) or {}
        cfg = parsed if isinstance(parsed, dict) else {}
        self._track_cfg_cache[track] = cfg
        return cfg

    def _extract_thresholds(self, track_cfg: dict[str, Any]) -> dict[str, float]:
        raw = track_cfg.get("promotion_thresholds", {})
        if not isinstance(raw, dict):
            return {}
        return {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}

    def _load_session_metadata(self, request: VerdictRequest) -> dict[str, Any]:
        cached_payload = self._request_payload_cache.get(request.artifact_id, {})
        inline_eval_scores = cached_payload.get("eval_scores")
        if isinstance(inline_eval_scores, dict):
            return {"eval_scores": inline_eval_scores}

        key_candidates = [
            str(cached_payload.get("session_metadata_key", "")),
            str(cached_payload.get("metadata_key", "")),
            f"grok-verdicts/sessions/{request.session_id}.json",
            f"training-sessions/{request.session_id}/metadata.json",
            f"sessions/{request.session_id}/metadata.json",
            f"{Path(request.b2_key).with_suffix('')}.metadata.json",
        ]

        for key in key_candidates:
            key = key.strip()
            if not key:
                continue
            try:
                payload = self._read_json(key)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload

        if request.b2_key.lower().endswith(".json"):
            try:
                payload = self._read_json(request.b2_key)
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                return payload
        return {}

    def _extract_eval_scores(self, metadata: dict[str, Any]) -> dict[str, float]:
        raw = metadata.get("eval_scores")
        if not isinstance(raw, dict):
            raw = metadata.get("metrics", {})
        if not isinstance(raw, dict):
            return {}
        return {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}

    def _load_sample_text(self, request: VerdictRequest, metadata: dict[str, Any]) -> str:
        cached_payload = self._request_payload_cache.get(request.artifact_id, {})
        for field in ("sample_text", "output", "text"):
            candidate = cached_payload.get(field)
            if isinstance(candidate, str) and candidate.strip():
                return candidate

        for field in ("sample_output", "output", "text"):
            candidate = metadata.get(field)
            if isinstance(candidate, str) and candidate.strip():
                return candidate

        try:
            payload_bytes = self._read_bytes(request.b2_key)
        except Exception:
            return ""
        decoded = payload_bytes.decode("utf-8", errors="ignore")
        if request.b2_key.lower().endswith(".json"):
            try:
                parsed = json.loads(decoded)
            except json.JSONDecodeError:
                return decoded
            if isinstance(parsed, dict):
                for field in ("output", "text", "generated_text"):
                    candidate = parsed.get(field)
                    if isinstance(candidate, str):
                        return candidate
                return json.dumps(parsed, ensure_ascii=False)
        return decoded

    def _score_adapter_integrity(self, request: VerdictRequest) -> float:
        if request.artifact_type != "adapter":
            return 1.0
        try:
            size_bytes = self._stat_size(request.b2_key)
        except Exception:
            return 0.0

        min_size = 1024
        max_size = 8 * 1024 * 1024 * 1024
        if min_size <= size_bytes <= max_size:
            return 1.0
        if 512 <= size_bytes < min_size:
            return 0.4
        if max_size < size_bytes <= max_size * 1.5:
            return 0.4
        return 0.0

    def _score_metric(self, scores: dict[str, Any], keys: tuple[str, ...], fallback: float) -> float:
        for key in keys:
            value = scores.get(key)
            if isinstance(value, (int, float)):
                return self._clamp(float(value), 0.0, 1.0)
        return self._clamp(fallback, 0.0, 1.0)

    def _score_language_quality(self, track: str, sample_text: str, eval_scores: dict[str, float]) -> float:
        if track != "saudi_mod":
            return self._score_metric(eval_scores, ("language_quality", "overall"), 0.75)
        metric_score = self._score_metric(eval_scores, ("arabic_fidelity", "language_quality", "overall"), 0.5)
        arabic_presence = 1.0 if _ARABIC_REGEX.search(sample_text or "") else 0.0
        return round((0.6 * metric_score) + (0.4 * arabic_presence), 4)

    def _score_format_compliance(self, sample_text: str, eval_scores: dict[str, float]) -> float:
        metric_score = self._score_metric(
            eval_scores,
            ("structured_output", "format_compliance", "structured_report_compliance", "overall"),
            0.5,
        )
        structured_score = self._structured_marker_score(sample_text)
        return round((0.5 * metric_score) + (0.5 * structured_score), 4)

    def _score_doctrinal_alignment(self, track: str, sample_text: str, eval_scores: dict[str, float]) -> float:
        metric_score = self._score_metric(eval_scores, ("doctrinal", "doctrinal_consistency", "overall"), 0.65)
        if track != "nato":
            return metric_score
        doctrinal_marker = 1.0 if "nato" in sample_text.lower() else 0.5
        return round((0.7 * metric_score) + (0.3 * doctrinal_marker), 4)

    def _score_degraded_input_handling(
        self,
        track: str,
        sample_text: str,
        eval_scores: dict[str, float],
    ) -> float:
        metric_score = self._score_metric(
            eval_scores,
            ("degraded_recovery", "degraded_input_recovery", "adaptation", "overall"),
            0.65,
        )
        if track != "ukraine_mod":
            return metric_score
        degraded_markers = ("degraded", "fallback", "partial data", "low bandwidth", "offline")
        marker_hit = any(marker in sample_text.lower() for marker in degraded_markers)
        marker_score = 1.0 if marker_hit else 0.5
        return round((0.7 * metric_score) + (0.3 * marker_score), 4)

    def _structured_marker_score(self, sample_text: str) -> float:
        stripped = (sample_text or "").strip()
        if not stripped:
            return 0.0
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                json.loads(stripped)
                return 1.0
            except json.JSONDecodeError:
                return 0.4
        if "<" in stripped and ">" in stripped and "</" in stripped:
            return 1.0
        if "```json" in stripped.lower():
            return 0.8
        if "{" in stripped and "}" in stripped and ":" in stripped:
            return 0.6
        return 0.3

    def _score_threshold_compliance(self, eval_scores: dict[str, float], thresholds: dict[str, float]) -> float:
        scoped_thresholds = {
            metric: threshold
            for metric, threshold in thresholds.items()
            if metric != "overall"
        }
        if not scoped_thresholds:
            return 0.75
        met = 0
        total = len(scoped_thresholds)
        for metric, threshold in scoped_thresholds.items():
            score = eval_scores.get(metric)
            if isinstance(score, (int, float)) and float(score) >= float(threshold):
                met += 1
        return round(met / total, 4)

    def _weighted_average(self, scores: dict[str, float], weights: dict[str, float]) -> float:
        numerator = 0.0
        denominator = 0.0
        for key, weight in weights.items():
            numerator += float(scores.get(key, 0.0)) * float(weight)
            denominator += float(weight)
        if denominator <= 0:
            return 0.0
        return round(self._clamp(numerator / denominator, 0.0, 1.0), 4)

    def _extract_api_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        choice0 = choices[0]
        if not isinstance(choice0, dict):
            return ""
        message = choice0.get("message", {})
        if not isinstance(message, dict):
            return ""
        content = message.get("content", "")
        return str(content)

    def _parse_api_payload(self, content: str) -> dict[str, Any]:
        cleaned = _CODE_FENCE_REGEX.sub("", content or "").strip()
        if not cleaned:
            return {"rating": 0.0, "reason": "Empty Grok API response", "criteria": {}}

        try:
            parsed_json = json.loads(cleaned)
            if isinstance(parsed_json, dict):
                rating = parsed_json.get("rating", parsed_json.get("score", 0.0))
                reason = parsed_json.get("reason", parsed_json.get("rationale", ""))
                criteria = parsed_json.get("criteria", {})
                return {"rating": float(rating), "reason": str(reason), "criteria": criteria}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        rating_match = _RATING_REGEX.search(cleaned)
        if rating_match:
            rating_value = float(rating_match.group(1))
        else:
            generic_match = re.search(r"\b(10|[1-9](?:\.\d+)?)\b", cleaned)
            rating_value = float(generic_match.group(1)) if generic_match else 0.0
        return {"rating": rating_value, "reason": cleaned[:500], "criteria": {}}

    def _normalize_api_criteria(self, criteria_payload: Any, fallback_score: float) -> dict[str, float]:
        if not isinstance(criteria_payload, dict):
            criteria_payload = {}
        normalized: dict[str, float] = {}
        for key, value in criteria_payload.items():
            if not isinstance(value, (int, float)):
                continue
            numeric = float(value)
            if numeric > 1.0:
                numeric = numeric / 10.0
            normalized[str(key)] = self._clamp(numeric, 0.0, 1.0)

        required_keys = (
            "factual_consistency",
            "language_quality",
            "format_compliance",
            "doctrinal_alignment",
            "degraded_input_handling",
        )
        for key in required_keys:
            normalized.setdefault(key, fallback_score)
        return normalized

    def _list_keys(self, prefix: str) -> list[str]:
        connector = self.b2_connector
        if hasattr(connector, "list_keys"):
            return [str(item) for item in connector.list_keys(prefix)]
        if hasattr(connector, "list_objects"):
            raw = connector.list_objects(prefix)
            return self._normalize_object_listing(raw)
        if hasattr(connector, "list"):
            raw = connector.list(prefix)
            return self._normalize_object_listing(raw)
        raise AttributeError("B2 connector does not expose list capability")

    def _normalize_object_listing(self, raw_listing: Any) -> list[str]:
        keys: list[str] = []
        if isinstance(raw_listing, list):
            for item in raw_listing:
                if isinstance(item, str):
                    keys.append(item)
                elif isinstance(item, dict):
                    value = item.get("key", item.get("name"))
                    if isinstance(value, str):
                        keys.append(value)
        return sorted(keys)

    def _read_bytes(self, key: str) -> bytes:
        connector = self.b2_connector
        for method_name in ("get_bytes", "read_bytes", "download_bytes"):
            if hasattr(connector, method_name):
                method = getattr(connector, method_name)
                payload = method(key)
                return payload if isinstance(payload, bytes) else bytes(payload)
        if hasattr(connector, "get_text"):
            return str(connector.get_text(key)).encode("utf-8")
        raise AttributeError("B2 connector does not expose byte-read capability")

    def _write_bytes(self, key: str, payload: bytes) -> None:
        connector = self.b2_connector
        for method_name in ("put_bytes", "write_bytes", "upload_bytes"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(key, payload)
                return
        if hasattr(connector, "put_text"):
            connector.put_text(key, payload.decode("utf-8", errors="ignore"))
            return
        raise AttributeError("B2 connector does not expose byte-write capability")

    def _read_json(self, key: str) -> dict[str, Any]:
        connector = self.b2_connector
        for method_name in ("get_json", "read_json"):
            if hasattr(connector, method_name):
                payload = getattr(connector, method_name)(key)
                if isinstance(payload, dict):
                    return payload
                if isinstance(payload, list):
                    return {"items": payload}
        data = self._read_bytes(key).decode("utf-8", errors="ignore")
        payload = json.loads(data)
        if isinstance(payload, dict):
            return payload
        return {"items": payload}

    def _write_json(self, key: str, payload: dict[str, Any]) -> None:
        connector = self.b2_connector
        for method_name in ("put_json", "write_json", "upload_json"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(key, payload)
                return
        self._write_bytes(key, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def _move_object(self, source_key: str, destination_key: str) -> None:
        connector = self.b2_connector
        for method_name in ("move", "move_object", "rename", "rename_object"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(source_key, destination_key)
                return
        self._copy_object(source_key, destination_key)
        self._delete_object(source_key)

    def _copy_object(self, source_key: str, destination_key: str) -> None:
        connector = self.b2_connector
        for method_name in ("copy", "copy_object"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(source_key, destination_key)
                return
        payload = self._read_bytes(source_key)
        self._write_bytes(destination_key, payload)

    def _delete_object(self, key: str) -> None:
        connector = self.b2_connector
        for method_name in ("delete", "delete_object", "remove"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(key)
                return

    def _stat_size(self, key: str) -> int:
        connector = self.b2_connector
        for method_name in ("stat_size", "size", "get_size"):
            if hasattr(connector, method_name):
                value = getattr(connector, method_name)(key)
                return int(value)
        return len(self._read_bytes(key))

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

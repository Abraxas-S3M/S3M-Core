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

from src.storage.object_storage import ObjectStorageConnector

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
    object_key: str  # Object storage object key
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
    _CANONICAL_STAGES = ("cpu_stage1", "gpu_stage2")
    _LEGACY_STAGE_ALIASES = {
        "stage_1_cpu": "cpu_stage1",
        "stage1_cpu": "cpu_stage1",
        "cpu_stage_1": "cpu_stage1",
        "stage_2_gpu": "gpu_stage2",
        "stage2_gpu": "gpu_stage2",
        "gpu_stage_2": "gpu_stage2",
    }
    _SCORING_WEIGHTS = {
        # Existing quality-gate criteria are down-weighted to prioritize novelty/value criteria.
        "adapter_integrity": 0.0225,
        "factual_consistency": 0.03,
        "language_quality": 0.0225,
        "format_compliance": 0.0225,
        "doctrinal_alignment": 0.0225,
        "degraded_input_handling": 0.015,
        "threshold_compliance": 0.015,
        # Strategic/doctrinal value criteria are primary promotion drivers.
        "doctrinal_novelty": 0.25,
        "strategic_effectiveness": 0.20,
        "autonomous_decision_value": 0.15,
        "cross_theater_awareness": 0.15,
        "predictive_insight": 0.10,
    }

    def __init__(
        self,
        mode: str = "offline",  # "api" or "offline"
        xai_api_key: Optional[str] = None,
        object_storage_connector: Optional[ObjectStorageConnector] = None,
        validation_log_path: Path | str = Path("state/training/validation_log.jsonl"),
    ) -> None:
        normalized_mode = str(mode or "offline").strip().lower()
        if normalized_mode not in {"api", "offline"}:
            raise ValueError("mode must be either 'api' or 'offline'")

        self.mode = normalized_mode
        self.xai_api_key = xai_api_key
        self.object_storage_connector = object_storage_connector or ObjectStorageConnector()
        self.xai_api_url = "https://api.x.ai/v1/chat/completions"
        self.xai_model = "grok-beta"

        self._pending_manifest_keys: dict[str, str] = {}
        self._request_payload_cache: dict[str, dict[str, Any]] = {}
        self._track_cfg_cache: dict[str, dict[str, Any]] = {}
        self._validation_log_path = Path(validation_log_path)

    def scan_pending(self) -> List[VerdictRequest]:
        """Scan grok-verdicts/pending/ in object storage for unreviewed artifacts."""
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
            if not self._is_verdict_request_payload(payload):
                continue
            request = self._payload_to_request(payload, fallback_key=key)
            if request.artifact_id in self._pending_manifest_keys:
                logger.warning(
                    "Duplicate pending request for artifact_id=%s encountered at %s; keeping first record",
                    request.artifact_id,
                    self._pending_manifest_keys[request.artifact_id],
                )
                continue
            self._pending_manifest_keys[request.artifact_id] = key
            self._request_payload_cache[request.artifact_id] = payload
            requests_found.append(request)

        requests_found.sort(key=lambda item: item.created_at)
        logger.info("Found %d pending Grok verdict requests", len(requests_found))
        return requests_found

    def _is_verdict_request_payload(self, payload: dict[str, Any]) -> bool:
        required = ("track", "artifact_type", "session_id")
        if not all(str(payload.get(field, "")).strip() for field in required):
            return False
        # At least one identity field is required so random JSON artifacts are not parsed as requests.
        identity_fields = ("artifact_id", "object_key", "engine_id")
        return any(str(payload.get(field, "")).strip() for field in identity_fields)

    def evaluate_artifact(self, request: VerdictRequest, validation_stage: str = "") -> Verdict:
        """Score a single training artifact.

        Evaluation criteria:
        - Factual consistency (does the output contradict the prompt?)
        - Language quality (Arabic fidelity for saudi_mod track)
        - Format compliance (structured output validity)
        - Doctrinal alignment (for nato track)
        - Degraded-input handling (for ukraine_mod track)

        Returns Verdict with: passed (bool), score (0-1), reason (str)
        """
        normalized_stage = self._resolve_validation_stage(request=request, validation_stage=validation_stage)
        if self.mode == "api" and self.xai_api_key:
            try:
                verdict = self._evaluate_api(request, validation_stage=normalized_stage)
                self._append_validation_log(request=request, verdict=verdict, validation_stage=normalized_stage)
                return verdict
            except Exception as exc:
                logger.warning("API evaluation failed for %s, falling back offline: %s", request.artifact_id, exc)
        verdict = self._evaluate_offline(request, validation_stage=normalized_stage)
        self._append_validation_log(request=request, verdict=verdict, validation_stage=normalized_stage)
        return verdict

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
        """Move artifact from pending/ to approved/ in object storage."""
        self._move_request_to_lane(request=request, verdict=verdict, lane="approved")

    def move_to_rejected(self, request: VerdictRequest, verdict: Verdict):
        """Move artifact from pending/ to rejected/ in object storage."""
        self._move_request_to_lane(request=request, verdict=verdict, lane="rejected")

    def promote_approved_adapters(self):
        """Copy approved adapters to the live adapters/ path in object storage.
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

            source_key = str(request_payload.get("object_key", ""))
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

    def _evaluate_offline(self, request: VerdictRequest, validation_stage: str = "cpu_stage1") -> Verdict:
        track_cfg = self._load_track_config(request.track)
        thresholds = self._extract_thresholds(track_cfg)
        metadata = self._load_session_metadata(request)
        eval_scores = self._extract_eval_scores(metadata)
        sample_text = self._load_sample_text(request, metadata)
        stage_gate = self._stage_gate(validation_stage)

        criteria_scores: dict[str, float] = {
            "adapter_integrity": self._score_adapter_integrity(request),
            "factual_consistency": self._score_metric(eval_scores, ("factual_consistency", "consistency", "overall"), 0.55),
            "language_quality": self._score_language_quality(request.track, sample_text, eval_scores),
            "format_compliance": self._score_format_compliance(sample_text, eval_scores),
            "doctrinal_alignment": self._score_doctrinal_alignment(request.track, sample_text, eval_scores),
            "degraded_input_handling": self._score_degraded_input_handling(request.track, sample_text, eval_scores),
            "threshold_compliance": self._score_threshold_compliance(eval_scores, thresholds),
            "doctrinal_novelty": self._score_doctrinal_novelty(sample_text, eval_scores),
            "strategic_effectiveness": self._score_strategic_effectiveness(sample_text, eval_scores),
            "autonomous_decision_value": self._score_autonomous_decision_value(sample_text, eval_scores),
            "cross_theater_awareness": self._score_cross_theater_awareness(sample_text, eval_scores),
            "predictive_insight": self._score_predictive_insight(sample_text, eval_scores),
        }

        score = self._weighted_average(criteria_scores, self._SCORING_WEIGHTS)

        required_score = stage_gate["required_score"]
        novelty_minimum = stage_gate["novelty_minimum"]
        critical_failures: list[str] = []
        if request.artifact_type == "adapter" and criteria_scores["adapter_integrity"] < 0.5:
            critical_failures.append("adapter_integrity")
        if request.track == "saudi_mod" and criteria_scores["language_quality"] < 0.45:
            critical_failures.append("language_quality")
        if request.track == "nato" and criteria_scores["doctrinal_alignment"] < 0.45:
            critical_failures.append("doctrinal_alignment")
        if request.track == "ukraine_mod" and criteria_scores["degraded_input_handling"] < 0.45:
            critical_failures.append("degraded_input_handling")
        if criteria_scores["doctrinal_novelty"] < novelty_minimum:
            critical_failures.append("doctrinal_novelty")

        passed = score >= required_score and criteria_scores["threshold_compliance"] >= 0.5 and not critical_failures
        if passed:
            reason = (
                f"Offline checks passed with score {score:.3f} "
                f"(required {required_score:.3f}) for track {request.track} at {validation_stage}"
            )
        else:
            reasons = [f"score {score:.3f} below required {required_score:.3f}" if score < required_score else ""]
            if criteria_scores["threshold_compliance"] < 0.5:
                reasons.append("insufficient promotion-threshold compliance from eval metadata")
            if criteria_scores["doctrinal_novelty"] < novelty_minimum:
                reasons.append(
                    f"doctrinal novelty {criteria_scores['doctrinal_novelty']:.3f} "
                    f"below stage minimum {novelty_minimum:.3f}"
                )
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

    def _evaluate_api(self, request: VerdictRequest, validation_stage: str = "cpu_stage1") -> Verdict:
        track_cfg = self._load_track_config(request.track)
        thresholds = self._extract_thresholds(track_cfg)
        metadata = self._load_session_metadata(request)
        eval_scores = self._extract_eval_scores(metadata)
        sample_text = self._load_sample_text(request, metadata)
        stage_gate = self._stage_gate(validation_stage)
        prompt = self._build_prompt(request, sample_text, validation_stage=validation_stage)

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
        fallback_score = round(rating / 10.0, 4)
        required_score = stage_gate["required_score"]
        novelty_minimum = stage_gate["novelty_minimum"]

        criteria_payload = parsed.get("criteria", {})
        criteria_scores = self._normalize_api_criteria(criteria_payload, fallback_score)
        criteria_scores["adapter_integrity"] = self._score_adapter_integrity(request)
        criteria_scores["threshold_compliance"] = self._score_threshold_compliance(eval_scores, thresholds)
        score = self._weighted_average(criteria_scores, self._SCORING_WEIGHTS)
        reason = str(parsed.get("reason", "")).strip() or "No reasoning returned by Grok API"

        critical_failures: list[str] = []
        if request.artifact_type == "adapter" and criteria_scores["adapter_integrity"] < 0.5:
            critical_failures.append("adapter_integrity")
        if request.track == "saudi_mod" and criteria_scores["language_quality"] < 0.45:
            critical_failures.append("language_quality")
        if request.track == "nato" and criteria_scores["doctrinal_alignment"] < 0.45:
            critical_failures.append("doctrinal_alignment")
        if request.track == "ukraine_mod" and criteria_scores["degraded_input_handling"] < 0.45:
            critical_failures.append("degraded_input_handling")
        if criteria_scores["doctrinal_novelty"] < novelty_minimum:
            critical_failures.append("doctrinal_novelty")

        passed = score >= required_score and criteria_scores["threshold_compliance"] >= 0.5 and not critical_failures
        if not passed:
            failure_fragments = []
            if score < required_score:
                failure_fragments.append(f"score {score:.3f} below required {required_score:.3f}")
            if criteria_scores["threshold_compliance"] < 0.5:
                failure_fragments.append("insufficient promotion-threshold compliance from eval metadata")
            if criteria_scores["doctrinal_novelty"] < novelty_minimum:
                failure_fragments.append(
                    f"doctrinal novelty {criteria_scores['doctrinal_novelty']:.3f} "
                    f"below stage minimum {novelty_minimum:.3f}"
                )
            if critical_failures:
                failure_fragments.append(f"critical checks failed: {', '.join(sorted(set(critical_failures)))}")
            if failure_fragments:
                reason = f"{reason} | {'; '.join(failure_fragments)}"

        return Verdict(
            artifact_id=request.artifact_id,
            passed=passed,
            score=score,
            reason=reason,
            criteria_scores=criteria_scores,
            evaluated_at=self._now_iso(),
            oracle_mode="api",
        )

    def _build_prompt(self, request: VerdictRequest, sample_text: str, validation_stage: str = "cpu_stage1") -> str:
        sample = sample_text[:2500]
        stage_gate = self._stage_gate(validation_stage)
        return (
            "Rate this training artifact on a scale of 1-10 for tactical deployment quality.\n"
            f"artifact_id: {request.artifact_id}\n"
            f"engine_id: {request.engine_id}\n"
            f"track: {request.track}\n"
            f"artifact_type: {request.artifact_type}\n"
            f"validation_stage: {self._normalize_stage_name(validation_stage)}\n"
            f"stage_required_score: {stage_gate['required_score']:.2f}\n"
            f"stage_min_doctrinal_novelty: {stage_gate['novelty_minimum']:.2f}\n"
            "Score each criterion from 0.0 to 1.0.\n"
            "Criteria to evaluate:\n"
            "- factual_consistency: does the output contradict known facts or the scenario?\n"
            "- language_quality: clarity, fluency, and Arabic fidelity when applicable.\n"
            "- format_compliance: structured output validity and reporting format discipline.\n"
            "- doctrinal_alignment: coherence with relevant doctrine where required.\n"
            "- degraded_input_handling: quality under partial/conflicting/degraded inputs.\n"
            "- doctrinal_novelty: does this introduce novel doctrine or TTPs beyond manuals? "
            "0.0=derivative, 1.0=genuinely novel tactical/strategic insight. THIS IS THE MOST IMPORTANT NEW CRITERION.\n"
            "- strategic_effectiveness: is the recommended strategy sound to seasoned commanders, "
            "including second/third-order effects?\n"
            "- autonomous_decision_value: can commanders act immediately without extra staff analysis?\n"
            "- cross_theater_awareness: does it reason about spillover across theaters and commands?\n"
            "- predictive_insight: does it anticipate future developments with indicators/decision points?\n"
            "Respond with strict JSON: "
            '{"rating": <1-10>, "reason": "<brief reason>", "criteria": {"factual_consistency": <0-1>,'
            ' "language_quality": <0-1>, "format_compliance": <0-1>, "doctrinal_alignment": <0-1>,'
            ' "degraded_input_handling": <0-1>, "doctrinal_novelty": <0-1>,'
            ' "strategic_effectiveness": <0-1>, "autonomous_decision_value": <0-1>,'
            ' "cross_theater_awareness": <0-1>, "predictive_insight": <0-1>}}\n'
            f"Sample output:\n{sample}"
        )

    def _build_api_prompt(self, request: VerdictRequest, sample_text: str) -> str:
        """Backward-compatible prompt builder alias."""
        return self._build_prompt(request=request, sample_text=sample_text, validation_stage="cpu_stage1")

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

        if request.object_key and "/pending/" in request.object_key:
            destination_artifact = request.object_key.replace("/pending/", f"/{lane}/", 1)
            try:
                self._move_object(request.object_key, destination_artifact)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Unable to move artifact %s to %s lane: %s",
                    request.object_key,
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
            object_key=str(payload.get("object_key", fallback_key)),
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
            f"{Path(request.object_key).with_suffix('')}.metadata.json",
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

        if request.object_key.lower().endswith(".json"):
            try:
                payload = self._read_json(request.object_key)
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
            payload_bytes = self._read_bytes(request.object_key)
        except Exception:
            return ""
        decoded = payload_bytes.decode("utf-8", errors="ignore")
        if request.object_key.lower().endswith(".json"):
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
            size_bytes = self._stat_size(request.object_key)
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

    def _score_doctrinal_novelty(self, sample_text: str, eval_scores: dict[str, float]) -> float:
        metric_score = self._score_metric(
            eval_scores,
            ("doctrinal_novelty", "novelty", "ttp_novelty", "innovation", "overall"),
            0.5,
        )
        text = (sample_text or "").lower()
        novel_markers = (
            "novel",
            "new ttp",
            "non-doctrinal",
            "unconventional",
            "adaptive doctrine",
            "emergent tactic",
            "deception plan",
            "cross-domain feint",
        )
        derivative_markers = (
            "standard operating procedure",
            "according to doctrine",
            "as per field manual",
            "follow existing doctrine",
            "routine response",
        )
        novelty_signal = 0.5 + (0.1 * sum(marker in text for marker in novel_markers))
        novelty_signal -= 0.18 * sum(marker in text for marker in derivative_markers)
        if len(text.split()) < 30:
            novelty_signal = min(novelty_signal, 0.3)
        novelty_signal = self._clamp(novelty_signal, 0.0, 1.0)
        return round((0.6 * metric_score) + (0.4 * novelty_signal), 4)

    def _score_strategic_effectiveness(self, sample_text: str, eval_scores: dict[str, float]) -> float:
        metric_score = self._score_metric(
            eval_scores,
            ("strategic_effectiveness", "strategy_quality", "operational_soundness", "overall"),
            0.55,
        )
        text = (sample_text or "").lower()
        strategic_markers = (
            "second-order",
            "third-order",
            "logistics",
            "sustainment",
            "escalation",
            "countermeasure",
            "reserve",
            "risk mitigation",
            "branch and sequel",
        )
        flawed_markers = (
            "no risk",
            "guaranteed victory",
            "without opposition",
            "ignore logistics",
            "no contingencies",
        )
        strategic_signal = 0.4 + (0.07 * sum(marker in text for marker in strategic_markers))
        strategic_signal -= 0.2 * sum(marker in text for marker in flawed_markers)
        strategic_signal = self._clamp(strategic_signal, 0.0, 1.0)
        return round((0.65 * metric_score) + (0.35 * strategic_signal), 4)

    def _score_autonomous_decision_value(self, sample_text: str, eval_scores: dict[str, float]) -> float:
        metric_score = self._score_metric(
            eval_scores,
            ("autonomous_decision_value", "decision_readiness", "actionability", "overall"),
            0.55,
        )
        text = (sample_text or "").lower()
        action_markers = (
            "recommended coa",
            "go/no-go",
            "decision point",
            "if/then",
            "execute immediately",
            "priority 1",
            "commander action",
            "trigger condition",
        )
        delay_markers = (
            "requires additional analysis",
            "consult staff",
            "insufficient information",
            "defer decision",
            "wait for confirmation",
        )
        action_signal = 0.4 + (0.08 * sum(marker in text for marker in action_markers))
        action_signal -= 0.15 * sum(marker in text for marker in delay_markers)
        action_signal = self._clamp(action_signal, 0.0, 1.0)
        return round((0.65 * metric_score) + (0.35 * action_signal), 4)

    def _score_cross_theater_awareness(self, sample_text: str, eval_scores: dict[str, float]) -> float:
        metric_score = self._score_metric(
            eval_scores,
            ("cross_theater_awareness", "multi_theater_awareness", "intertheater_effects", "overall"),
            0.5,
        )
        text = (sample_text or "").lower()
        theaters = {
            "middle_east": ("centcom", "red sea", "gulf", "houthi", "levant"),
            "europe": ("eucom", "black sea", "baltic", "eastern europe"),
            "indo_pacific": ("indopacom", "south china sea", "taiwan strait", "pacific"),
            "africa": ("africom", "sahel", "horn of africa"),
        }
        theater_hits = sum(any(marker in text for marker in markers) for markers in theaters.values())
        theater_signal = self._clamp((theater_hits - 1) / 2.0, 0.0, 1.0) if theater_hits else 0.0
        return round((0.6 * metric_score) + (0.4 * theater_signal), 4)

    def _score_predictive_insight(self, sample_text: str, eval_scores: dict[str, float]) -> float:
        metric_score = self._score_metric(
            eval_scores,
            ("predictive_insight", "forecast_quality", "early_warning", "overall"),
            0.5,
        )
        text = (sample_text or "").lower()
        predictive_markers = (
            "likely",
            "anticipated",
            "forecast",
            "early warning indicator",
            "decision point",
            "next 24",
            "next 72",
            "trigger to watch",
        )
        reactive_markers = (
            "already happened",
            "reported that",
            "after action",
            "historical summary",
        )
        predictive_signal = 0.35 + (0.08 * sum(marker in text for marker in predictive_markers))
        predictive_signal -= 0.12 * sum(marker in text for marker in reactive_markers)
        predictive_signal = self._clamp(predictive_signal, 0.0, 1.0)
        return round((0.65 * metric_score) + (0.35 * predictive_signal), 4)

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
        if not eval_scores:
            # Tactical context: missing eval metadata should be treated as unknown, not automatic failure.
            return 0.75
        scoped_thresholds = {
            metric: threshold
            for metric, threshold in thresholds.items()
            if metric != "overall"
        }
        if not scoped_thresholds:
            return 0.75
        # Metadata can be missing for certain API-review payloads; avoid auto-failing those.
        if not eval_scores:
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
        key_aliases = {
            "factual_consistency": "factual_consistency",
            "language_quality": "language_quality",
            "format_compliance": "format_compliance",
            "doctrinal_alignment": "doctrinal_alignment",
            "degraded_input_handling": "degraded_input_handling",
            "doctrinal_novelty": "doctrinal_novelty",
            "ttp_novelty": "doctrinal_novelty",
            "novelty": "doctrinal_novelty",
            "strategic_effectiveness": "strategic_effectiveness",
            "strategy_quality": "strategic_effectiveness",
            "autonomous_decision_value": "autonomous_decision_value",
            "decision_readiness": "autonomous_decision_value",
            "cross_theater_awareness": "cross_theater_awareness",
            "multi_theater_awareness": "cross_theater_awareness",
            "predictive_insight": "predictive_insight",
            "forecast_quality": "predictive_insight",
        }
        for key, value in criteria_payload.items():
            if not isinstance(value, (int, float)):
                continue
            numeric = float(value)
            if numeric > 1.0:
                numeric = numeric / 10.0
            normalized_key = str(key).strip().lower().replace("-", "_").replace(" ", "_")
            canonical_key = key_aliases.get(normalized_key, normalized_key)
            normalized[canonical_key] = self._clamp(numeric, 0.0, 1.0)

        required_keys = (
            "factual_consistency",
            "language_quality",
            "format_compliance",
            "doctrinal_alignment",
            "degraded_input_handling",
            "doctrinal_novelty",
            "strategic_effectiveness",
            "autonomous_decision_value",
            "cross_theater_awareness",
            "predictive_insight",
        )
        for key in required_keys:
            normalized.setdefault(key, fallback_score)
        return normalized

    def _normalize_stage_name(self, stage_name: str) -> str:
        normalized = str(stage_name or "").strip().lower()
        if normalized in self._CANONICAL_STAGES:
            return normalized
        if normalized in self._LEGACY_STAGE_ALIASES:
            return self._LEGACY_STAGE_ALIASES[normalized]
        return "cpu_stage1"

    def _resolve_validation_stage(self, request: VerdictRequest, validation_stage: str = "") -> str:
        cached_payload = self._request_payload_cache.get(request.artifact_id, {})
        candidate = (
            str(validation_stage).strip()
            or str(cached_payload.get("validation_stage", "")).strip()
            or "cpu_stage1"
        )
        return self._normalize_stage_name(candidate)

    def _stage_gate(self, validation_stage: str) -> dict[str, float]:
        stage = self._normalize_stage_name(validation_stage)
        if stage == "gpu_stage2":
            return {"required_score": 0.70, "novelty_minimum": 0.5}
        return {"required_score": 0.55, "novelty_minimum": 0.3}

    def _list_keys(self, prefix: str) -> list[str]:
        connector = self.object_storage_connector
        if hasattr(connector, "list_keys"):
            return [str(item) for item in connector.list_keys(prefix)]
        if hasattr(connector, "list_objects"):
            raw = connector.list_objects(prefix)
            return self._normalize_object_listing(raw)
        if hasattr(connector, "list"):
            raw = connector.list(prefix)
            return self._normalize_object_listing(raw)
        raise AttributeError("Object storage connector does not expose list capability")

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
        connector = self.object_storage_connector
        for method_name in ("get_bytes", "read_bytes", "download_bytes"):
            if hasattr(connector, method_name):
                method = getattr(connector, method_name)
                payload = method(key)
                return payload if isinstance(payload, bytes) else bytes(payload)
        if hasattr(connector, "get_text"):
            return str(connector.get_text(key)).encode("utf-8")
        raise AttributeError("Object storage connector does not expose byte-read capability")

    def _write_bytes(self, key: str, payload: bytes) -> None:
        connector = self.object_storage_connector
        for method_name in ("put_bytes", "write_bytes", "upload_bytes"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(key, payload)
                return
        if hasattr(connector, "put_text"):
            connector.put_text(key, payload.decode("utf-8", errors="ignore"))
            return
        raise AttributeError("Object storage connector does not expose byte-write capability")

    def _read_json(self, key: str) -> dict[str, Any]:
        connector = self.object_storage_connector
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
        connector = self.object_storage_connector
        for method_name in ("put_json", "write_json", "upload_json"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(key, payload)
                return
        self._write_bytes(key, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def _move_object(self, source_key: str, destination_key: str) -> None:
        connector = self.object_storage_connector
        for method_name in ("move", "move_object", "rename", "rename_object"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(source_key, destination_key)
                return
        self._copy_object(source_key, destination_key)
        self._delete_object(source_key)

    def _copy_object(self, source_key: str, destination_key: str) -> None:
        connector = self.object_storage_connector
        for method_name in ("copy", "copy_object"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(source_key, destination_key)
                return
        payload = self._read_bytes(source_key)
        self._write_bytes(destination_key, payload)

    def _delete_object(self, key: str) -> None:
        connector = self.object_storage_connector
        for method_name in ("delete", "delete_object", "remove"):
            if hasattr(connector, method_name):
                getattr(connector, method_name)(key)
                return

    def _stat_size(self, key: str) -> int:
        connector = self.object_storage_connector
        for method_name in ("stat_size", "size", "get_size"):
            if hasattr(connector, method_name):
                value = getattr(connector, method_name)(key)
                return int(value)
        return len(self._read_bytes(key))

    def _append_validation_log(self, request: VerdictRequest, verdict: Verdict, validation_stage: str = "") -> None:
        self._validation_log_path.parent.mkdir(parents=True, exist_ok=True)
        stage_name = self._resolve_validation_stage(request=request, validation_stage=validation_stage)
        payload = {
            "artifact_id": request.artifact_id,
            "engine_id": request.engine_id,
            "track": request.track,
            "artifact_type": request.artifact_type,
            "session_id": request.session_id,
            "validation_stage": stage_name,
            "passed": bool(verdict.passed),
            "score": float(verdict.score),
            "reason": verdict.reason,
            "criteria_scores": dict(verdict.criteria_scores),
            "oracle_mode": verdict.oracle_mode,
            "evaluated_at": verdict.evaluated_at,
        }
        with self._validation_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

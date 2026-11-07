"""Quad-engine orchestrator for the S3M-Core demo orchestration layer.

Tactical context:
    The orchestrator is the conductor of the four advisory engines. Given a
    routed operational packet it asks each responsible engine for its output,
    assembles a commander-ready brief (SITREP, threat assessment, COA options,
    Arabic summary), and emits human-review decision cards.

Engine roles:
    * tactical_engine  -> fast SITREP, track explanation, immediate summary.
    * reasoning_engine -> threat assessment, competing hypotheses, confidence
      reasoning, anomaly analysis.
    * planning_engine  -> COA options, watch priorities, sensor cueing, task list.
    * arabic_engine    -> Arabic commander summary and GCC regional phrasing.

Safety doctrine:
    * If local LLM is disabled or a model is missing, the engine returns a
      deterministic placeholder and is reported as ``placeholder`` so the demo
      never goes blank and a placeholder is never mistaken for a live model.
    * Every result is ``human_review_required`` and every decision card carries
      ``status="human_review_required"``. The orchestrator NEVER authorizes
      autonomous or kinetic action; it only produces recommendations / briefs.
    * No external AI APIs, trainers, sync daemons, RunPod jobs, or R2 access are
      ever invoked from this path.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional

from src.quad_engine.audit_log import AuditLog, get_audit_log
from src.quad_engine.local_llm import LocalLLMRunner, get_local_llm
from src.quad_engine.model_registry import ModelRegistry, get_registry
from src.quad_engine.models import (
    ARABIC_ENGINE,
    OUTPUT_ARABIC,
    OUTPUT_COA,
    OUTPUT_SITREP,
    OUTPUT_THREAT,
    PLANNING_ENGINE,
    REASONING_ENGINE,
    TACTICAL_ENGINE,
    CoaOption,
    DecisionCard,
    EngineStatus,
    OperationalPacket,
    QuadEngineResult,
    RouteInfo,
)
from src.integrations.lechonk.orchestrator_routing import resolve_planning_backing_engine
from src.quad_engine.packet_router import PacketRouter, get_packet_router

# Which engine owns which output key.
_OUTPUT_ENGINE: Dict[str, str] = {
    OUTPUT_SITREP: TACTICAL_ENGINE,
    "track_explanation": TACTICAL_ENGINE,
    OUTPUT_THREAT: REASONING_ENGINE,
    "anomaly_analysis": REASONING_ENGINE,
    "competing_hypotheses": REASONING_ENGINE,
    OUTPUT_COA: PLANNING_ENGINE,
    "watch_priorities": PLANNING_ENGINE,
    "sensor_cueing": PLANNING_ENGINE,
    "commander_tasks": PLANNING_ENGINE,
    OUTPUT_ARABIC: ARABIC_ENGINE,
}

# System prompts used when (and only when) a live local model is available.
_SYSTEM_PROMPTS: Dict[str, str] = {
    TACTICAL_ENGINE: (
        "You are the S3M Tactical Engine. Produce a concise, factual SITREP for a "
        "commander. Recommendations only; never authorize action."
    ),
    REASONING_ENGINE: (
        "You are the S3M Reasoning Engine. Provide a threat assessment with "
        "competing hypotheses and a confidence rationale. Analysis only."
    ),
    PLANNING_ENGINE: (
        "You are the S3M Planning Engine. Offer course-of-action options, watch "
        "priorities, and sensor cueing suggestions. Recommendations require human review."
    ),
    ARABIC_ENGINE: (
        "أنت محرك اللغة العربية في إس ٣ إم. لخّص الموقف للقائد بالعربية الفصحى مع "
        "مصطلحات عسكرية خليجية. توصيات فقط تتطلب مراجعة بشرية."
    ),
}


def _seed(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _payload_summary(packet: OperationalPacket) -> str:
    payload = packet.payload or {}
    bits: List[str] = []
    for key in ("callsign", "track_id", "domain", "affiliation", "title", "summary", "status"):
        value = payload.get(key)
        if value:
            bits.append(f"{key}={value}")
    if not bits:
        bits.append(f"packet_type={packet.packet_type.value}")
    return ", ".join(bits)


class QuadEngineOrchestrator:
    """Coordinates the four advisory engines into one structured result."""

    def __init__(
        self,
        *,
        registry: Optional[ModelRegistry] = None,
        router: Optional[PacketRouter] = None,
        local_llm: Optional[LocalLLMRunner] = None,
        audit_log: Optional[AuditLog] = None,
        max_results: int = 500,
    ) -> None:
        self._registry = registry or get_registry()
        self._router = router or get_packet_router()
        self._local_llm = local_llm or get_local_llm()
        self._audit = audit_log or get_audit_log()
        self._max_results = max(1, int(max_results))
        self._results: Dict[str, QuadEngineResult] = {}

    # ── Engine output generation ─────────────────────────────

    def _engine_status(self, engine_id: str) -> EngineStatus:
        return self._registry.effective_status(engine_id)

    def _generate(
        self,
        engine_id: str,
        output_key: str,
        packet: OperationalPacket,
    ) -> tuple[Any, EngineStatus]:
        """Generate one output, preferring live local inference then placeholder.

        Returns the output value and the *realized* engine status for this call.
        """
        # Attempt live local inference only when the engine is truly available.
        if self._local_llm.engine_available(engine_id):
            prompt = self._build_prompt(output_key, packet)
            text = self._local_llm.generate(
                engine_id,
                prompt,
                system_prompt=_SYSTEM_PROMPTS.get(engine_id, ""),
            )
            if text:
                if output_key == OUTPUT_COA:
                    # Live COA text is wrapped as a single descriptive option;
                    # structured option synthesis stays deterministic for safety.
                    return (
                        [
                            CoaOption(
                                option_id="coa-live-1",
                                name="Local model COA",
                                description=text,
                                risk="medium",
                                confidence=0.6,
                            ).model_dump()
                        ],
                        EngineStatus.LIVE_LOCAL,
                    )
                return text, EngineStatus.LIVE_LOCAL

        # Deterministic placeholder fallback (the demo never goes blank).
        return self._placeholder(output_key, packet), EngineStatus.PLACEHOLDER

    def _build_prompt(self, output_key: str, packet: OperationalPacket) -> str:
        return (
            f"Output requested: {output_key}.\n"
            f"Packet type: {packet.packet_type.value}.\n"
            f"Track: {packet.track}. Source: {packet.source}.\n"
            f"Context: {_payload_summary(packet)}.\n"
            f"Payload: {packet.payload}."
        )

    def _placeholder(self, output_key: str, packet: OperationalPacket) -> Any:
        context = _payload_summary(packet)
        ref = _seed(f"{packet.packet_id}:{output_key}")

        if output_key == OUTPUT_SITREP:
            return (
                f"[PLACEHOLDER SITREP {ref}] Track '{packet.track}' reported a "
                f"{packet.packet_type.value} from source '{packet.source}'. "
                f"Context: {context}. Situation nominal pending verification; "
                f"no immediate kinetic indicators. Recommend continued monitoring."
            )
        if output_key == "track_explanation":
            return (
                f"[PLACEHOLDER TRACK EXPLANATION {ref}] Contact correlated under "
                f"track '{packet.track}'. {context}. Behavior consistent with "
                f"routine activity until corroborated by additional sensors."
            )
        if output_key == OUTPUT_THREAT:
            return (
                f"[PLACEHOLDER THREAT ASSESSMENT {ref}] Preliminary threat level "
                f"ASSESSED MODERATE pending confirmation. Competing hypotheses: "
                f"(1) routine/neutral activity; (2) probing or reconnaissance. "
                f"Anomaly indicators inconclusive. Confidence rationale: limited "
                f"single-source data. {context}."
            )
        if output_key == "anomaly_analysis":
            return (
                f"[PLACEHOLDER ANOMALY ANALYSIS {ref}] No statistically significant "
                f"deviation confirmed from baseline for {context}. Flag for analyst review."
            )
        if output_key == "competing_hypotheses":
            return [
                "H1: Routine/neutral activity (baseline).",
                "H2: Reconnaissance or probing behavior.",
                "H3: Sensor artifact or mis-correlation.",
            ]
        if output_key == OUTPUT_COA:
            return [
                CoaOption(
                    option_id="coa-1",
                    name="Maintain watch",
                    description=(
                        f"Continue passive monitoring of track '{packet.track}' and "
                        "re-evaluate on next update."
                    ),
                    risk="low",
                    confidence=0.55,
                ).model_dump(),
                CoaOption(
                    option_id="coa-2",
                    name="Cue additional ISR",
                    description=(
                        "Task additional ISR/sensor coverage to confirm identity and intent."
                    ),
                    risk="low",
                    confidence=0.5,
                ).model_dump(),
                CoaOption(
                    option_id="coa-3",
                    name="Elevate to commander review",
                    description=(
                        "Escalate for commander decision if affiliation resolves to hostile."
                    ),
                    risk="medium",
                    confidence=0.45,
                ).model_dump(),
            ]
        if output_key == "watch_priorities":
            return [
                f"Priority 1: Confirm identity/affiliation of track '{packet.track}'.",
                "Priority 2: Monitor approach vectors to key theater nodes.",
                "Priority 3: Maintain Arabic/English common picture for command staff.",
            ]
        if output_key == "sensor_cueing":
            return [
                "Cue ISR asset toward reported bearing for positive identification.",
                "Maintain radar custody; correlate with maritime/air feeds.",
            ]
        if output_key == "commander_tasks":
            return [
                "Review threat assessment and COA options.",
                "Authorize ISR cueing if warranted (human decision).",
                "Acknowledge that no autonomous action has been taken.",
            ]
        if output_key == OUTPUT_ARABIC:
            return (
                f"[ملخص للقائد - عرض توضيحي {ref}] تم رصد حدث ({packet.packet_type.value}) "
                f"على المسار '{packet.track}'. الوضع مستقر مبدئيًا ويخضع للتحقق. "
                f"التوصية: مواصلة المراقبة وتقييم الموقف. القرار النهائي يتطلب مراجعة بشرية."
            )
        return f"[PLACEHOLDER {output_key} {ref}] {context}."

    # ── Decision cards / confidence ──────────────────────────

    def _decision_cards(
        self,
        packet: OperationalPacket,
        route: RouteInfo,
    ) -> List[DecisionCard]:
        payload = packet.payload or {}
        affiliation = str(payload.get("affiliation", "")).lower()
        priority = "high" if affiliation in {"hostile", "suspect"} else "medium"

        cards = [
            DecisionCard(
                title=f"Review {packet.packet_type.value} on track '{packet.track}'",
                summary=(
                    "AI-generated recommendation requires commander review before "
                    "any action. Outputs are advisory only."
                ),
                priority=priority,
                status="human_review_required",
                recommended_action="Validate AI assessment against live sensor data.",
            ),
            DecisionCard(
                title="No autonomous action taken",
                summary=(
                    "The quad-engine layer produced recommendations only. No kinetic "
                    "or autonomous action was executed."
                ),
                priority="low",
                status="human_review_required",
                recommended_action="Acknowledge advisory-only posture.",
            ),
        ]
        return cards

    def _confidence(self, engine_status: Dict[str, EngineStatus]) -> float:
        """Deterministic blended confidence.

        Live local engines lend more confidence than placeholders; the value is
        intentionally bounded and conservative for a demo layer.
        """
        if not engine_status:
            return 0.0
        per_engine = {
            EngineStatus.LIVE_LOCAL: 0.8,
            EngineStatus.PLACEHOLDER: 0.45,
            EngineStatus.UNAVAILABLE: 0.0,
        }
        total = sum(per_engine.get(s, 0.0) for s in engine_status.values())
        return round(total / len(engine_status), 2)

    # ── Public orchestration entrypoints ─────────────────────

    def process_packet(self, packet: OperationalPacket) -> QuadEngineResult:
        """Route, run, and assemble a structured result for one packet."""
        route = self._router.route(packet)

        requested = packet.requested_outputs or [
            OUTPUT_SITREP,
            OUTPUT_THREAT,
            OUTPUT_COA,
            OUTPUT_ARABIC,
        ]

        outputs: Dict[str, Any] = {}
        realized_status: Dict[str, EngineStatus] = {}

        for output_key in requested:
            engine_id = _OUTPUT_ENGINE.get(output_key)
            if engine_id is None:
                # Unknown output keys are ignored rather than erroring out.
                continue
            value, status = self._generate(engine_id, output_key, packet)
            outputs[output_key] = value
            realized_status[engine_id] = status

        # Report status for all four engines so the GUI always sees the panel,
        # using the realized status when the engine was consulted.
        engine_status: Dict[str, EngineStatus] = {}
        for engine_id in (TACTICAL_ENGINE, REASONING_ENGINE, PLANNING_ENGINE, ARABIC_ENGINE):
            engine_status[engine_id] = realized_status.get(
                engine_id, self._engine_status(engine_id)
            )

        result = QuadEngineResult(
            result_id=f"qe-{uuid.uuid4().hex[:12]}",
            packet_id=packet.packet_id,
            route=route,
            outputs=outputs,
            decision_cards=self._decision_cards(packet, route),
            confidence=self._confidence(
                {k: v for k, v in realized_status.items()} or engine_status
            ),
            human_review_required=True,
            engine_status=engine_status,
            classification=packet.classification,
        )

        planning_route = resolve_planning_backing_engine()

        self._store_result(result)
        self._audit.record(
            "quad_engine_packet",
            {
                "result_id": result.result_id,
                "packet_id": packet.packet_id,
                "packet_type": packet.packet_type.value,
                "track": packet.track,
                "primary_engine": route.primary_engine,
                "requested_outputs": list(requested),
                "engine_status": {k: v.value for k, v in engine_status.items()},
                "planning_backing": planning_route.audit_record(),
                "human_review_required": True,
                "autonomous_action": False,
                "external_api_called": False,
            },
        )
        return result

    def _store_result(self, result: QuadEngineResult) -> None:
        self._results[result.result_id] = result
        if len(self._results) > self._max_results:
            # Drop oldest entries (insertion order preserved in dict).
            for key in list(self._results.keys())[: len(self._results) - self._max_results]:
                self._results.pop(key, None)

    def get_result(self, result_id: str) -> Optional[QuadEngineResult]:
        return self._results.get(result_id)

    # ── COP commander brief demo ─────────────────────────────

    def build_cop_brief(self, cop_state: Dict[str, Any]) -> QuadEngineResult:
        """Build a deterministic commander brief from a COP state payload.

        Tactical context:
            This summarizes active tracks, alerts, and decisions from the Saudi
            MOD COP demo into an executive SITREP, threat assessment, watch
            priorities, human-review decision cards, and an Arabic commander
            summary placeholder. It runs entirely on the supplied COP snapshot
            and never reaches out to a model, trainer, or external API.
        """
        track = str(cop_state.get("track", "saudi_mod"))
        tracks = list(cop_state.get("tactical_tracks", []) or [])
        alerts = list(cop_state.get("alerts", []) or [])
        decisions = list(cop_state.get("decisions", []) or [])

        hostiles = [t for t in tracks if str(t.get("affiliation", "")).lower() == "hostile"]
        unknowns = [t for t in tracks if str(t.get("affiliation", "")).lower() == "unknown"]
        domains = sorted({str(t.get("domain", "")) for t in tracks if t.get("domain")})
        active_alerts = [a for a in alerts if str(a.get("status", "active")).lower() == "active"]

        sitrep = (
            f"[EXECUTIVE SITREP] Theater '{track}': {len(tracks)} active tracks across "
            f"domains [{', '.join(domains) or 'n/a'}]. "
            f"{len(hostiles)} hostile, {len(unknowns)} unknown contacts. "
            f"{len(active_alerts)} active alert(s), {len(decisions)} open decision item(s). "
            f"Common operating picture stable; outputs are advisory and require human review."
        )

        alert_titles = [str(a.get("title", a.get("summary", "alert"))) for a in active_alerts]
        threat_assessment = (
            f"[THREAT ASSESSMENT] {len(hostiles)} hostile and {len(unknowns)} unknown "
            f"contact(s) under watch. "
            + (
                "Priority threats: " + "; ".join(alert_titles[:3]) + "."
                if alert_titles
                else "No active high-priority alerts at this time."
            )
            + " Competing hypotheses retained; confidence MODERATE pending corroboration."
        )

        watch_priorities = [
            f"Confirm identity/intent of {len(hostiles) + len(unknowns)} non-friendly contact(s).",
            "Maintain custody on active alert locations.",
            "Sustain bilingual (Arabic/English) common picture for command staff.",
        ]

        decision_cards: List[DecisionCard] = []
        for dec in decisions[:5]:
            decision_cards.append(
                DecisionCard(
                    title=str(dec.get("title", "Commander decision item")),
                    summary=str(dec.get("summary", "Review required.")),
                    priority=str(dec.get("priority", "medium")),
                    status="human_review_required",
                    recommended_action="Commander review required before action.",
                )
            )
        decision_cards.append(
            DecisionCard(
                title="No autonomous action taken",
                summary="Commander brief is advisory only; no kinetic/autonomous action executed.",
                priority="low",
                status="human_review_required",
                recommended_action="Acknowledge advisory-only posture.",
            )
        )

        arabic_summary = (
            f"[ملخص القائد - عرض توضيحي] المسرح '{track}': {len(tracks)} مسارات نشطة، "
            f"منها {len(hostiles)} معادية و{len(unknowns)} مجهولة. "
            f"عدد الإنذارات النشطة {len(active_alerts)} وعدد قرارات القيادة المفتوحة {len(decisions)}. "
            f"الصورة العملياتية مستقرة. جميع المخرجات استشارية وتتطلب مراجعة بشرية قبل أي إجراء."
        )

        engine_status = self._registry.engine_status_map()
        route = RouteInfo(
            primary_engine=TACTICAL_ENGINE,
            supporting_engines=[REASONING_ENGINE, PLANNING_ENGINE, ARABIC_ENGINE],
            reason="COP commander brief: tactical summary with reasoning, planning, and Arabic support.",
            route_hint="tactical",
        )

        result = QuadEngineResult(
            result_id=f"qe-cop-{uuid.uuid4().hex[:12]}",
            packet_id=f"cop-brief-{track}",
            route=route,
            outputs={
                OUTPUT_SITREP: sitrep,
                OUTPUT_THREAT: threat_assessment,
                "watch_priorities": watch_priorities,
                OUTPUT_ARABIC: arabic_summary,
            },
            decision_cards=decision_cards,
            confidence=self._confidence(engine_status),
            human_review_required=True,
            engine_status=engine_status,
            classification=str(cop_state.get("classification", "UNCLASSIFIED_DEMO")),
        )

        self._store_result(result)
        self._audit.record(
            "quad_engine_cop_brief",
            {
                "result_id": result.result_id,
                "track": track,
                "tracks": len(tracks),
                "alerts": len(active_alerts),
                "decisions": len(decisions),
                "engine_status": {k: v.value for k, v in engine_status.items()},
                "human_review_required": True,
                "autonomous_action": False,
                "external_api_called": False,
            },
        )
        return result


_GLOBAL_ORCHESTRATOR: Optional[QuadEngineOrchestrator] = None


def get_orchestrator() -> QuadEngineOrchestrator:
    """Return the process-wide orchestrator singleton."""
    global _GLOBAL_ORCHESTRATOR
    if _GLOBAL_ORCHESTRATOR is None:
        _GLOBAL_ORCHESTRATOR = QuadEngineOrchestrator()
    return _GLOBAL_ORCHESTRATOR

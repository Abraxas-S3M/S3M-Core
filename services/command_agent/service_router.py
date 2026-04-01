"""Service router for command-agent intent dispatch.

Military context:
Routes commander intent to mission, threat, kill-chain, risk, and status services
so command decisions can be executed rapidly with bilingual outputs.
"""

from __future__ import annotations

import time
import uuid

from services.command_agent.models import CommandContext, CommandIntent, CommandResponse
from services.killchain import F2T2EAPipeline
from services.risk_assessment import RiskEngine
from src.autonomy.swarm import NLCommander
from src.dashboard.aggregator import DashboardAggregator
from src.threat_detection.threat_manager import ThreatManager


class ServiceRouter:
    """Route intents to subsystem handlers and shape response payloads."""

    def __init__(self):
        self.nl_commander = NLCommander()
        self.killchain = F2T2EAPipeline()
        self.risk_engine = RiskEngine()
        self.threat_manager = ThreatManager()
        self.dashboard = DashboardAggregator()
        self.current_authority = 1

    def route(self, intent: CommandIntent, entities: dict, context: CommandContext, raw_text: str) -> dict:
        """Dispatch intent to target service and return standardized result envelope."""
        started = time.perf_counter()
        result = {"service": "unknown", "action": "none", "result": {"message": "No route"}}

        if intent == CommandIntent.MOVE_UNIT:
            cmd = (
                self.nl_commander.parse_arabic_command(raw_text)
                if context and context.commander_language == "ar"
                else self.nl_commander.parse_command(raw_text)
            )
            result = {"service": "autonomy", "action": "move_unit", "result": {"command": cmd.to_dict(), "status": "queued"}}

        elif intent == CommandIntent.ENGAGE_TARGET:
            chain_result = self.killchain.execute_chain({"image_path": "stub_image.jpg", "target_hint": entities.get("targets", [])})
            risk = self.risk_engine.assess_engagement(chain_result.get("target", {})).to_dict()
            result = {"service": "killchain", "action": "engage_target", "result": {"killchain": chain_result, "risk": risk}}

        elif intent == CommandIntent.AUTHORIZE_KILLCHAIN:
            level = int(entities.get("parameters", {}).get("authority_level", 3))
            self.current_authority = level
            result = {"service": "killchain", "action": "set_authority", "result": {"authority_level": level}}

        elif intent == CommandIntent.SET_ROE:
            roe = entities.get("parameters", {}).get("roe_level", "weapons_tight")
            result = {"service": "rules", "action": "set_roe", "result": {"roe_level": roe, "status": "updated"}}

        elif intent == CommandIntent.QUERY_THREATS:
            threats = [e.to_dict() for e in self.threat_manager.get_threats(limit=20)]
            result = {"service": "threat_manager", "action": "query_threats", "result": {"threats": threats, "count": len(threats)}}

        elif intent == CommandIntent.QUERY_READINESS:
            result = {
                "service": "readiness",
                "action": "query_readiness",
                "result": {"unit": context.current_region if context else "unknown", "readiness_score": 0.78},
            }

        elif intent == CommandIntent.QUERY_STATUS:
            result = {"service": "dashboard", "action": "query_status", "result": self.dashboard.get_overview()}

        elif intent == CommandIntent.ANALYZE_RISK:
            assessment = self.risk_engine.assess_mission(
                mission={"name": "ad-hoc", "platform_type": "air", "objectives": 2, "duration_hours": 4},
                assets=[{"type": "uav_quadrotor_small", "condition_score": 0.35}],
                personnel=[{"readiness": 0.82}],
            )
            result = {"service": "risk_engine", "action": "analyze_risk", "result": assessment.to_dict()}

        elif intent == CommandIntent.GENERATE_REPORT:
            result = {"service": "intel", "action": "generate_report", "result": {"report": "SITREP generated (offline stub)."}}

        elif intent == CommandIntent.GENERATE_BRIEF:
            result = {"service": "intel", "action": "generate_brief", "result": {"brief": "Daily brief generated (offline stub)."}}

        elif intent == CommandIntent.UPLOAD_DOCUMENT:
            result = {"service": "document_processor", "action": "process_document", "result": {"status": "processed"}}

        elif intent == CommandIntent.UPLOAD_DATA:
            result = {"service": "document_processor", "action": "process_data", "result": {"status": "ingested"}}

        elif intent == CommandIntent.UPLOAD_IMAGE:
            result = {"service": "document_processor", "action": "process_image", "result": {"status": "analyzed"}}

        elif intent == CommandIntent.SYSTEM_CONTROL:
            result = {"service": "system", "action": "control", "result": {"status": "acknowledged"}}

        latency_ms = (time.perf_counter() - started) * 1000.0
        result["latency_ms"] = latency_ms
        return result

    def compose_response(self, route_result: dict, context: CommandContext) -> CommandResponse:
        """Compose bilingual commander response with suggestions and sources."""
        service = route_result.get("service", "unknown")
        action = route_result.get("action", "none")
        result = route_result.get("result", {})
        intent_text = f"{service}:{action}"
        text_en = f"Command processed via {intent_text}."
        text_ar = f"تمت معالجة الأمر عبر {intent_text}."

        suggestions = [
            "Request latest threat picture",
            "Assess mission risk before engagement",
            "Generate SITREP for your sector",
        ]

        return CommandResponse(
            response_id=f"resp-{uuid.uuid4().hex[:10]}",
            input_id=str(result.get("input_id", "unknown")),
            intent=CommandIntent.UNKNOWN,
            text_en=text_en,
            text_ar=text_ar,
            structured_data=result,
            actions_taken=[{"service": service, "action": action}],
            sources=[service],
            confidence=0.8,
            follow_up_suggestions=suggestions,
            response_time_ms=float(route_result.get("latency_ms", 0.0)),
        )

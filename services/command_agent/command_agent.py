"""Central multimodal AI command-and-control agent.

Military context:
This agent is the commander-facing tactical interface that normalizes multimodal
inputs, routes intents to sovereign subsystems, and records auditable outcomes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import time
import uuid
from typing import Dict, List, Optional, Union

from services.command_agent.document_processor import DocumentProcessor
from services.command_agent.intent_classifier import IntentClassifier
from services.command_agent.models import (
    CommandContext,
    CommandInput,
    CommandResponse,
    InputModality,
)
from services.command_agent.service_router import ServiceRouter
from services.command_agent.voice_processor import VoiceProcessor
from src.security.crypto import SecureAuditLog


class CommandAgent:
    """Multimodal AI C2 agent for bilingual field-command operations."""

    def __init__(self):
        self.voice = VoiceProcessor(model_backend="auto")
        self.documents = DocumentProcessor()
        self.classifier = IntentClassifier()
        self.router = ServiceRouter()
        self.audit = SecureAuditLog(log_dir="data/security_audit/command_agent")
        self.sessions: Dict[str, CommandContext] = {}

    @staticmethod
    def _detect_language(text: str) -> str:
        return "ar" if any(0x0600 <= ord(ch) <= 0x06FF for ch in text) else "en"

    def process(
        self,
        input_data: Union[str, bytes],
        modality: InputModality,
        context: CommandContext = None,
        file_path: str = None,
    ) -> CommandResponse:
        """Process one command through normalization, intent routing, and response."""
        started = time.perf_counter()
        input_id = f"in-{uuid.uuid4().hex[:10]}"

        text_content = ""
        language = "en"
        structured = None

        if modality == InputModality.VOICE:
            out = self.voice.transcribe(input_data if isinstance(input_data, (bytes, bytearray)) else b"", language="auto")
            text_content = out.get("text", "")
            language = out.get("language", "en")
            structured = out
        elif modality == InputModality.TEXT:
            text_content = str(input_data)
            language = self._detect_language(text_content)
        elif modality == InputModality.PDF:
            structured = self.documents.process_pdf(file_path or str(input_data))
            text_content = structured.get("text", "")
            language = structured.get("language", "en")
        elif modality == InputModality.SPREADSHEET:
            structured = self.documents.process_spreadsheet(file_path or str(input_data))
            text_content = structured.get("summary", "")
            language = "en"
        elif modality == InputModality.IMAGE:
            structured = self.documents.process_image(file_path or str(input_data))
            text_content = structured.get("description", "")
            language = "en"
        else:
            text_content = str(input_data)
            language = self._detect_language(text_content)

        if context is None:
            context = self.create_session("default-commander", "Captain", language, "unknown")

        cmd_input = CommandInput(
            input_id=input_id,
            modality=modality,
            raw_content=input_data,
            text_content=text_content,
            language=language,
            file_path=file_path,
            file_type=None,
            timestamp=datetime.now(timezone.utc),
        )

        intent, conf = self.classifier.classify(text_content, context)
        entities = self.classifier.extract_entities(text_content, intent)
        route_result = self.router.route(intent, entities, context, text_content)
        response = self.router.compose_response(route_result, context)
        response.input_id = cmd_input.input_id
        response.intent = intent
        response.confidence = conf
        response.response_time_ms = (time.perf_counter() - started) * 1000.0
        if structured is not None:
            response.structured_data = {**(response.structured_data or {}), "input_processing": structured}

        context.conversation_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "input": "[REDACTED]" if "classified" in context.permissions else text_content,
                "intent": intent.value,
                "response_en": response.text_en,
            }
        )
        context.conversation_history = context.conversation_history[-20:]

        self.audit.log(
            action="command_processed",
            source="command_agent",
            details={
                "input_id": cmd_input.input_id,
                "intent": intent.value,
                "language": language,
                "confidence": conf,
                "session_id": context.session_id,
            },
        )
        return response

    def create_session(self, commander_id, rank, language, region) -> CommandContext:
        """Create and register a commander interaction session."""
        session_id = f"sess-{uuid.uuid4().hex[:10]}"
        ctx = CommandContext(
            session_id=session_id,
            commander_id=commander_id,
            commander_rank=rank,
            commander_language=language,
            active_mission=None,
            conversation_history=[],
            current_region=region,
            permissions=["standard"],
        )
        self.sessions[session_id] = ctx
        return ctx

    def get_session(self, session_id) -> Optional[CommandContext]:
        """Return commander session by session ID."""
        return self.sessions.get(session_id)

    def get_conversation_history(self, session_id, limit=20) -> List[dict]:
        """Return recent conversation history for specified session."""
        session = self.get_session(session_id)
        if session is None:
            return []
        return session.conversation_history[-max(1, int(limit)) :]

    def health_check(self) -> dict:
        """Return command-agent subsystem health indicators."""
        return {
            "status": "operational",
            "voice": self.voice.get_model_info(),
            "sessions": len(self.sessions),
            "services": {
                "router": "ready",
                "intent_classifier": "ready",
                "document_processor": "ready",
            },
        }

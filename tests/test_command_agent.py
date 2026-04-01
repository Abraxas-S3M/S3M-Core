"""Unit tests for AI command-and-control agent.

Military context:
Tests validate multimodal command understanding and safe routing across tactical
services for bilingual commander interactions.
"""

from pathlib import Path

from services.command_agent.command_agent import CommandAgent
from services.command_agent.document_processor import DocumentProcessor
from services.command_agent.intent_classifier import IntentClassifier
from services.command_agent.models import CommandIntent, InputModality
from services.command_agent.service_router import ServiceRouter
from services.command_agent.voice_processor import VoiceProcessor


def test_intent_classifier_move_unit():
    ic = IntentClassifier()
    intent, _ = ic.classify("Send 2 drones to grid 500,300", None)
    assert intent == CommandIntent.MOVE_UNIT


def test_intent_classifier_query_threats():
    ic = IntentClassifier()
    intent, _ = ic.classify("What is the threat level?", None)
    assert intent == CommandIntent.QUERY_THREATS


def test_intent_classifier_arabic_rtb_maps_to_move_unit():
    ic = IntentClassifier()
    intent, _ = ic.classify("عودة للقاعدة", None)
    assert intent == CommandIntent.MOVE_UNIT


def test_document_processor_spreadsheet_detects_personnel_data(tmp_path: Path):
    p = tmp_path / "personnel.csv"
    p.write_text("name,rank,unit\nAli,CPT,1st\n", encoding="utf-8")
    dp = DocumentProcessor()
    out = dp.process_spreadsheet(str(p))
    assert out["detected_type"] == "personnel"


def test_service_router_routes_query_threats_to_threat_manager():
    router = ServiceRouter()
    ctx = CommandAgent().create_session("cmdr", "Captain", "en", "alpha")
    out = router.route(CommandIntent.QUERY_THREATS, {}, ctx, "What is the threat level?")
    assert out["service"] == "threat_manager"


def test_service_router_routes_analyze_risk_to_risk_engine():
    router = ServiceRouter()
    ctx = CommandAgent().create_session("cmdr", "Captain", "en", "alpha")
    out = router.route(CommandIntent.ANALYZE_RISK, {}, ctx, "Analyze mission risk")
    assert out["service"] == "risk_engine"


def test_command_agent_process_text_command_end_to_end():
    agent = CommandAgent()
    ctx = agent.create_session("cmdr", "Captain", "en", "alpha")
    resp = agent.process("What is the threat level in sector alpha?", InputModality.TEXT, context=ctx)
    assert resp.intent == CommandIntent.QUERY_THREATS
    assert resp.text_en


def test_conversation_history_maintained_across_commands():
    agent = CommandAgent()
    ctx = agent.create_session("cmdr", "Captain", "en", "alpha")
    agent.process("What is the threat level?", InputModality.TEXT, context=ctx)
    agent.process("Analyze risk for route bravo", InputModality.TEXT, context=ctx)
    hist = agent.get_conversation_history(ctx.session_id)
    assert len(hist) >= 2


def test_voice_processor_returns_stub_when_no_model_installed():
    vp = VoiceProcessor(model_backend="auto")
    out = vp.transcribe(b"", language="auto")
    if vp.backend == "stub":
        assert "VOICE_NOT_AVAILABLE" in out["text"]
    else:
        assert "text" in out

"""FastAPI routes for AI command and control agent.

Military context:
These endpoints expose secure commander-facing multimodal interactions to query,
control, and analyze tactical systems in English and Arabic.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.command_agent.command_agent import CommandAgent
from services.command_agent.models import CommandIntent, InputModality


router = APIRouter()
_AGENT = CommandAgent()


@router.post("/command/text")
async def command_text(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process text command from commander."""
    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    language = payload.get("language", "en")
    ctx = _AGENT.create_session(
        payload.get("commander_id", "cmdr"),
        payload.get("rank", "Captain"),
        language,
        payload.get("region", "unknown"),
    )
    resp = _AGENT.process(text, InputModality.TEXT, context=ctx)
    return resp.__dict__


@router.post("/command/voice")
async def command_voice(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process voice command audio bytes."""
    audio = payload.get("audio_bytes", b"")
    if isinstance(audio, str):
        audio = audio.encode("utf-8")
    ctx = _AGENT.create_session(
        payload.get("commander_id", "cmdr"),
        payload.get("rank", "Captain"),
        "en",
        payload.get("region", "unknown"),
    )
    resp = _AGENT.process(audio, InputModality.VOICE, context=ctx)
    return resp.__dict__


@router.post("/command/upload/pdf")
async def command_upload_pdf(file: UploadFile = File(...), commander_id: str = Form("cmdr")) -> Dict[str, Any]:
    """Process uploaded PDF command/intel file."""
    path = f"/tmp/{file.filename}"
    with open(path, "wb") as handle:
        handle.write(await file.read())
    ctx = _AGENT.create_session(commander_id, "Captain", "en", "unknown")
    resp = _AGENT.process(path, InputModality.PDF, context=ctx, file_path=path)
    return resp.__dict__


@router.post("/command/upload/spreadsheet")
async def command_upload_spreadsheet(file: UploadFile = File(...), commander_id: str = Form("cmdr")) -> Dict[str, Any]:
    """Process uploaded spreadsheet file for tactical ingestion."""
    path = f"/tmp/{file.filename}"
    with open(path, "wb") as handle:
        handle.write(await file.read())
    ctx = _AGENT.create_session(commander_id, "Captain", "en", "unknown")
    resp = _AGENT.process(path, InputModality.SPREADSHEET, context=ctx, file_path=path)
    return resp.__dict__


@router.post("/command/upload/image")
async def command_upload_image(file: UploadFile = File(...), commander_id: str = Form("cmdr")) -> Dict[str, Any]:
    """Process uploaded tactical image file."""
    path = f"/tmp/{file.filename}"
    with open(path, "wb") as handle:
        handle.write(await file.read())
    ctx = _AGENT.create_session(commander_id, "Captain", "en", "unknown")
    resp = _AGENT.process(path, InputModality.IMAGE, context=ctx, file_path=path)
    return resp.__dict__


@router.post("/command/session")
async def create_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create commander session context."""
    session = _AGENT.create_session(
        commander_id=payload.get("commander_id", "cmdr"),
        rank=payload.get("rank", "Captain"),
        language=payload.get("language", "en"),
        region=payload.get("region", "unknown"),
    )
    return session.__dict__


@router.get("/command/session/{id}")
async def get_session(id: str) -> Dict[str, Any]:
    """Get commander session and conversation history."""
    session = _AGENT.get_session(id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": session.__dict__, "conversation_history": session.conversation_history}


@router.get("/command/intents")
async def intents() -> Dict[str, Any]:
    """List supported command intents."""
    return {"intents": [i.value for i in CommandIntent]}


@router.get("/command/status")
async def status() -> Dict[str, Any]:
    """Return command-agent health and capability status."""
    return _AGENT.health_check()

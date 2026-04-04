"""AI Chat endpoint for the GUI AI Panel.

Routes natural language queries to the S3M quad-engine inference system.
Supports Arabic/English bilingual via ALLaM engine routing.
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

ai_router = APIRouter(prefix="/ai", tags=["GUI AI Chat"])


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096)
    workspace: Optional[str] = None
    language: str = "EN"


class ChatResponse(BaseModel):
    response: str
    engine: str
    confidence: float
    requestId: str
    workspaceLink: Optional[str] = None


@ai_router.post("/chat", response_model=ChatResponse)
async def ai_chat(req: ChatRequest):
    """Send a natural language query to S3M inference engines."""
    import time
    import uuid

    # Import existing inference infrastructure
    from src.api.server import simulate_inference, state

    # Route Arabic to ALLaM, else use domain routing
    if req.language.upper() == "AR":
        engine = "allam"
    elif req.workspace:
        domain_map = {
            "command": "tactical",
            "cop": "tactical",
            "decisions": "tactical",
            "risk": "intelligence",
            "planning": "tactical",
            "sustainment": "logistics",
            "readiness": "tactical",
            "cyber": "intelligence",
            "simulation": "tactical",
            "communication": "tactical",
            "surveillance": "intelligence",
        }
        domain = domain_map.get(req.workspace, "general")
        engine = state.resolve_engine(None, domain)
    else:
        engine = state.resolve_engine(None, None)

    # Enrich prompt with workspace context
    context_prefix = f"[Workspace: {req.workspace}] " if req.workspace else ""
    full_prompt = f"{context_prefix}{req.prompt}"

    result = simulate_inference(engine, full_prompt, 512, 0.7)

    return ChatResponse(
        response=result["text"],
        engine=engine,
        confidence=0.85 if result.get("live") else 0.6,
        requestId=f"chat-{uuid.uuid4().hex[:8]}",
        workspaceLink=req.workspace,
    )

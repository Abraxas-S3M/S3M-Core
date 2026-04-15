"""FastAPI routes for APP-11 XML-MTF interoperability exchange."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.interop.mtf import MTFFormatter, MTFTransport
from src.api.config import api_config

mtf_router = APIRouter()
_formatter = MTFFormatter(
    config={
        "originator": getattr(api_config, "mtf_originator", "S3M INTEL CENTER"),
        "namespace": getattr(api_config, "mtf_namespace", "urn:nato:mtf:app11d"),
    }
)
_transport = MTFTransport(gateway_url=getattr(api_config, "mtf_gateway_url", None))
if _transport.gateway_url:
    _transport.connect(_transport.gateway_url)


class MTFSendRequest(BaseModel):
    type: str = Field(..., min_length=1, max_length=24)
    content: dict[str, Any] = Field(default_factory=dict)
    classification: str = Field(default="UNCLASSIFIED", min_length=1, max_length=32)
    originator: str | None = Field(default=None, max_length=64)


@mtf_router.post("/interop/mtf/send")
async def send_mtf_message(req: MTFSendRequest) -> dict[str, Any]:
    try:
        xml_payload = _formatter.format_message(
            report_type=req.type,
            content=req.content,
            originator=req.originator or "",
            classification=req.classification,
        )
        parsed = _formatter.parse_message(xml_payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    queued = _transport.push_message(
        xml_str=xml_payload,
        message_type=parsed["message_type"],
        metadata={
            "originator": parsed["originator"],
            "classification": parsed["classification"],
            "serial_number": parsed["serial_number"],
            "datetime_group": parsed["datetime_group"],
        },
    )
    return {
        "status": queued.get("status", "unknown"),
        "message_type": parsed["message_type"],
        "serial_number": parsed["serial_number"],
        "datetime_group": parsed["datetime_group"],
        "transport": queued,
    }


@mtf_router.get("/interop/mtf/outbox")
async def list_mtf_outbox() -> list[dict[str, Any]]:
    return _transport.list_outbox()


@mtf_router.get("/interop/mtf/status")
async def mtf_status() -> dict[str, Any]:
    return {
        "formatter": {
            "namespace": _formatter.namespace,
            "default_originator": _formatter.default_originator,
            "supported_types": sorted(MTFFormatter.SUPPORTED_TYPES),
        },
        "transport": _transport.get_server_status(),
    }

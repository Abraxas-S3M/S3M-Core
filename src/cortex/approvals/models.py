"""Pydantic models for the out-of-band approvals FastAPI surface."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=128)
    public_key_b64: str = Field(min_length=16)
    approver_label: str = Field(min_length=1, max_length=256)
    duress_pin: str = Field(min_length=4, max_length=32)

    @field_validator("device_id", "approver_label")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class AdminRegistrationVote(BaseModel):
    admin_id: str = Field(min_length=1, max_length=128)
    registration_id: str


class ChangeRequestBody(BaseModel):
    envelope_id: str
    change_class: Literal["C", "D"]
    proposer_device_id: str
    proposer_session_id: str
    diff: str
    risk_before: Dict[str, Any] = Field(default_factory=dict)
    risk_after: Dict[str, Any] = Field(default_factory=dict)
    blast_radius: Dict[str, Any] = Field(default_factory=dict)
    rollback_steps: List[str] = Field(default_factory=list)
    interpreter_context: str = ""


class ApprovalSubmitBody(BaseModel):
    envelope_id: str
    decision: Literal["APPROVE", "DENY"]
    timestamp: str
    nonce: str
    signature_b64: str
    duress_pin: Optional[str] = None


class KillActionBody(BaseModel):
    holder_device_id: str


class DevicePayloadResponse(BaseModel):
    change_id: str
    envelope_id: str
    summary_en: str
    summary_ar: str
    summaries_machine_generated: bool = True
    diff: str
    risk_before: Dict[str, Any]
    risk_after: Dict[str, Any]
    blast_radius: Dict[str, Any]
    rollback_steps: List[str]


class ApprovalSubmitResponse(BaseModel):
    ui_decision: str
    recorded_decision: str
    alert_raised: bool = False
    blocked: bool = False

"""Standalone FastAPI app for cortex approvals (mTLS + audit)."""

from __future__ import annotations

from fastapi import FastAPI

from src.cortex.approvals.routes import approvals_router, bind_service
from src.cortex.approvals.service import ApprovalService


def create_approvals_app(service: ApprovalService | None = None) -> FastAPI:
    app = FastAPI(title="S3M Cortex Out-of-Band Approvals", version="1.0.0")
    if service is not None:
        bind_service(service)
    app.include_router(approvals_router)
    return app

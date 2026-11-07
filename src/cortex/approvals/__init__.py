"""Out-of-band approver device API for class C/D change control."""

from src.cortex.approvals.app import create_approvals_app
from src.cortex.approvals.service import ApprovalService

__all__ = ["ApprovalService", "create_approvals_app"]

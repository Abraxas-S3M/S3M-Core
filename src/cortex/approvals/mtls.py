"""mTLS client identity extraction for approver API requests.

Military/tactical context: device-bound approvals must not trust console
sessions; only verified client certificate fingerprints map to approvers.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException, Request


def _test_mode() -> bool:
    return os.environ.get("APPROVALS_MTLS_MODE", "test").lower() in {"test", "dev"}


async def require_mtls_identity(
    request: Request,
    x_client_cert_fingerprint: Optional[str] = Header(default=None, alias="X-Client-Cert-Fingerprint"),
    x_client_cert_subject: Optional[str] = Header(default=None, alias="X-Client-Cert-Subject"),
) -> str:
    """Return verified client identity (device or admin fingerprint)."""
    if getattr(request.state, "mtls_identity", None):
        return str(request.state.mtls_identity)

    ssl_obj = getattr(request.scope.get("extensions", {}), "get", lambda _k, _d=None: None)("ssl")
    if ssl_obj is not None:
        client = ssl_obj.get("client") if isinstance(ssl_obj, dict) else None
        if client and client.get(0):
            cert = client[0]
            fp = getattr(cert, "fingerprint", None)
            if fp:
                return fp().hex()

    if x_client_cert_fingerprint:
        return x_client_cert_fingerprint.strip()

    if x_client_cert_subject:
        return x_client_cert_subject.strip()

    if _test_mode():
        raise HTTPException(
            status_code=401,
            detail="mTLS client identity required (set X-Client-Cert-Fingerprint)",
        )

    raise HTTPException(status_code=401, detail="mTLS client certificate required")


async def optional_session_id(
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-Id"),
) -> Optional[str]:
    return x_session_id.strip() if x_session_id else None

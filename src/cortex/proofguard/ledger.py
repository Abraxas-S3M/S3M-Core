"""ProofGuard dual-ledger reconciliation.

Military/tactical context:
Cortex keeps its own record of every write it sent; the control plane keeps its own record
of every change it applied and signs a receipt for each. Neither side is trusted alone.
Reconciling the two ledgers exposes what a single log cannot:

* MISSING_IN_CONTROL_PLANE   Cortex holds a receipt the control plane's ledger omits.
* UNACCOUNTED_CHANGE         The control plane applied a change Cortex never sent - a rogue
                             agent, an out-of-band administrator, or stolen credentials.
                             Critical when it carries Cortex's own client id.
* RECEIPT_DIGEST_MISMATCH    The receipt does not hash to what Cortex sent and received.
* RECEIPT_SIGNATURE_INVALID  The receipt is not signed by the pinned control-plane key.
* APPROVAL_MISMATCH          The receipt cites a different approval than Cortex attached.
* ACKNOWLEDGED_NOT_APPLIED   A valid signed receipt exists but Cortex's independent
                             observation shows the change did not take effect: the
                             control plane is on record claiming a change it did not make.

Cryptographic integrity proves *who said what*; it does not prove a decision was right.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _record_bytes(record: Mapping[str, Any]) -> bytes:
    # Must match the control plane's signer exactly (RecordSigner.sign_record).
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")


def reconstruct_record(write: Mapping[str, Any]) -> Dict[str, Any]:
    """Rebuild the record the control plane signed, from what Cortex sent and received."""
    resp = write["response"]
    receipt = resp["receipt"]
    return {
        "tool": write["tool"],
        "request_id": receipt["request_id"],
        "client_id": write["client_id"],
        "arguments": dict(write["arguments"]),
        "result": next(v for k, v in resp.items() if k != "receipt"),
        "approval_jti": receipt.get("approval_jti", ""),
        "applied_at": receipt["applied_at"],
    }


def verify_receipt(write: Mapping[str, Any], receipt_public_key_b64: str) -> List[str]:
    problems = []
    receipt = write["response"]["receipt"]
    payload = _record_bytes(reconstruct_record(write))
    if hashlib.sha256(payload).hexdigest() != receipt["record_digest"]:
        problems.append("RECEIPT_DIGEST_MISMATCH")
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(receipt_public_key_b64))
        key.verify(base64.urlsafe_b64decode(receipt["signature_b64"]), payload)
    except Exception:
        problems.append("RECEIPT_SIGNATURE_INVALID")
    token = write.get("approval")
    if token:
        try:
            jti = jwt.decode(token, options={"verify_signature": False}).get("jti")
        except jwt.PyJWTError:
            jti = None
        if jti != receipt.get("approval_jti"):
            problems.append("APPROVAL_MISMATCH")
    return problems


@dataclass
class Discrepancy:
    kind: str
    severity: str
    receipt_digest: Optional[str]
    detail: str


@dataclass
class Reconciliation:
    cortex_writes: int
    control_plane_changes: int
    matched: int
    discrepancies: List[Discrepancy] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.discrepancies

    def to_dict(self) -> Dict[str, Any]:
        return {"cortex_writes": self.cortex_writes, "control_plane_changes": self.control_plane_changes,
                "matched": self.matched, "clean": self.clean,
                "discrepancies": [asdict(d) for d in self.discrepancies]}


def reconcile(
    cortex_writes: Sequence[Mapping[str, Any]],
    control_plane_events: Iterable[Mapping[str, Any]],
    *,
    receipt_public_key_b64: str,
    cortex_client_id: str,
    observed_failures: Optional[Iterable[str]] = None,
) -> Reconciliation:
    """``observed_failures``: receipt digests whose postcondition Cortex saw fail."""
    plane = {}
    for ev in control_plane_events:
        if ev.get("type") == "change.applied":
            plane[str(ev["attributes"].get("s3m.receipt.digest"))] = ev
    ours: Dict[str, Mapping[str, Any]] = {}
    out = Reconciliation(cortex_writes=0, control_plane_changes=len(plane), matched=0)
    for w in cortex_writes:
        receipt = w["response"]["receipt"]
        if receipt.get("replayed"):
            continue  # idempotent replay of an already-ledgered write
        digest = receipt["record_digest"]
        ours[digest] = w
        out.cortex_writes += 1
        for p in verify_receipt(w, receipt_public_key_b64):
            out.discrepancies.append(Discrepancy(p, "critical", digest, f"{w['tool']} {w['arguments']}"))
        if digest in plane:
            out.matched += 1
        else:
            out.discrepancies.append(Discrepancy("MISSING_IN_CONTROL_PLANE", "high", digest,
                                                 f"{w['tool']} receipted but absent from control-plane ledger"))
    for digest, ev in plane.items():
        if digest not in ours:
            who = str(ev["attributes"].get("client.id"))
            sev = "critical" if who == cortex_client_id else "high"
            out.discrepancies.append(Discrepancy(
                "UNACCOUNTED_CHANGE", sev, digest,
                f"{ev['attributes'].get('s3m.tool')} on {ev['attributes'].get('s3m.resource')} by {who} "
                + ("using Cortex's identity but not sent by Cortex" if sev == "critical" else "outside Cortex"),
            ))
    for digest in observed_failures or []:
        if digest in ours:
            out.discrepancies.append(Discrepancy("ACKNOWLEDGED_NOT_APPLIED", "high", digest,
                                                 "signed receipt exists but observed state shows no effect"))
    return out

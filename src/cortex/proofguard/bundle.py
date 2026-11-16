"""ProofGuard case bundle: one signed, self-verifying record of a defense cycle.

Military/tactical context:
After an incident, a reviewer outside the operating unit must be able to reconstruct what
Cortex saw, decided, was approved to do, actually sent, what the control plane signed for,
and what was observed afterwards - and detect any altered, reordered or missing record -
using only the bundle and two public keys.

Bundle contents: cycle report, the complete Cortex Merkle audit log (lines verbatim), its
head (entry count, last hash, Merkle root), Cortex's write ledger with control-plane
receipts, the control-plane change ledger, the dual-ledger reconciliation, and an Ed25519
signature by the evidence key over all of it.

    python -m src.cortex.proofguard.bundle verify case.json --evidence-key <b64> --receipt-key <b64>
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from s3m_core.defense.audit.merkle_log import MerkleAuditLog
from src.cortex.proofguard.ledger import reconcile

SCHEMA = "s3m.cortex.evidence/0.1"


def _canonical(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def public_key_b64(key: Ed25519PrivateKey) -> str:
    return base64.urlsafe_b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def observed_failures(report: Mapping[str, Any], writes: Sequence[Mapping[str, Any]]) -> List[str]:
    """Receipt digests of writes whose postcondition Cortex observed to fail."""
    failed = []
    failure = (report.get("verification") or {}).get("failure") or {}
    if failure.get("reason") != "postcondition_mismatch":
        return failed
    change = next((c for c in report.get("changes", []) if c["change_id"] == failure["change_id"]), None)
    if change is None:
        return failed
    for w in writes:
        if w["arguments"].get("route_id") == change["route_id"] and not w["response"]["receipt"].get("replayed"):
            # the forward write for this change (its rollback is a different tool or prefix)
            if w["tool"].split(".")[-1] in change["xiid_action"]:
                failed.append(w["response"]["receipt"]["record_digest"])
    return failed


def build_bundle(
    *,
    report: Mapping[str, Any],
    audit_log_path: Path,
    cortex_writes: Sequence[Mapping[str, Any]],
    control_plane_events: Sequence[Mapping[str, Any]],
    cortex_client_id: str,
    receipt_public_key_b64: str,
    evidence_key: Ed25519PrivateKey,
) -> Dict[str, Any]:
    lines = [ln for ln in Path(audit_log_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    last = json.loads(lines[-1]) if lines else {}
    writes = [dict(w) for w in cortex_writes]
    events = [dict(e) for e in control_plane_events if e.get("type") == "change.applied"]
    rec = reconcile(writes, events, receipt_public_key_b64=receipt_public_key_b64,
                    cortex_client_id=cortex_client_id, observed_failures=observed_failures(report, writes))
    body = {
        "schema": SCHEMA,
        "case_id": report["case_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report": dict(report),
        "audit_log": lines,
        "audit_head": {"entries": len(lines), "last_entry_hash": last.get("entry_hash"),
                       "merkle_root": last.get("merkle_root")},
        "cortex_writes": writes,
        "control_plane_events": events,
        "cortex_client_id": cortex_client_id,
        "reconciliation": rec.to_dict(),
        "keys": {"evidence_public_key_b64": public_key_b64(evidence_key),
                 "receipt_public_key_b64": receipt_public_key_b64},
    }
    body["signature_b64"] = base64.urlsafe_b64encode(evidence_key.sign(_canonical(body))).decode()
    return body


def verify_bundle(bundle: Mapping[str, Any], *, evidence_public_key_b64: str,
                  receipt_public_key_b64: str) -> Dict[str, Any]:
    """Independent verification. Keys are supplied by the reviewer, never taken from the bundle."""
    problems: List[str] = []
    body = {k: v for k, v in bundle.items() if k != "signature_b64"}
    try:
        Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(evidence_public_key_b64)).verify(
            base64.urlsafe_b64decode(str(bundle.get("signature_b64", ""))), _canonical(body))
    except Exception:
        problems.append("BUNDLE_SIGNATURE_INVALID")
    if bundle.get("keys", {}).get("receipt_public_key_b64") != receipt_public_key_b64:
        problems.append("RECEIPT_KEY_NOT_PINNED_VALUE")

    lines = list(bundle.get("audit_log", []))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        integrity = MerkleAuditLog(str(path)).verify_integrity()
    if not integrity.chain_intact:
        problems.append(f"AUDIT_CHAIN_BROKEN at entry {integrity.first_broken_entry}")
    head = bundle.get("audit_head", {})
    last = json.loads(lines[-1]) if lines else {}
    if head.get("entries") != len(lines) or head.get("last_entry_hash") != last.get("entry_hash") \
            or head.get("merkle_root") != last.get("merkle_root"):
        problems.append("AUDIT_HEAD_MISMATCH (truncated or extended log)")

    writes = bundle.get("cortex_writes", [])
    report = bundle.get("report", {})
    rec = reconcile(writes, bundle.get("control_plane_events", []), receipt_public_key_b64=receipt_public_key_b64,
                    cortex_client_id=str(bundle.get("cortex_client_id")),
                    observed_failures=observed_failures(report, writes))
    if rec.to_dict() != bundle.get("reconciliation"):
        problems.append("RECONCILIATION_DOES_NOT_RECOMPUTE")

    # Every change the report calls executed must have a receipted write.
    receipted = {(w["tool"].split(".")[-1], w["arguments"].get("route_id")) for w in writes}
    for ch in report.get("changes", []):
        if ch.get("state") in {"verified", "executed", "rolled_back"}:
            if (ch["xiid_action"].split("_")[0], ch["route_id"]) not in receipted:
                problems.append(f"CHANGE_WITHOUT_RECEIPT {ch['change_id']}")
    # Every completed write in the audit log must be in the write ledger, and vice versa.
    from src.cortex.mcp_contract.manifest import load_contract

    contract = load_contract()
    completed = [json.loads(ln)["details"]["tool"] for ln in lines
                 if json.loads(ln).get("event_type") == "mcp_tool_result"
                 and json.loads(ln)["details"].get("tool") in contract.tools
                 and contract.tool(json.loads(ln)["details"]["tool"]).is_write]
    if sorted(completed) != sorted(w["tool"] for w in writes):
        problems.append(f"WRITE_LEDGER_MISMATCH audit={len(completed)} ledger={len(writes)}")
    return {"valid": not problems, "problems": problems, "audit": integrity.to_dict(),
            "reconciliation": rec.to_dict()}


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify a ProofGuard case bundle offline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("bundle", type=Path)
    v.add_argument("--evidence-key", required=True)
    v.add_argument("--receipt-key", required=True)
    args = ap.parse_args(argv)
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    result = verify_bundle(bundle, evidence_public_key_b64=args.evidence_key, receipt_public_key_b64=args.receipt_key)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())

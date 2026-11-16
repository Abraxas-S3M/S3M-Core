"""ProofGuard: dual-ledger reconciliation and offline case-bundle verification.

Military/tactical context:
An after-action reviewer outside the unit must be able to trust the record of what Cortex
did - and to detect tampering, deletion, out-of-band changes and a control plane that
signs for changes it did not make - using only the bundle and two public keys.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from range.run_contract_cycle import case_bundle, contract_range, run_contract_cycle
from src.cortex.mcp_contract.client import ContractMCPTransport
from src.cortex.mcp_contract.manifest import load_contract
from src.cortex.proofguard import bundle as pg
from src.cortex.proofguard.bundle import public_key_b64, verify_bundle

pytestmark = pytest.mark.cortex


def _resign(b, key):
    body = {k: v for k, v in b.items() if k != "signature_b64"}
    b["signature_b64"] = base64.urlsafe_b64encode(key.sign(pg._canonical(body))).decode()
    return b


@pytest.fixture
def case(tmp_path):
    key = Ed25519PrivateKey.generate()
    with contract_range() as rng:
        report, tr = asyncio.run(run_contract_cycle(rng, workdir=tmp_path, case_id="t-pg"))
        yield rng, report, tr, key, case_bundle(rng, report, tr, tmp_path, key)


def _verify(rng, key, b):
    return verify_bundle(b, evidence_public_key_b64=public_key_b64(key),
                         receipt_public_key_b64=rng.state.signer.public_key_b64)


def test_clean_cycle_reconciles_and_verifies(case) -> None:
    rng, report, tr, key, b = case
    assert report.outcome == "verified"
    assert b["reconciliation"]["clean"] and b["reconciliation"]["matched"] == 4
    assert _verify(rng, key, b) == {**_verify(rng, key, b), "valid": True, "problems": []}


def test_tampered_audit_entry_detected(case) -> None:
    rng, _, _, key, b = case
    t = copy.deepcopy(b)
    entry = json.loads(t["audit_log"][3])
    entry["details"]["tool"] = "route.restore"
    t["audit_log"][3] = json.dumps(entry)
    problems = _verify(rng, key, t)["problems"]
    assert "BUNDLE_SIGNATURE_INVALID" in problems and any(p.startswith("AUDIT_CHAIN_BROKEN") for p in problems)
    # Even an attacker holding the evidence key cannot hide an edited entry: the chain breaks.
    assert any(p.startswith("AUDIT_CHAIN_BROKEN") for p in _verify(rng, key, _resign(t, key))["problems"])


def test_truncated_log_detected(case) -> None:
    rng, _, _, key, b = case
    t = copy.deepcopy(b)
    t["audit_log"] = t["audit_log"][:-3]
    problems = _verify(rng, key, t)["problems"]
    assert "BUNDLE_SIGNATURE_INVALID" in problems and any(p.startswith("AUDIT_HEAD_MISMATCH") for p in problems)


def test_deleted_write_detected_even_if_resigned(case) -> None:
    rng, _, _, key, b = case
    t = copy.deepcopy(b)
    t["cortex_writes"] = t["cortex_writes"][1:]
    problems = _verify(rng, key, _resign(t, key))["problems"]
    assert "RECONCILIATION_DOES_NOT_RECOMPUTE" in problems
    assert any(p.startswith("WRITE_LEDGER_MISMATCH") for p in problems)


def test_forged_receipt_detected(case) -> None:
    rng, _, tr, key, b = case
    t = copy.deepcopy(b)
    t["cortex_writes"][0]["response"]["route"]["status"] = "active"  # claim a different result
    rec = verify_bundle(_resign(t, key), evidence_public_key_b64=public_key_b64(key),
                        receipt_public_key_b64=rng.state.signer.public_key_b64)["reconciliation"]
    kinds = {d["kind"] for d in rec["discrepancies"]}
    assert {"RECEIPT_DIGEST_MISMATCH", "RECEIPT_SIGNATURE_INVALID"} <= kinds


def _rogue_write(rng, transport_factory, route_id="rt-mail-file"):
    async def go():
        c = transport_factory()
        await c.pin_contract()
        args = {"route_id": route_id}
        tok = rng.approval_authority.issue(client_id=c.identity.client_id, resource=rng.url, tool="route.expire",
                                           arguments=args, approval_ids=["x"])
        await c._raw_call("route.expire", {**args, "approval": tok, "idempotency_key": "rogue-000001"})
        await c.close()

    asyncio.run(go())


def test_out_of_band_change_is_unaccounted(case, tmp_path) -> None:
    rng, report, tr, key, _ = case
    _rogue_write(rng, lambda: rng.client("ops-admin-7"))
    b = case_bundle(rng, report, tr, tmp_path, key)
    d = [x for x in b["reconciliation"]["discrepancies"] if x["kind"] == "UNACCOUNTED_CHANGE"]
    assert len(d) == 1 and d[0]["severity"] == "high" and "ops-admin-7" in d[0]["detail"]


def test_stolen_cortex_identity_is_critical(case, tmp_path) -> None:
    rng, report, tr, key, _ = case

    def clone_of_cortex():
        return ContractMCPTransport(url=rng.url, resource=rng.url, identity=tr.identity,
                                    authorization_server=rng.authorization_server,
                                    sandbox=rng.sandboxes["sbx-change-limited"], contract=load_contract(),
                                    contract_authority_key=rng.manifest_public_key)

    _rogue_write(rng, clone_of_cortex)
    b = case_bundle(rng, report, tr, tmp_path, key)
    d = [x for x in b["reconciliation"]["discrepancies"] if x["kind"] == "UNACCOUNTED_CHANGE"]
    assert len(d) == 1 and d[0]["severity"] == "critical"


def test_acknowledged_but_not_applied(tmp_path) -> None:
    key = Ed25519PrivateKey.generate()
    with contract_range() as rng:
        rng.state.drop_next_write, rng.state.drop_write_skip = True, 1
        report, tr = asyncio.run(run_contract_cycle(rng, workdir=tmp_path, case_id="t-pg-drop"))
        b = case_bundle(rng, report, tr, tmp_path, key)
        assert report.outcome == "rolled_back"
        kinds = [d["kind"] for d in b["reconciliation"]["discrepancies"]]
        assert kinds == ["ACKNOWLEDGED_NOT_APPLIED"]
        assert _verify(rng, key, b)["valid"]  # the evidence itself is intact; the discrepancy is the finding


def test_cli_exit_codes(case, tmp_path) -> None:
    rng, _, _, key, b = case
    good = tmp_path / "good.json"
    good.write_text(json.dumps(b))
    args = ["verify", str(good), "--evidence-key", public_key_b64(key),
            "--receipt-key", rng.state.signer.public_key_b64]
    assert pg.main(args) == 0
    bad = copy.deepcopy(b)
    bad["report"]["outcome"] = "verified-by-hand"
    badp = tmp_path / "bad.json"
    badp.write_text(json.dumps(bad))
    assert pg.main(["verify", str(badp), *args[2:]]) == 2


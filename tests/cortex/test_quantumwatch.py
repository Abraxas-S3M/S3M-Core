"""QuantumWatch: inventory, classification, compliance and migration planning.

Military/tactical context:
The inventory must find real crypto with evidence and without false confidence; the plan
must meet the profile's dates, respect engineering capacity and dependencies, and say
which part of its benefit rests on an unverified vendor claim.
"""

from __future__ import annotations

import functools

from pathlib import Path

import pytest
import yaml

pytest.importorskip("ortools")

from src.cortex.quantumwatch.catalog import approved, get  # noqa: E402
from src.cortex.quantumwatch.discovery import infer_fabric, load_declared, reconcile, scan_python  # noqa: E402
from src.cortex.quantumwatch.planner import CRQC, needs_migration, plan, span  # noqa: E402
from src.cortex.quantumwatch.watch import assess, load_profiles, status_of, to_plan_assets  # noqa: E402

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
S = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
OVERLAY = ROOT / "range/enterprise/crypto_enterprise_200.yaml"
CFG = load_profiles()
NIST, CNSA = CFG["profiles"]["nist-ir8547"], CFG["profiles"]["cnsa-2.0"]

SAMPLE = '''
import hashlib, ssl, jwt, oqs
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.fernet import Fernet
key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
cache = hashlib.md5(b"x", usedforsecurity=False)
digest = hashlib.sha256(b"x")
token = jwt.encode({}, key, algorithm="RS256")
kem = oqs.KeyEncapsulation(mechanism)
box = Fernet(Fernet.generate_key())
ctx = ssl.create_default_context()
'''


@functools.lru_cache(maxsize=None)
def _cached(items):
    kw = dict(items)
    return assess(routes=S["routes"], crypto_overlay=OVERLAY, code_paths=list((ROOT / "src/cortex").rglob("*.py")),
                  declared_inventory=ROOT / "configs/cortex/cbom_inventory.yaml", **kw)


def _assess(**kw):
    return _cached(tuple(sorted(kw.items())))


def test_profiles_classify_correctly() -> None:
    assert not approved(get("ed25519"), NIST) and not approved(get("rsa-4096"), CNSA)
    assert approved(get("ml-kem-768"), NIST) and not approved(get("ml-kem-768"), CNSA)
    assert approved(get("ml-kem-1024"), CNSA) and approved(get("x25519-ml-kem-768"), NIST)
    assert approved(get("aes-128-gcm"), NIST) and not approved(get("aes-128-gcm"), CNSA)
    assert not approved(get("ml-kem"), NIST)  # parameter set unknown: cannot be approved
    assert not approved(get("xiid-sealedtunnel"), NIST)  # vendor claim until documented


def test_scanner_finds_usage_with_evidence(tmp_path) -> None:
    f = tmp_path / "svc" / "pkg" / "mod.py"
    f.parent.mkdir(parents=True)
    f.write_text(SAMPLE)
    found = {a.algo_id: a for a in scan_python([f], tmp_path)}
    assert {"rsa-3072", "md5", "sha-256", "ml-kem", "aes-128-cbc-hmac", "x25519"} <= set(found)
    assert found["md5"].usage == "non-security" and found["rsa-3072"].location.endswith(":5")
    assert found["rsa-3072"].usage == "authenticity" and found["x25519"].usage == "confidentiality"


def test_scanner_on_cortex_source_finds_real_quantum_vulnerable_signing() -> None:
    found = scan_python(list((ROOT / "src/cortex").rglob("*.py")), ROOT)
    locs = {a.location.split(":")[0] for a in found if a.algo_id == "ed25519"}
    assert {"src/cortex/mcp_contract/tokens.py", "src/cortex/proofguard/ledger.py"} <= locs
    assert not any("quantumwatch" in a.location for a in found)  # the catalogue is not "use"


def test_reconciliation_exposes_inventory_gaps() -> None:
    declared = load_declared(ROOT / "configs/cortex/cbom_inventory.yaml")
    code = scan_python(list((ROOT / "src").rglob("*.py")), ROOT)
    gaps = reconcile(declared, code)
    # The declared inventory says AES-256-GCM for sealed audit entries; the code uses Fernet (AES-128-CBC + HMAC).
    assert "aes-128-cbc-hmac" in gaps["found_in_code_not_declared"]
    assert "ecdsa-p256" in gaps["declared_not_found_in_code"]


def test_fabric_inference_flags_cleartext_and_unverified_overlay() -> None:
    assets = infer_fabric(S["routes"], yaml.safe_load(OVERLAY.read_text())["data_class"])
    status = {a.asset_id: status_of(a, NIST) for a in assets}
    assert status["fabric:rt-users-erp"] == "quantum_vulnerable"
    assert {k for k, v in status.items() if v == "broken_now"} == {
        "fabric:rt-cams-nvr", "fabric:rt-ci-dc", "fabric:rt-users-print"}
    assert sum(v == "claimed_pq_unverified" for v in status.values()) == 12  # one per sealed route


def test_crqc_cdf_is_monotone() -> None:
    c = CRQC(CFG["crqc_cdf"])
    ys = [c.F(2026 + i / 4) for i in range(160)]
    assert all(b >= a for a, b in zip(ys, ys[1:])) and ys[0] < 0.01 and c.F(2100) == 0.97


def test_plan_meets_deadlines_capacity_and_dependencies() -> None:
    r = _assess(profile_id="cnsa-2.0")
    p = r["plan"]
    assert p["status"] == "OPTIMAL" and p["deadline_misses"] == {}
    assert max(p["weeks_used"]) <= 12 + 1e-9
    assert p["native"]["declared:pki-issuing-ca"] > p["native"]["declared:pki-root-ca"]
    assert p["native"]["declared:vpn-ike"] <= "2030Q4"  # CNSA 2.0 networking deadline
    assert all(k.startswith("fabric:") for k in p["overlay"])


def test_optimiser_beats_deadline_first_practice() -> None:
    for prof, cap, gain in [("nist-ir8547", 12, 0.3), ("cnsa-2.0", 12, 0.5), ("cnsa-2.0", 6, 0.5)]:
        r = _assess(profile_id=prof, capacity_weeks=cap)
        assert r["plan"]["risk"] <= (1 - gain) * r["baseline"]["risk"], (prof, cap)
        assert r["baseline"]["deadline_misses"] == {}


def test_overlay_benefit_depends_on_the_vendor_claim() -> None:
    with_claim = _assess(profile_id="nist-ir8547")["plan"]
    no_overlay = _assess(profile_id="nist-ir8547", sealed_overlay_available=False)["plan"]
    claim_fails = _assess(profile_id="nist-ir8547", overlay_residual=1.0)["plan"]
    assert with_claim["risk"] < 0.7 * no_overlay["risk"]
    assert claim_fails["risk"] == pytest.approx(no_overlay["risk"], rel=0.02)


def test_infeasible_deadlines_are_reported_not_hidden() -> None:
    from src.cortex.quantumwatch.discovery import load_declared as ld
    pa = to_plan_assets(ld(OVERLAY))
    p = plan(pa, CNSA, crqc=CRQC(CFG["crqc_cdf"]), years=CFG["data_classes"], capacity_weeks=0.5)
    assert p.status == "DEADLINES_INFEASIBLE" and p.deadline_misses
    assert span(16, 12) == 3 and span(3, 12) == 1


def test_cbom_carries_status_and_evidence() -> None:
    r = _assess()
    comps = r["cbom"]["components"]
    assert r["cbom"]["specVersion"] == "1.6" and len(comps) == len(r["assets"])
    props = {p["name"]: p["value"] for p in comps[0]["properties"]}
    assert {"s3m:quantum_status", "s3m:source", "s3m:confidence"} <= set(props)
    assert all(c["evidence"]["occurrences"][0]["location"] for c in comps)
    assert r["to_migrate"] == sum(needs_migration(a, NIST) for a in to_plan_assets(
        infer_fabric(S["routes"], yaml.safe_load(OVERLAY.read_text())["data_class"])
        + load_declared(OVERLAY) + scan_python(list((ROOT / "src/cortex").rglob("*.py")), ROOT)))

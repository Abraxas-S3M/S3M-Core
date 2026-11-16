"""QuantumWatch orchestration: discover -> classify -> assess -> plan -> CBOM (capability 13).

Military/tactical context:
One report a crypto authority can act on: every cryptographic asset with its evidence and
quantum status, the gaps between what was declared and what was found, compliance against
the chosen profile, and a migration plan that states what it assumes.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml

from src.cortex.quantumwatch.catalog import approved, get
from src.cortex.quantumwatch.discovery import CryptoAsset, infer_fabric, load_declared, reconcile, scan_python
from src.cortex.quantumwatch.planner import CRQC, PlanAsset, baseline_plan, needs_migration, plan

ROOT = Path(__file__).resolve().parents[3]
PROFILES_FILE = ROOT / "configs" / "cortex" / "quantum_profiles.yaml"
FABRIC_CATEGORY = {"ssh": "networking", "rdp": "networking"}


def load_profiles(path: Path = PROFILES_FILE) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def to_plan_assets(assets: Sequence[CryptoAsset], *, sealed_overlay_available: bool = True) -> List[PlanAsset]:
    out = []
    for a in assets:
        if a.algo_id == "xiid-sealedtunnel":
            continue  # the overlay itself is an option, not an asset to migrate
        c = a.context
        if a.source == "fabric":
            capture = 1.0 if c.get("internet_facing") else 0.3
            overlay = (sealed_overlay_available and a.usage == "confidentiality" and not c.get("sealed"))
            if c.get("sealed"):
                capture *= 0.05  # already inside a SealedTunnel (vendor claim; REQUIRES XIID VALIDATION)
            out.append(PlanAsset(a.asset_id, a.algo_id, a.usage, c.get("data_class", "operational"),
                                 FABRIC_CATEGORY.get(str(c.get("service")), "web_cloud_os"), capture, 0.0, 3.0,
                                 overlay, [], c.get("route_id")))
        elif a.source == "declared" and "native_effort_weeks" in c:
            capture = 1.0 if c.get("internet_facing") else (0.5 if c.get("at_rest") else 0.3)
            out.append(PlanAsset(a.asset_id, a.algo_id, a.usage, c.get("data_class", "operational"),
                                 c.get("category", "custom_application"), capture, float(c.get("trust_years", 0)),
                                 float(c["native_effort_weeks"]), False,
                                 [f"declared:{d}" for d in c.get("depends_on", [])]))
        elif a.source == "code":
            out.append(PlanAsset(a.asset_id, a.algo_id, a.usage, "identity" if "cortex" in a.location else "operational",
                                 "custom_application", 0.3, 5.0 if a.usage == "authenticity" else 0.0, 1.0, False, []))
    return out


def status_of(a: CryptoAsset, profile: Mapping[str, Any]) -> str:
    algo = get(a.algo_id)
    if algo.algo_id == "xiid-sealedtunnel":
        return "claimed_pq_unverified"
    if algo.quantum == "classically_broken":
        return "non_security_use" if a.usage == "non-security" else "broken_now"
    if approved(algo, profile):
        return "compliant"
    if algo.quantum == "broken_by_shor":
        return "quantum_vulnerable"
    if algo.quantum == "pq":
        return "pq_parameters_unverified"
    return "below_profile" if algo.quantum == "grover_reduced" else "unknown"


def cbom(assets: Sequence[CryptoAsset], profile_id: str, profile: Mapping[str, Any], version: str) -> Dict[str, Any]:
    """CycloneDX 1.6 CBOM with real primitive classification and per-asset evidence."""
    comps = []
    for a in assets:
        algo = get(a.algo_id)
        props = {"assetType": "algorithm",
                 "algorithmProperties": {"primitive": algo.primitive, "parameterSetIdentifier": a.algo_id,
                                         "classicalSecurityLevel": algo.bits or 0,
                                         "nistQuantumSecurityLevel": algo.nist_category or 0}}
        comps.append({"type": "cryptographic-asset", "bom-ref": a.asset_id, "name": a.algo_id,
                      "cryptoProperties": props,
                      "evidence": {"occurrences": [{"location": a.location}]},
                      "properties": [{"name": "s3m:source", "value": a.source},
                                     {"name": "s3m:confidence", "value": a.confidence},
                                     {"name": "s3m:usage", "value": a.usage},
                                     {"name": "s3m:quantum_status", "value": status_of(a, profile)},
                                     {"name": "s3m:profile", "value": profile_id}]})
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"timestamp": datetime.now(timezone.utc).isoformat(),
                         "component": {"type": "application", "name": "quantumwatch-assessment", "version": version}},
            "components": comps}


def assess(*, routes: Sequence[Mapping[str, Any]], crypto_overlay: Path, code_paths: Sequence[Path],
           declared_inventory: Optional[Path], profile_id: str = "nist-ir8547", capacity_weeks: float = 12.0,
           overlay_residual: float = 0.05, sealed_overlay_available: bool = True) -> Dict[str, Any]:
    cfg = load_profiles()
    profile = cfg["profiles"][profile_id]
    overlay_cfg = yaml.safe_load(crypto_overlay.read_text(encoding="utf-8"))
    fabric = infer_fabric(routes, overlay_cfg.get("data_class", {}))
    declared_range = load_declared(crypto_overlay)
    code = scan_python(code_paths, ROOT)
    declared_cbom = load_declared(declared_inventory) if declared_inventory else []
    everything = fabric + declared_range + code
    statuses = Counter(status_of(a, profile) for a in everything)
    crqc = CRQC(cfg["crqc_cdf"])
    years = cfg["data_classes"]
    pa = to_plan_assets(everything, sealed_overlay_available=sealed_overlay_available)
    kw = dict(crqc=crqc, years=years, capacity_weeks=capacity_weeks, overlay_residual=overlay_residual)
    optimised = plan(pa, profile, **kw)
    base = baseline_plan(pa, profile, **kw)
    return {
        "profile": profile_id,
        "assets": [a.to_dict() | {"status": status_of(a, profile)} for a in everything],
        "status_counts": dict(statuses),
        "broken_now": sorted(a.asset_id for a in everything if status_of(a, profile) == "broken_now"),
        "reconciliation": reconcile(declared_cbom, code) if declared_cbom else {},
        "to_migrate": sum(needs_migration(a, profile) for a in pa),
        "plan": optimised.to_dict(),
        "baseline": base.to_dict(),
        "cbom": cbom(everything, profile_id, profile, "0.1"),
        "assumptions": {"crqc_cdf": cfg["crqc_cdf"], "data_classes": years, "overlay_residual": overlay_residual,
                        "sealed_tunnel_pq": "vendor claim; REQUIRES XIID VALIDATION"},
    }


__all__ = ["assess", "cbom", "load_profiles", "status_of", "to_plan_assets"]

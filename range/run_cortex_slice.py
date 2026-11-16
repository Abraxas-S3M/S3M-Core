#!/usr/bin/env python3
"""Run the Cortex vertical slice against the mock XiiD MCP server.

Military/tactical context:
Range rehearsal of one complete defensive cycle on a synthetic 200-host enterprise:
discovery over MCP -> CyberTwin -> alternative architectures -> signed approvals ->
broker-gated execution -> verification from observed state -> rollback/escalation.
Nothing here touches a real network: the XiiD server is the in-repo mock on loopback.

Usage:
    python -m range.run_cortex_slice --scenario sim-002
    python -m range.run_cortex_slice --scenario sim-005   # silent write failure mid-plan
    python -m range.run_cortex_slice --scenario all --out range/reports
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import socket
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

import httpx
import uvicorn
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from range.mock_xiid_mcp.app import build_mock_server  # noqa: E402
from range.mock_xiid_mcp.state import MockServerState  # noqa: E402
from s3m_core.defense.audit.merkle_log import MerkleAuditLog  # noqa: E402
from src.cortex.approvals.service import ApprovalService  # noqa: E402
from src.cortex.defense_cycle import CycleReport, DefenseCycle, RangeApprovalBoard, option_table  # noqa: E402
from src.cortex.tool_map import XiidToolMap  # noqa: E402
from src.cortex.transport_mcp import MockHttpMCPTransport  # noqa: E402
from src.cortex.xiid_broker import XiidMCPBroker  # noqa: E402

SCENARIO = ROOT / "range" / "mock_xiid_mcp" / "scenarios" / "enterprise_200.yaml"
MISSION = ROOT / "range" / "enterprise" / "mission_enterprise_200.yaml"

SCENARIOS = {
    "sim-002": "Predictive attack-path reduction (happy path)",
    "sim-005": "Failed policy deployment: XiiD acknowledges a write it never applies",
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def mock_xiid(scenario_path: Path = SCENARIO) -> Iterator[Tuple[str, str, MockServerState]]:
    """Start the mock XiiD MCP server on loopback; yields (mcp_url, bearer, state)."""
    bearer = secrets.token_urlsafe(24)
    port = _free_port()
    _, state, app = build_mock_server(scenario_path=scenario_path, bearer_token=bearer, port=port)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/admin/metrics", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("mock XiiD MCP server failed to start")
    try:
        yield f"http://127.0.0.1:{port}/mcp", bearer, state
    finally:
        server.should_exit = True
        thread.join(timeout=5)


async def run_cycle(
    url: str,
    bearer: str,
    *,
    workdir: Path,
    session_id: str = "cortex-slice",
    case_id: str | None = None,
    board_policy=None,
) -> Tuple[CycleReport, XiidMCPBroker]:
    key = secrets.token_bytes(32)
    audit = MerkleAuditLog(str(workdir / f"{session_id}-audit.jsonl"))
    transport = MockHttpMCPTransport(url, bearer)
    broker = XiidMCPBroker(
        transport=transport,
        tool_map=XiidToolMap.from_yaml(),
        audit_log=audit,
        session_id=session_id,
        envelope_signing_key=key,
        require_bound_envelopes=True,
    )
    service = ApprovalService()
    board = RangeApprovalBoard(service, policy=board_policy)
    mission = yaml.safe_load(MISSION.read_text(encoding="utf-8"))
    cycle = DefenseCycle(
        broker=broker,
        audit_log=audit,
        mission=mission,
        approval_service=service,
        approval_board=board,
        envelope_signing_key=key,
        session_id=session_id,
    )
    try:
        return await cycle.run(case_id), broker
    finally:
        await transport.close()


def render_markdown(report: Dict[str, Any], title: str) -> str:
    v = report["verification"]
    lines = [
        f"# Cortex vertical slice - {title}",
        "",
        f"Case `{report['case_id']}` - outcome **{report['outcome'].upper()}** - "
        f"{report['audit'].get('duration_seconds')} s",
        "",
        "## What is real and what is simulated",
        "",
        *[f"- **{k}**: {val}" for k, val in report["labels"].items()],
        "",
        "## Discovery (XiiD MCP reads via broker)",
        "",
        f"- Manifest digest pinned: `{report['discovery']['manifest_digest'][:16]}...`",
        f"- Routes {report['discovery']['routes']}, findings {report['discovery']['findings']}, "
        f"STLinks {report['discovery']['stlinks']}",
        f"- Twin: {report['twin']['nodes']} nodes, {report['twin']['routes']} route edges, "
        f"{report['twin']['identity_edges']} identity edges; baseline system risk "
        f"{report['twin']['system_risk']:.3f}",
        "",
        "## Top modelled attack paths (baseline)",
        "",
        "| p | path |",
        "|---|---|",
        *[f"| {p['probability']:.3f} | {' -> '.join(p['nodes'])} |" for p in report["analysis"]["top_attack_paths"][:6]],
        "",
        "## Unnecessary reachability (no observed use, no dependent required flow)",
        "",
        *[f"- `{r['route_id']}`: {r['source']} -> {r['target']} ({r['service']})"
          for r in report["analysis"]["unnecessary_routes"]],
        "",
        "## Alternative architectures (simulated on the twin)",
        "",
        "| option | policy | risk | changes | irreversible | disrupted sessions (30d) | flows ok | rec |",
        "|---|---|---|---|---|---|---|---|",
        *[
            f"| {r['option']} | {r['label']} | {r['risk']} | {r['changes']} | {r['irreversible']} | "
            f"{r['disrupted_sessions_30d']} | {r['flows_ok']} | {'**yes**' if r['recommended'] else ''} |"
            for r in option_table(report["options"])
        ],
        "",
        "Protected-asset exposure (max path probability from any foothold):",
        "",
        "| asset | baseline | predicted (recommended) | observed after cycle |",
        "|---|---|---|---|",
    ]
    rec = next((o for o in report["options"] if o["recommended"]), None)
    for asset, before in report["analysis"]["asset_exposure"].items():
        pred = rec["asset_exposure_after"].get(asset) if rec else None
        obs = v["observed_asset_exposure"].get(asset)
        lines.append(f"| {asset} | {before:.3f} | {pred:.3f} | {obs:.3f} |")
    lines += [
        "",
        "## Changes: authorization, execution, verification",
        "",
        "| change | XiiD action | class | approvals | reversible | state |",
        "|---|---|---|---|---|---|",
    ]
    for ch in report["changes"]:
        a = ch["authorization"]
        lines.append(
            f"| {ch['change_id']} | `{ch['xiid_action']}` | {a.get('change_class')} | "
            f"{len(a.get('votes', []))}/{a.get('required_approvals')} | {ch['reversible']} | **{ch['state']}** |"
        )
    lines += [
        "",
        "## Verification from observed XiiD state",
        "",
        f"- Predicted system risk {v['predicted_system_risk']:.3f}; observed {v['observed_system_risk']:.3f}; "
        f"matches prediction: **{v['matches_prediction']}**",
        f"- Required flows broken after cycle: {v['observed_broken_flows'] or 'none'}",
    ]
    if v.get("failure"):
        lines.append(f"- Failure detected: `{v['failure']['change_id']}` ({v['failure']['reason']})")
    if report.get("rollback"):
        rb = report["rollback"]
        lines += [
            f"- Rollback performed: {rb['performed']}, restored to approved state: **{rb['restored']}**",
            *[f"  - {s['change_id']}: {s['status']}" for s in rb["steps"]],
            f"- Risk after rollback {rb['system_risk_after_rollback']:.3f}; broken flows "
            f"{rb['broken_flows_after_rollback'] or 'none'}",
        ]
    if report.get("escalations"):
        lines += ["", "## Escalations", "", *[f"- {json.dumps(e)}" for e in report["escalations"]]]
    lines += [
        "",
        "## Evidence",
        "",
        f"- Merkle audit chain intact: **{report['audit']['merkle_chain_intact']}**",
        f"- Stages: {', '.join(s['stage'] + ':' + s['status'] for s in report['stages'])}",
        "",
    ]
    return "\n".join(lines)


def run_scenario(name: str, out_dir: Path) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    with mock_xiid() as (url, bearer, state), tempfile.TemporaryDirectory() as tmp:
        if name == "sim-005":
            state.drop_next_write = True
            state.drop_write_skip = 1  # first write applies, second is acknowledged but dropped
        report, _ = asyncio.run(run_cycle(url, bearer, workdir=Path(tmp), case_id=f"{name}-{int(time.time())}"))
        data = report.to_dict()
        data["scenario"] = {"id": name, "title": SCENARIOS[name]}
        data["mock_metrics"] = {"write_calls": state.metrics.write_calls, "tool_calls": dict(state.metrics.tool_calls)}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out_dir / f"{name}_{stamp}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    (out_dir / f"{name}_{stamp}.md").write_text(render_markdown(data, f"{name.upper()} {SCENARIOS[name]}"), encoding="utf-8")
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", default="sim-002", choices=[*SCENARIOS, "all"])
    ap.add_argument("--out", type=Path, default=ROOT / "range" / "reports")
    args = ap.parse_args(argv)
    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    rc = 0
    for name in names:
        d = run_scenario(name, args.out)
        expected = {"sim-002": "verified", "sim-005": "rolled_back"}[name]
        ok = d["outcome"] == expected and not d["verification"]["observed_broken_flows"]
        final_risk = (d.get("rollback") or {}).get("system_risk_after_rollback", d["verification"]["observed_system_risk"])
        print(f"{name}: outcome={d['outcome']} expected={expected} "
              f"risk baseline {d['twin']['system_risk']:.3f} -> final {final_risk:.3f} "
              f"chain_intact={d['audit']['merkle_chain_intact']} {'PASS' if ok else 'FAIL'}")
        rc |= 0 if ok else 1
    print(f"reports written to {args.out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

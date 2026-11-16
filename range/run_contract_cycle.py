#!/usr/bin/env python3
"""Run the Cortex defense cycle over the S3M control-plane MCP contract v0.1.

Military/tactical context:
Same cycle as ``run_cortex_slice`` but against Abraxas's own contract: a DPoP-bound
client in the ``sbx-change-limited`` sandbox, an independent Approval Authority, and the
manifest-driven reference control plane. ``route.restore`` (proposed to XiiD) makes route
expiry reversible, so SIM-005 can undo an expiry as well as a narrowing.

    python -m range.run_contract_cycle --scenario all
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator

import httpx
import uvicorn
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from range.contract_server.app import ContractServerState, build_contract_server, new_trust  # noqa: E402
from s3m_core.defense.audit.merkle_log import MerkleAuditLog  # noqa: E402
from src.cortex.approvals.service import ApprovalService  # noqa: E402
from src.cortex.defense_cycle import CycleReport, DefenseCycle, RangeApprovalBoard  # noqa: E402
from src.cortex.mcp_contract.authz import load_sandboxes  # noqa: E402
from src.cortex.mcp_contract.client import ContractMCPTransport  # noqa: E402
from src.cortex.mcp_contract.manifest import load_contract  # noqa: E402
from src.cortex.mcp_contract.tokens import ApprovalAuthority, ClientIdentity, SandboxAuthorizationServer  # noqa: E402
from src.cortex.tool_map import XiidToolMap  # noqa: E402
from src.cortex.xiid_broker import XiidMCPBroker  # noqa: E402

MISSION = ROOT / "range" / "enterprise" / "mission_enterprise_200.yaml"
TOOL_MAP = ROOT / "configs" / "xiid_tool_map.contract_v0_1.yaml"


@dataclass
class ContractRange:
    url: str
    state: ContractServerState
    authorization_server: SandboxAuthorizationServer
    approval_authority: ApprovalAuthority
    manifest_public_key: Any
    sandboxes: Dict[str, Any]

    def client(self, client_id: str = "cortex-range-01", sandbox: str = "sbx-change-limited",
               scopes: list[str] | None = None) -> ContractMCPTransport:
        identity = ClientIdentity(client_id)
        profile = self.sandboxes[sandbox]
        self.authorization_server.register_client(
            identity.private_key.public_key(), client_id,
            scopes=scopes or profile.scopes, sandboxes=[sandbox],
        )
        return ContractMCPTransport(
            url=self.url, resource=self.url, identity=identity, authorization_server=self.authorization_server,
            sandbox=profile, contract=load_contract(), contract_authority_key=self.manifest_public_key,
            scopes=scopes,
        )

    def admin(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return httpx.post(self.url.removesuffix("/mcp") + "/admin/fault", json=body, timeout=5).json()


@contextmanager
def contract_range() -> Iterator[ContractRange]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    url = f"http://127.0.0.1:{port}/mcp"
    sandboxes = load_sandboxes()
    as_server = SandboxAuthorizationServer(sandbox_scopes={k: v.scopes for k, v in sandboxes.items()})
    authority = ApprovalAuthority()
    trust = new_trust(url, as_server.issuer, as_server.public_key, authority.issuer, authority.public_key)
    _, state, app = build_contract_server(trust=trust, sandboxes=sandboxes)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            httpx.get(url.removesuffix("/mcp") + "/admin/metrics", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)
    try:
        yield ContractRange(url, state, as_server, authority, trust.manifest_key.public_key(), sandboxes)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


async def run_contract_cycle(rng: ContractRange, *, workdir: Path, case_id: str, board_policy=None,
                             sandbox: str = "sbx-change-limited",
                             exposure_target: float | None = None, mission_guard=None,
                             clock=None, intents=None) -> tuple[CycleReport, ContractMCPTransport]:
    transport = rng.client(sandbox=sandbox)
    tool_map = XiidToolMap.from_yaml(TOOL_MAP)
    key = secrets.token_bytes(32)
    session_id = "cortex-contract"
    audit = MerkleAuditLog(str(workdir / f"{case_id}-audit.jsonl"))
    broker = XiidMCPBroker(transport=transport, tool_map=tool_map, audit_log=audit, session_id=session_id,
                           envelope_signing_key=key, require_bound_envelopes=True)

    def approval_sink(action: str, arguments, approval_ids):
        tool = tool_map.resolve(action).tool
        token = rng.approval_authority.issue(client_id=transport.identity.client_id, resource=rng.url,
                                             tool=tool, arguments=arguments, approval_ids=approval_ids)
        transport.attach_approval(tool, arguments, token)

    service = ApprovalService()
    cycle = DefenseCycle(
        broker=broker, audit_log=audit, mission=yaml.safe_load(MISSION.read_text(encoding="utf-8")),
        approval_service=service, approval_board=RangeApprovalBoard(service, policy=board_policy),
        envelope_signing_key=key, session_id=session_id,
        xiid_label="S3M contract v0.1 reference control plane (range), DPoP client in " + sandbox,
        expire_inverse="restore_route", approval_sink=approval_sink,
        exposure_target=exposure_target, mission_guard=mission_guard, clock=clock, intents=intents,
    )
    try:
        return await cycle.run(case_id), transport
    finally:
        await transport.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cortex cycle over contract v0.1")
    ap.add_argument("--scenario", default="all", choices=["c-sim-002", "c-sim-005", "all"])
    ap.add_argument("--out", type=Path, default=ROOT / "range" / "reports")
    args = ap.parse_args(argv)
    names = ["c-sim-002", "c-sim-005"] if args.scenario == "all" else [args.scenario]
    args.out.mkdir(parents=True, exist_ok=True)
    rc = 0
    for name in names:
        with contract_range() as rng, tempfile.TemporaryDirectory() as tmp:
            if name == "c-sim-005":
                rng.state.drop_next_write, rng.state.drop_write_skip = True, 1
            report, transport = asyncio.run(run_contract_cycle(rng, workdir=Path(tmp), case_id=name))
            data = report.to_dict()
            data["contract"] = {"server_writes_applied": rng.state.writes_applied, "denials": rng.state.denials,
                                "receipts": [p.receipt_digest for p in transport.provenance if p.receipt_digest],
                                "audit_head": rng.state.audit[-1] if rng.state.audit else None}
        expected = {"c-sim-002": "verified", "c-sim-005": "rolled_back"}[name]
        ok = data["outcome"] == expected and not data["verification"]["observed_broken_flows"]
        final = (data.get("rollback") or {}).get("system_risk_after_rollback", data["verification"]["observed_system_risk"])
        print(f"{name}: outcome={data['outcome']} expected={expected} risk {data['twin']['system_risk']:.3f} -> "
              f"{final:.3f} receipts={len(data['contract']['receipts'])} {'PASS' if ok else 'FAIL'}")
        (args.out / f"{name}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

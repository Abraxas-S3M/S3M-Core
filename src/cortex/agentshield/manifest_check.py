"""AgentShield MCP server checks: contract drift and instruction-like text in tool metadata.

Military/tactical context:
Tool descriptions reach an agent's context window. A server that changes a description
after approval ("rug pull") or embeds instructions in it is attacking the agent, not the
network. Cortex never executes descriptions; this check makes such changes visible and
blocks the server until a human re-approves its manifest.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence

from src.cortex.mcp_contract.manifest import ContractManifest

INJECTION_PATTERNS = {
    "override_instruction": re.compile(r"\b(ignore|disregard|forget)\b.{0,30}\b(instruction|prior|previous|above|rules)",
                                       re.I),
    "imperative_to_agent": re.compile(r"\byou (must|should|need to)\b.{0,40}\b(call|invoke|run|use|send|expire|disable)",
                                      re.I),
    "prompt_reference": re.compile(r"\b(system prompt|developer message|assistant:)", re.I),
    "mass_action": re.compile(r"\b(every|all)\s+(route|stlink|host|session|tool)s?\b", re.I),
    "external_url": re.compile(r"https?://", re.I),
    "hidden_unicode": re.compile("[​-‏‪-‮⁦-⁩﻿]"),
    "encoded_blob": re.compile(r"[A-Za-z0-9+/]{48,}={0,2}"),
    "markup": re.compile(r"<\s*(script|img|iframe|a\s)", re.I),
}


def injection_markers(text: str) -> List[str]:
    return sorted(k for k, rx in INJECTION_PATTERNS.items() if rx.search(text or ""))


def check_server(contract: ContractManifest, advertised: Sequence[Mapping[str, Any]], *,
                 server_id: str = "xiid-control-plane") -> Dict[str, Any]:
    """Compare a live tools/list with the pinned contract and scan its metadata.

    Verdicts: ``pinned`` (identical to contract), ``drift`` (differs, nothing instruction-like),
    ``suspicious`` (instruction-like text in any description). Anything but ``pinned`` blocks
    use of the server until its manifest is re-approved.
    """
    drift = contract.advertised_matches(advertised)
    markers = {}
    for tool in advertised:
        found = injection_markers(str(tool.get("description") or ""))
        if found:
            markers[str(tool.get("name"))] = found
    contract_markers = {n: injection_markers(contract.tool(n).raw["description"]) for n in contract.tools}
    contract_markers = {n: m for n, m in contract_markers.items() if m}
    new_markers = {n: m for n, m in markers.items() if m != contract_markers.get(n)}
    verdict = "suspicious" if new_markers else ("drift" if drift else "pinned")
    return {"server_id": server_id, "verdict": verdict, "drift": drift, "injection_markers": new_markers,
            "tools_advertised": len(list(advertised)), "blocked": verdict != "pinned"}


__all__ = ["INJECTION_PATTERNS", "check_server", "injection_markers"]

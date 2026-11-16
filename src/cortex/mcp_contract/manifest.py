"""Load, validate, digest and sign the Cortex control-plane MCP contract.

Military/tactical context:
Both ends of the MCP link derive their behaviour from one signed manifest. The client
pins its SHA-256 and the contract authority's Ed25519 signature; any drift between the
manifest and what the server advertises (a "rug pull") is detected before a tool runs.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas" / "v0.1"
CLASS_SCOPE = {"A": "cortex.read", "B": "cortex.simulate", "C": "cortex.write.c", "D": "cortex.write.d"}
WIRE_ONLY_ARGS = ("approval", "idempotency_key")


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def args_sha256(arguments: Mapping[str, Any] | None) -> str:
    """Digest of tool arguments as approved: wire-only fields are excluded."""
    body = {k: v for k, v in dict(arguments or {}).items() if k not in WIRE_ONLY_ARGS}
    return hashlib.sha256(canonical_json(body)).hexdigest()


@dataclass(frozen=True)
class ToolSpec:
    raw: Mapping[str, Any]

    @property
    def name(self) -> str:
        return str(self.raw["name"])

    @property
    def tool_class(self) -> str:
        return str(self.raw["class"])

    @property
    def kind(self) -> str:
        return str(self.raw["kind"])

    @property
    def scope(self) -> str:
        return str(self.raw["scope"])

    @property
    def is_write(self) -> bool:
        return self.kind == "write"

    @property
    def min_approvals(self) -> int:
        return int(self.raw.get("write", {}).get("min_approvals", 0))

    @property
    def inverse(self) -> Optional[str]:
        return self.raw.get("write", {}).get("inverse")

    @property
    def resource_args(self) -> Mapping[str, str]:
        return self.raw.get("resource_args", {})

    @property
    def input_schema(self) -> Dict[str, Any]:
        return dict(self.raw["inputSchema"])

    @property
    def output_schema(self) -> Dict[str, Any]:
        return dict(self.raw["outputSchema"])


class ContractManifest:
    """In-memory contract with resolving validators."""

    def __init__(self, manifest: Mapping[str, Any], schemas: Iterable[Mapping[str, Any]]) -> None:
        self.raw = dict(manifest)
        self.registry = Registry().with_resources(
            [(str(s["$id"]), Resource.from_contents(dict(s))) for s in schemas]
        )
        self.tools: Dict[str, ToolSpec] = {str(t["name"]): ToolSpec(t) for t in self.raw["tools"]}
        self._in: Dict[str, Draft202012Validator] = {}
        self._out: Dict[str, Draft202012Validator] = {}
        for name, spec in self.tools.items():
            self._in[name] = Draft202012Validator(spec.input_schema, registry=self.registry, format_checker=FormatChecker())
            self._out[name] = Draft202012Validator(spec.output_schema, registry=self.registry, format_checker=FormatChecker())
        telemetry = next(s for s in schemas if str(s["$id"]).endswith(":telemetry"))
        self.telemetry_validator = Draft202012Validator(telemetry, registry=self.registry, format_checker=FormatChecker())

    @property
    def version(self) -> str:
        return str(self.raw["version"])

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.raw)).hexdigest()

    def tool(self, name: str) -> ToolSpec:
        if name not in self.tools:
            raise KeyError(f"tool not in contract: {name}")
        return self.tools[name]

    @staticmethod
    def _errors(validator: Draft202012Validator, instance: Any) -> List[str]:
        return [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message[:160]}"
            for e in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
        ][:10]

    def input_errors(self, name: str, arguments: Mapping[str, Any]) -> List[str]:
        return self._errors(self._in[name], dict(arguments))

    def output_errors(self, name: str, result: Mapping[str, Any]) -> List[str]:
        return self._errors(self._out[name], dict(result))

    def telemetry_errors(self, event: Mapping[str, Any]) -> List[str]:
        return self._errors(self.telemetry_validator, dict(event))

    def advertised_matches(self, advertised: Iterable[Mapping[str, Any]]) -> List[str]:
        """Compare a server's tools/list with the contract; returns drift descriptions."""
        drift: List[str] = []
        seen = set()
        for tool in advertised:
            name = str(tool.get("name"))
            seen.add(name)
            if name not in self.tools:
                drift.append(f"unexpected tool advertised: {name}")
                continue
            spec = self.tools[name]
            if tool.get("input_schema") != spec.input_schema:
                drift.append(f"{name}: inputSchema differs from contract")
            if tool.get("output_schema") != spec.output_schema:
                drift.append(f"{name}: outputSchema differs from contract")
            if (tool.get("description") or "") != spec.raw["description"]:
                drift.append(f"{name}: description differs from contract")
        for missing in sorted(set(self.tools) - seen):
            drift.append(f"contract tool not advertised: {missing}")
        return drift


@lru_cache(maxsize=1)
def load_contract() -> ContractManifest:
    def read(name: str) -> Dict[str, Any]:
        return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))

    return ContractManifest(read("manifest.json"), [read("common.schema.json"), read("telemetry.schema.json")])


# ---- contract authority signature ----------------------------------------------------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def key_id(public_key: Ed25519PublicKey) -> str:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return "ed25519:" + hashlib.sha256(raw).hexdigest()[:16]


def sign_manifest(contract: ContractManifest, key: Ed25519PrivateKey) -> Dict[str, str]:
    material = f"{contract.raw['contract']}|{contract.version}|{contract.sha256}".encode("ascii")
    return {
        "contract": str(contract.raw["contract"]),
        "version": contract.version,
        "manifest_sha256": contract.sha256,
        "signature_b64": _b64(key.sign(material)),
        "key_id": key_id(key.public_key()),
    }


def verify_manifest_statement(statement: Mapping[str, Any], public_key: Ed25519PublicKey) -> bool:
    try:
        material = f"{statement['contract']}|{statement['version']}|{statement['manifest_sha256']}".encode("ascii")
        public_key.verify(_unb64(str(statement["signature_b64"])), material)
        return statement.get("key_id") == key_id(public_key)
    except Exception:
        return False

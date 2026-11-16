"""QuantumWatch discovery: find cryptography in code, in the fabric, and in declarations.

Military/tactical context:
A crypto inventory that only lists what people remember is wrong in the places that
matter. Three independent sources are reconciled:

1. **Code** (``scan_python``): an AST pass over Python sources that recognises crypto API
   use (``cryptography``, ``hashlib``, ``hmac``, PyJWT algorithms, ``ssl``, liboqs) and
   records file:line evidence. It reads code, it never executes it.
2. **Fabric** (``infer_fabric``): each XiiD route's service implies a protocol and its usual
   key exchange; SealedTunnel routes are recorded as the vendor's claimed profile.
   Confidence is ``inferred``. A live handshake probe is the production follow-up.
3. **Declared** (``load_declared``): the customer's own inventory (e.g. the CBOM inventory).

``reconcile`` reports declared-but-not-found and found-but-not-declared, the gaps an
assessor asks about first.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import yaml

# Trailing attribute / call name -> canonical algorithm id.
NAME_MAP: Dict[str, str] = {
    "Ed25519PrivateKey": "ed25519", "Ed25519PublicKey": "ed25519",
    "X25519PrivateKey": "x25519", "X25519PublicKey": "x25519",
    "SECP256R1": "ecdsa-p256", "SECP384R1": "ecdsa-p384",
    "PKCS1v15": "rsa-2048", "OAEP": "rsa-kex",
    "Fernet": "aes-128-cbc-hmac", "MultiFernet": "aes-128-cbc-hmac",
    "AESGCM": "aes-256-gcm", "ChaCha20Poly1305": "chacha20-poly1305",
    "SHA256": "sha-256", "SHA384": "sha-384", "SHA512": "sha-512", "SHA1": "sha-1", "MD5": "md5",
    "SHA3_256": "sha3-256",
    "sha256": "sha-256", "sha384": "sha-384", "sha512": "sha-512", "sha1": "sha-1", "md5": "md5",
    "sha3_256": "sha3-256",
    "PBKDF2HMAC": "pbkdf2-sha256", "pbkdf2_hmac": "pbkdf2-sha256", "HKDF": "hkdf-sha256", "Scrypt": "scrypt",
    "create_default_context": "tls-default", "SSLContext": "tls-default",
}
STRING_MAP: Dict[str, str] = {
    "HS256": "hmac-sha256", "RS256": "rsa-2048", "PS256": "rsa-2048", "ES256": "ecdsa-p256",
    "ES384": "ecdsa-p384", "EdDSA": "ed25519",
    "Kyber768": "ml-kem-768", "Kyber1024": "ml-kem-1024", "ML-KEM-768": "ml-kem-768", "ML-KEM-1024": "ml-kem-1024",
    "Dilithium3": "ml-dsa-65", "Dilithium5": "ml-dsa-87", "ML-DSA-65": "ml-dsa-65", "ML-DSA-87": "ml-dsa-87",
}
# tls-default: Python's default context negotiates classical ECDHE (X25519/P-256) unless a
# hybrid group is configured, so it is treated as x25519 key agreement.
ALIAS = {"tls-default": "x25519"}


@dataclass
class CryptoAsset:
    asset_id: str
    algo_id: str
    source: str  # code | fabric | declared
    location: str  # file:line, route id, or component name
    usage: str  # confidentiality | authenticity | integrity | key-derivation | unknown
    confidence: str  # observed | inferred | declared
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _usage(algo: str) -> str:
    from src.cortex.quantumwatch.catalog import get

    prim = get(algo).primitive
    return {"signature": "authenticity", "key-agree": "confidentiality", "kem": "confidentiality",
            "ae": "confidentiality", "block-cipher": "confidentiality", "hash": "integrity", "mac": "authenticity",
            "kdf": "key-derivation"}.get(prim, "unknown")


def _rsa_bits(call: ast.Call) -> Optional[str]:
    for kw in call.keywords:
        if kw.arg == "key_size" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
            return f"rsa-{kw.value.value}" if kw.value.value in (2048, 3072, 4096) else "rsa-2048"
    return None


SELF = Path(__file__).resolve().parent  # the catalogue names algorithms; do not report it as use


def scan_python(paths: Iterable[Path], root: Path) -> List[CryptoAsset]:
    found: Dict[tuple, CryptoAsset] = {}
    for path in paths:
        if path.resolve().parent == SELF:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        imports_hashlib = any(isinstance(n, (ast.Import, ast.ImportFrom)) and "hashlib" in ast.dump(n)
                              for n in ast.walk(tree))
        for node in ast.walk(tree):
            algo = None
            if isinstance(node, ast.Call):
                name = _dotted(node.func)
                tail = name.rsplit(".", 1)[-1]
                if name.startswith("oqs.") and tail in ("KeyEncapsulation", "Signature"):
                    algo = "ml-kem" if tail == "KeyEncapsulation" else "ml-dsa"  # parameter set chosen at runtime
                elif tail == "generate_private_key" and "rsa" in name:
                    algo = _rsa_bits(node) or "rsa-2048"
                elif tail == "new" and name.startswith("hashlib") and node.args and isinstance(node.args[0], ast.Constant):
                    algo = NAME_MAP.get(str(node.args[0].value).lower())
                elif tail in NAME_MAP and (tail not in ("sha256", "sha1", "md5", "sha384", "sha512", "sha3_256")
                                           or name.startswith("hashlib") or imports_hashlib):
                    algo = NAME_MAP[tail]
                if algo is None:
                    for arg in list(node.args) + [kw.value for kw in node.keywords]:
                        vals = arg.elts if isinstance(arg, (ast.List, ast.Tuple)) else [arg]
                        for v in vals:
                            if isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value in STRING_MAP:
                                algo = STRING_MAP[v.value]
            elif isinstance(node, ast.Attribute) and node.attr in NAME_MAP and node.attr[0].isupper():
                algo = NAME_MAP[node.attr]
            elif isinstance(node, ast.Name) and node.id in NAME_MAP and node.id[0].isupper() \
                    and isinstance(node.ctx, ast.Load):
                algo = NAME_MAP[node.id]
            if not algo:
                continue
            algo = ALIAS.get(algo, algo)
            line = getattr(node, "lineno", 0)
            non_security = isinstance(node, ast.Call) and any(
                kw.arg == "usedforsecurity" and isinstance(kw.value, ast.Constant) and kw.value.value is False
                for kw in node.keywords)
            key = (rel, algo)
            if key not in found:  # one asset per (file, algorithm); first line is the evidence
                found[key] = CryptoAsset(f"code:{rel}:{algo}", algo, "code", f"{rel}:{line}",
                                         "non-security" if non_security else _usage(algo), "observed",
                                         {"component": rel.split("/")[2] if rel.count("/") >= 2 else rel})
            elif non_security and found[key].usage == "non-security":
                pass
            elif not non_security and found[key].usage == "non-security":
                found[key].usage = _usage(algo)  # any security use in the file wins
    return sorted(found.values(), key=lambda a: a.asset_id)


# service -> (algorithm id for the key exchange / protection, protocol label)
SERVICE_CRYPTO: Dict[str, tuple] = {
    "https": ("x25519", "TLS 1.2/1.3, classical ECDHE"), "https-api": ("x25519", "TLS, classical ECDHE"),
    "ssh": ("x25519", "SSH curve25519 KEX, Ed25519/RSA host keys"),
    "rdp": ("ecdh-p256", "RDP over TLS/CredSSP"), "smb": ("aes-128-gcm", "SMB3 (signing/encryption config-dependent)"),
    "ldap": ("cleartext", "LDAP without StartTLS (signing not enforced)"),
    "kerberos": ("aes-256", "Kerberos AES256-CTS; PKINIT would add RSA/ECDH"),
    "postgres": ("x25519", "PostgreSQL TLS if enabled"), "mssql": ("rsa-kex", "TDS/TLS, legacy RSA key exchange common"),
    "smtp": ("x25519", "SMTP STARTTLS, opportunistic"), "rtsp": ("cleartext", "RTSP, typically unencrypted"),
    "ipp": ("cleartext", "IPP, typically unencrypted"), "any": ("unknown", "mixed"),
}


def infer_fabric(routes: Sequence[Mapping[str, Any]], data_class: Mapping[str, str]) -> List[CryptoAsset]:
    out = []
    for r in routes:
        if r.get("status") == "expired":
            continue
        algo, proto = SERVICE_CRYPTO.get(str(r.get("service")), ("unknown", "unrecognised service"))
        ctx = {"route_id": r["id"], "source": r["source"], "target": r["target"], "service": r.get("service"),
               "protocol": proto, "sealed": bool(r.get("sealed_tunnel")),
               "internet_facing": str(r["source"]).startswith("ext:"),
               "data_class": data_class.get(str(r["target"]), "operational")}
        # Transport protocols protect data in transit: fabric assets are confidentiality uses.
        out.append(CryptoAsset(f"fabric:{r['id']}", algo, "fabric", r["id"], "confidentiality", "inferred", ctx))
        if r.get("sealed_tunnel"):
            out.append(CryptoAsset(f"fabric:{r['id']}:sealedtunnel", "xiid-sealedtunnel", "fabric", r["id"],
                                   "confidentiality", "declared",
                                   dict(ctx, note="vendor-claimed layered PQ encryption; REQUIRES XIID VALIDATION")))
    return out


def load_declared(path: Path) -> List[CryptoAsset]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = []
    for block in raw.get("components", []):
        for a in block.get("algorithms", []):
            algo = {"tls-aes-256-gcm": "aes-256-gcm", "ecdsa-p256": "ecdsa-p256"}.get(str(a["id"]), str(a["id"]))
            algo = {"sha256": "sha-256", "sha512": "sha-512"}.get(algo, algo)
            out.append(CryptoAsset(f"declared:{block['name']}:{algo}", algo, "declared", str(block["name"]),
                                   _usage(algo), "declared", {"purpose": a.get("purpose", "")}))
    for a in raw.get("assets", []):  # richer declarations (range overlay)
        out.append(CryptoAsset(f"declared:{a['id']}", a["algo"], "declared", a["id"], a.get("usage", _usage(a["algo"])),
                               "declared", {k: v for k, v in a.items() if k not in ("id", "algo", "usage")}))
    return out


def reconcile(declared: Sequence[CryptoAsset], code: Sequence[CryptoAsset]) -> Dict[str, List[str]]:
    d = {a.algo_id for a in declared}
    c = {a.algo_id for a in code}
    return {"declared_not_found_in_code": sorted(d - c), "found_in_code_not_declared": sorted(c - d)}


__all__ = ["CryptoAsset", "SERVICE_CRYPTO", "infer_fabric", "load_declared", "reconcile", "scan_python"]

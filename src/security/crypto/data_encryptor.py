"""Encryption utilities for S3M Phase 10 data protection."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path
from typing import List

try:
    from cryptography.fernet import Fernet

    _HAS_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover - explicitly supported fallback path
    Fernet = None  # type: ignore
    _HAS_CRYPTOGRAPHY = False


class DataEncryptor:
    """Encrypt/decrypt files and blobs for tactical edge persistence.

    Notes:
    - Preferred mode uses ``cryptography`` Fernet authenticated encryption.
    - Fallback mode is XOR stream masking derived from SHA-256 and is
      intentionally for air-gapped dev/test continuity only.
    """

    def __init__(self, keys_dir: str = "configs/keys/") -> None:
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, key_id: str) -> Path:
        return self.keys_dir / f"{key_id}.key"

    def generate_key(self, key_id: str = "default") -> str:
        key_bytes = secrets.token_bytes(32)
        self._key_path(key_id).write_text(key_bytes.hex(), encoding="utf-8")
        return key_id

    def load_key(self, key_id: str = "default") -> bytes:
        key_path = self._key_path(key_id)
        if not key_path.exists():
            raise FileNotFoundError(f"encryption key not found: {key_path}")
        key_hex = key_path.read_text(encoding="utf-8").strip()
        if not key_hex:
            raise ValueError(f"encryption key file is empty: {key_path}")
        return bytes.fromhex(key_hex)

    def _derive_fernet_key(self, base_key: bytes) -> bytes:
        # Tactical context: derive a deterministic AEAD key from mission key
        # material while preserving a pure-stdlib fallback if cryptography is absent.
        derived = hashlib.sha256(base_key + b"S3M_PHASE10_FERNET_DERIVE").digest()
        return base64.urlsafe_b64encode(derived)

    def _xor_keystream(self, key: bytes, nonce: bytes, length: int) -> bytes:
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
            stream.extend(block)
            counter += 1
        return bytes(stream[:length])

    def _encrypt_fallback(self, data: bytes, key: bytes) -> bytes:
        nonce = secrets.token_bytes(16)
        stream = self._xor_keystream(hashlib.sha256(key).digest(), nonce, len(data))
        ciphertext = bytes(a ^ b for a, b in zip(data, stream))
        digest = hashlib.sha256(key + nonce + ciphertext).digest()
        return b"S3MXOR1" + nonce + digest + ciphertext

    def _decrypt_fallback(self, data: bytes, key: bytes) -> bytes:
        if not data.startswith(b"S3MXOR1"):
            raise ValueError("invalid fallback ciphertext header")
        payload = data[len(b"S3MXOR1") :]
        if len(payload) < 48:
            raise ValueError("fallback ciphertext is truncated")
        nonce = payload[:16]
        digest = payload[16:48]
        ciphertext = payload[48:]
        expected = hashlib.sha256(key + nonce + ciphertext).digest()
        if digest != expected:
            raise ValueError("fallback ciphertext integrity check failed")
        stream = self._xor_keystream(hashlib.sha256(key).digest(), nonce, len(ciphertext))
        return bytes(a ^ b for a, b in zip(ciphertext, stream))

    def encrypt_data(self, data: bytes, key_id: str = "default") -> bytes:
        key = self.load_key(key_id)
        if _HAS_CRYPTOGRAPHY:
            fernet = Fernet(self._derive_fernet_key(key))
            return fernet.encrypt(data)
        return self._encrypt_fallback(data, key)

    def decrypt_data(self, data: bytes, key_id: str = "default") -> bytes:
        key = self.load_key(key_id)
        if _HAS_CRYPTOGRAPHY:
            fernet = Fernet(self._derive_fernet_key(key))
            return fernet.decrypt(data)
        return self._decrypt_fallback(data, key)

    def encrypt_file(self, filepath: str, key_id: str = "default") -> str:
        path = Path(filepath)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"file not found: {filepath}")
        encrypted = self.encrypt_data(path.read_bytes(), key_id=key_id)
        encrypted_path = Path(f"{filepath}.enc")
        encrypted_path.write_bytes(encrypted)
        return str(encrypted_path)

    def decrypt_file(self, filepath: str, key_id: str = "default") -> str:
        path = Path(filepath)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"file not found: {filepath}")
        decrypted = self.decrypt_data(path.read_bytes(), key_id=key_id)
        if filepath.endswith(".enc"):
            output = filepath[: -len(".enc")]
        else:
            output = f"{filepath}.dec"
        Path(output).write_bytes(decrypted)
        return output

    def verify_file_integrity(self, filepath: str) -> str:
        path = Path(filepath)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"file not found: {filepath}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def list_keys(self) -> List[str]:
        key_ids: List[str] = []
        for key_file in sorted(self.keys_dir.glob("*.key")):
            key_ids.append(key_file.stem)
        return key_ids

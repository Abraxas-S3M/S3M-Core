"""Security manager for encrypted tactical communications."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List

from services.comms.models import Message
from src.security.crypto.data_encryptor import DataEncryptor


class CommsSecurityManager:
    """Enforce encryption, classification policy, and safe audit sanitization."""

    def __init__(self) -> None:
        self.encryptor = DataEncryptor(keys_dir="configs/keys/comms")
        self._keys: Dict[str, Dict[str, Any]] = {}
        self._default_key = "comms_default"
        try:
            self.encryptor.load_key(self._default_key)
        except Exception:
            self.encryptor.generate_key(self._default_key)

    def encrypt_message(self, message: Message, protocol: str = "aes256") -> Message:
        if protocol == "none":
            message.encryption_protocol = "none"
            return message
        plaintext = message.body
        ciphertext = self.encryptor.encrypt_data(plaintext.encode("utf-8"), key_id=self._default_key)
        message.body = ciphertext.hex()
        message.encryption_protocol = protocol
        message.metadata["encrypted"] = True
        message.metadata["_plaintext_body"] = plaintext
        return message

    def decrypt_message(self, message: Message) -> Message:
        if message.encryption_protocol in {"none", ""}:
            return message
        raw = bytes.fromhex(message.body)
        plaintext = self.encryptor.decrypt_data(raw, key_id=self._default_key)
        message.body = plaintext.decode("utf-8", errors="replace")
        message.metadata["decrypted"] = True
        return message

    def validate_classification(self, message: Message) -> bool:
        classification = str(message.classification or "").upper()
        disallowed = ["TOP SECRET", "SCI", "SPECIAL ACCESS"]
        if any(token in classification for token in disallowed):
            return False
        return bool(classification.strip())

    def sanitize_for_logging(self, message: Message) -> Dict[str, Any]:
        return message.to_log_safe()

    def key_exchange(self, node_id: str) -> Dict[str, Any]:
        node_key = f"node_{node_id}"
        self.encryptor.generate_key(node_key)
        record = {
            "node_id": node_id,
            "key_id": node_key,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        self._keys[node_id] = record
        return deepcopy(record)

    def get_key_registry(self) -> List[Dict[str, Any]]:
        return [deepcopy(entry) for entry in self._keys.values()]

    def rotate_keys(self) -> None:
        for node_id in list(self._keys.keys()):
            self.key_exchange(node_id)


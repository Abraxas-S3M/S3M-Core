"""BackBlaze B2 S3-compatible connector for sovereign model storage.

Military/tactical context:
This connector enforces integrity checks during movement of mission-critical
model artifacts, ensuring the FP16 source-of-truth and Q4 serving derivatives
remain coherent across contested or degraded infrastructure.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except Exception:  # pragma: no cover - import guard for minimal environments
    boto3 = None

    class BotoCoreError(Exception):
        """Fallback boto core error when botocore is unavailable."""

    class ClientError(Exception):
        """Fallback boto client error when botocore is unavailable."""

        def __init__(self, error_response: dict[str, Any] | None = None, operation_name: str | None = None) -> None:
            self.response = error_response or {}
            self.operation_name = str(operation_name or "")
            super().__init__(f"{self.operation_name}: {self.response}")


LOGGER = logging.getLogger("s3m.storage.b2")


class B2ConnectorError(RuntimeError):
    """Raised when B2 storage operations fail after controlled retries."""


class B2ObjectNotFoundError(B2ConnectorError):
    """Raised when a requested B2 object key does not exist."""


class B2ChecksumMismatchError(B2ConnectorError):
    """Raised when uploaded object checksums fail verification."""


class B2Connector:
    """B2 S3 connector with retries, checksum verification, and sync helpers."""

    def __init__(
        self,
        *,
        key_id: str | None = None,
        app_key: str | None = None,
        bucket_name: str | None = None,
        endpoint: str | None = None,
        region_name: str = "us-east-1",
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        self.key_id = self._required_value("S3M_B2_KEY_ID", key_id)
        self.app_key = self._required_value("S3M_B2_APP_KEY", app_key)
        self.bucket_name = str(bucket_name or os.getenv("S3M_B2_BUCKET_NAME", "s3m-vault")).strip() or "s3m-vault"
        self.endpoint = self._required_value("S3M_B2_ENDPOINT", endpoint)
        self.region_name = str(region_name or "us-east-1").strip() or "us-east-1"
        self.max_retries = max(1, int(max_retries))

        if client is not None:
            self._client = client
        else:
            if boto3 is None:
                raise ImportError("boto3 must be installed to use B2Connector")
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.key_id,
                aws_secret_access_key=self.app_key,
                region_name=self.region_name,
            )

    @classmethod
    def from_env(cls) -> "B2Connector":
        """Build connector from standard S3M BackBlaze environment variables."""
        return cls()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "B2Connector":
        """Build connector from loaded YAML config, resolving ${ENV_NAME} tokens."""
        backblaze = config.get("backblaze", {}) if isinstance(config, dict) else {}
        if not isinstance(backblaze, dict):
            raise ValueError("backblaze config section must be a mapping")

        credentials = backblaze.get("credentials", {})
        if not isinstance(credentials, dict):
            credentials = {}

        key_id = cls._resolve_config_value(backblaze.get("key_id")) or cls._resolve_config_value(
            os.getenv(str(credentials.get("key_id_env", "S3M_B2_KEY_ID")))
        )
        app_key = cls._resolve_config_value(backblaze.get("app_key")) or cls._resolve_config_value(
            os.getenv(str(credentials.get("app_key_env", "S3M_B2_APP_KEY")))
        )

        return cls(
            key_id=key_id,
            app_key=app_key,
            bucket_name=cls._resolve_config_value(backblaze.get("bucket_name")) or "s3m-vault",
            endpoint=cls._resolve_config_value(backblaze.get("endpoint")),
            region_name=cls._resolve_config_value(backblaze.get("region_name"))
            or cls._resolve_config_value(backblaze.get("region"))
            or "us-east-1",
            max_retries=int(backblaze.get("max_retries", 3)),
        )

    def upload_file(self, local_path: str | Path, remote_key: str) -> dict[str, Any]:
        """Upload one local artifact with SHA-256 integrity metadata."""
        source = Path(local_path).resolve()
        key = self._normalize_key(remote_key)
        if not source.exists() or not source.is_file():
            raise ValueError(f"local_path is not a readable file: {source}")

        sha256 = self._sha256_file(source)
        size_bytes = source.stat().st_size
        LOGGER.info("Uploading %s -> s3://%s/%s (%s bytes)", source, self.bucket_name, key, size_bytes)

        self._with_retries(
            action=f"upload file '{source}' to '{key}'",
            operation=lambda: self._client.upload_file(
                Filename=str(source),
                Bucket=self.bucket_name,
                Key=key,
                ExtraArgs={"Metadata": {"sha256": sha256}},
            ),
        )
        head = self._head_object(key)
        self._verify_upload_integrity(head=head, expected_sha256=sha256, expected_size=size_bytes, remote_key=key)
        return {"remote_key": key, "size_bytes": size_bytes, "sha256": sha256}

    def download_file(self, remote_key: str, local_path: str | Path) -> dict[str, Any]:
        """Download one artifact from B2 to a local path."""
        key = self._normalize_key(remote_key)
        destination = Path(local_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected_size = int(self._head_object(key).get("ContentLength", 0))
        LOGGER.info("Downloading s3://%s/%s -> %s", self.bucket_name, key, destination)

        self._with_retries(
            action=f"download key '{key}' to '{destination}'",
            operation=lambda: self._client.download_file(
                Bucket=self.bucket_name,
                Key=key,
                Filename=str(destination),
            ),
        )
        actual_size = destination.stat().st_size
        if expected_size and expected_size != actual_size:
            raise B2ConnectorError(
                f"Downloaded file size mismatch for key '{key}': expected={expected_size}, got={actual_size}"
            )
        return {"remote_key": key, "local_path": str(destination), "size_bytes": actual_size}

    def sync_down(
        self,
        remote_prefix: str,
        local_dir: str | Path,
        exclude_patterns: list[str] | None = None,
    ) -> dict[str, int]:
        """Download every object under a prefix into a local directory."""
        prefix = self._normalize_prefix(remote_prefix)
        destination_root = Path(local_dir).resolve()
        destination_root.mkdir(parents=True, exist_ok=True)
        patterns = [str(pattern) for pattern in (exclude_patterns or []) if str(pattern).strip()]

        downloaded = 0
        skipped = 0
        bytes_transferred = 0

        for key in self.list_keys(prefix):
            relative = key[len(prefix) :] if key.startswith(prefix) else key
            if not relative:
                continue
            if self._is_excluded(relative, patterns):
                skipped += 1
                continue
            target = destination_root / Path(relative)
            result = self.download_file(key, target)
            downloaded += 1
            bytes_transferred += int(result.get("size_bytes", 0))

        return {
            "downloaded": downloaded,
            "uploaded": 0,
            "skipped": skipped,
            "bytes_transferred": bytes_transferred,
        }

    def sync_up(self, local_dir: str | Path, remote_prefix: str) -> dict[str, int]:
        """Upload every file in a local directory tree into a B2 prefix."""
        source_root = Path(local_dir).resolve()
        if not source_root.exists() or not source_root.is_dir():
            raise ValueError(f"local_dir must exist and be a directory: {source_root}")

        prefix = self._normalize_prefix(remote_prefix)
        uploaded = 0
        bytes_transferred = 0
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root).as_posix()
            key = f"{prefix}{relative}"
            result = self.upload_file(path, key)
            uploaded += 1
            bytes_transferred += int(result.get("size_bytes", 0))

        return {
            "downloaded": 0,
            "uploaded": uploaded,
            "skipped": 0,
            "bytes_transferred": bytes_transferred,
        }

    def list_keys(self, prefix: str) -> list[str]:
        """List object keys beneath a prefix."""
        normalized_prefix = self._normalize_prefix(prefix)

        def _list() -> list[str]:
            paginator = self._client.get_paginator("list_objects_v2")
            keys: list[str] = []
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=normalized_prefix):
                for entry in page.get("Contents", []):
                    key = str(entry.get("Key", "")).strip()
                    if key:
                        keys.append(key)
            return keys

        keys = self._with_retries(action=f"list keys for prefix '{normalized_prefix}'", operation=_list)
        return sorted(keys)

    def file_exists(self, remote_key: str) -> bool:
        """Return True when a key exists in B2."""
        key = self._normalize_key(remote_key)
        try:
            self._head_object(key)
            return True
        except B2ObjectNotFoundError:
            return False

    def delete_file(self, remote_key: str) -> bool:
        """Delete one object from B2."""
        key = self._normalize_key(remote_key)
        LOGGER.info("Deleting s3://%s/%s", self.bucket_name, key)
        self._with_retries(
            action=f"delete key '{key}'",
            operation=lambda: self._client.delete_object(Bucket=self.bucket_name, Key=key),
        )
        return True

    def get_file_size(self, remote_key: str) -> int:
        """Return object size in bytes."""
        key = self._normalize_key(remote_key)
        return int(self._head_object(key).get("ContentLength", 0))

    def get_file_sha256(self, remote_key: str) -> str:
        """Return stored SHA-256 metadata for a key, if present."""
        key = self._normalize_key(remote_key)
        metadata = self._head_object(key).get("Metadata", {})
        return str(metadata.get("sha256", "")).strip().lower()

    # ---------------------------------------------------------------------
    # Compatibility helpers used by existing sync/snapshot modules.
    # ---------------------------------------------------------------------
    def upload_json(self, object_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Upload JSON payload to B2 and return metadata for manifests."""
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return self.upload_bytes(object_key=object_key, content=content, content_type="application/json")

    def upload_bytes(
        self,
        object_key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload raw bytes to B2 while validating SHA-256 integrity metadata."""
        key = self._normalize_key(object_key)
        if not isinstance(content, (bytes, bytearray)):
            raise ValueError("content must be bytes")
        payload = bytes(content)
        sha256 = hashlib.sha256(payload).hexdigest()
        size_bytes = len(payload)

        self._with_retries(
            action=f"upload byte payload to '{key}'",
            operation=lambda: self._client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=payload,
                ContentType=content_type,
                Metadata={"sha256": sha256},
            ),
        )
        head = self._head_object(key)
        self._verify_upload_integrity(head=head, expected_sha256=sha256, expected_size=size_bytes, remote_key=key)
        etag = str(head.get("ETag", "")).replace('"', "")
        return {
            "object_key": key,
            "etag": etag,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size_bytes,
            "content_type": content_type,
        }

    def list_objects(self, prefix: str) -> list[dict[str, Any]]:
        """Legacy object listing shape used by sync daemon guards."""
        normalized_prefix = self._normalize_prefix(prefix)

        def _list() -> list[dict[str, Any]]:
            paginator = self._client.get_paginator("list_objects_v2")
            objects: list[dict[str, Any]] = []
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=normalized_prefix):
                for entry in page.get("Contents", []):
                    key = str(entry.get("Key", "")).strip()
                    if not key:
                        continue
                    objects.append({"Key": key, "Size": int(entry.get("Size", 0))})
            return objects

        return self._with_retries(action=f"list objects for prefix '{normalized_prefix}'", operation=_list)

    def sync_prefix_to_local(
        self,
        prefix: str,
        local_dir: str | Path,
        blocked_tokens: list[str] | None = None,
    ) -> dict[str, int]:
        """Legacy wrapper around sync_down with optional blocked-token filtering."""
        lowered_tokens = [str(token).lower() for token in (blocked_tokens or []) if str(token).strip()]
        if lowered_tokens and any(token in str(prefix).lower() for token in lowered_tokens):
            LOGGER.warning("Refusing blocked pull prefix: %s", prefix)
            return {"downloaded": 0, "uploaded": 0, "skipped": 0, "bytes_transferred": 0}

        normalized_prefix = self._normalize_prefix(prefix)
        target_root = Path(local_dir).resolve()
        target_root.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        skipped = 0
        bytes_transferred = 0

        for key in self.list_keys(normalized_prefix):
            lower_key = key.lower()
            if lowered_tokens and any(token in lower_key for token in lowered_tokens):
                skipped += 1
                continue
            relative = key[len(normalized_prefix) :] if key.startswith(normalized_prefix) else key
            if not relative:
                continue
            result = self.download_file(key, target_root / relative)
            downloaded += 1
            bytes_transferred += int(result.get("size_bytes", 0))

        return {
            "downloaded": downloaded,
            "uploaded": 0,
            "skipped": skipped,
            "bytes_transferred": bytes_transferred,
        }

    def sync_local_to_prefix(self, local_dir: str | Path, prefix: str) -> dict[str, int]:
        """Legacy wrapper around sync_up."""
        return self.sync_up(local_dir=local_dir, remote_prefix=prefix)

    # ---------------------------------------------------------------------
    # Internal helpers.
    # ---------------------------------------------------------------------
    def _head_object(self, remote_key: str) -> dict[str, Any]:
        key = self._normalize_key(remote_key)
        try:
            return self._with_retries(
                action=f"head object '{key}'",
                operation=lambda: self._client.head_object(Bucket=self.bucket_name, Key=key),
            )
        except B2ConnectorError as exc:
            root = exc.__cause__
            if isinstance(root, ClientError):
                code = str(root.response.get("Error", {}).get("Code", "")).strip()
                if code in {"404", "NoSuchKey", "NotFound"}:
                    raise B2ObjectNotFoundError(f"B2 object not found: '{key}'") from exc
            raise

    def _verify_upload_integrity(
        self,
        *,
        head: dict[str, Any],
        expected_sha256: str,
        expected_size: int,
        remote_key: str,
    ) -> None:
        metadata = head.get("Metadata", {}) if isinstance(head, dict) else {}
        remote_sha256 = str(metadata.get("sha256", "")).strip().lower()
        remote_size = int(head.get("ContentLength", 0))
        if remote_sha256 != expected_sha256.lower():
            raise B2ChecksumMismatchError(
                f"SHA-256 mismatch after upload for '{remote_key}': "
                f"expected={expected_sha256}, remote={remote_sha256 or 'missing'}"
            )
        if remote_size != expected_size:
            raise B2ChecksumMismatchError(
                f"Size mismatch after upload for '{remote_key}': expected={expected_size}, remote={remote_size}"
            )

    def _with_retries(self, *, action: str, operation: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return operation()
            except Exception as exc:  # noqa: BLE001
                if not self._should_retry(exc) or attempt >= self.max_retries:
                    raise B2ConnectorError(f"Failed to {action}") from exc
                backoff_seconds = 2 ** (attempt - 1)
                LOGGER.warning(
                    "Retrying B2 operation after failure (attempt %s/%s, backoff=%ss): %s",
                    attempt,
                    self.max_retries,
                    backoff_seconds,
                    action,
                )
                last_error = exc
                time.sleep(backoff_seconds)
        raise B2ConnectorError(f"Failed to {action}") from last_error

    @staticmethod
    def _should_retry(error: Exception) -> bool:
        if isinstance(error, (BotoCoreError, OSError, TimeoutError)):
            return True
        if isinstance(error, ClientError):
            error_code = str(error.response.get("Error", {}).get("Code", "")).strip()
            if error_code in {"404", "NoSuchKey", "NotFound", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
                return False
            return True
        return False

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _is_excluded(relative_path: str, patterns: list[str]) -> bool:
        if not patterns:
            return False
        normalized = str(relative_path).replace("\\", "/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)

    @classmethod
    def _normalize_key(cls, remote_key: str) -> str:
        key = str(remote_key or "").strip().lstrip("/")
        if not key:
            raise ValueError("remote key must be non-empty")
        if ".." in Path(key).parts:
            raise ValueError("remote key must not contain path traversal")
        return key

    @classmethod
    def _normalize_prefix(cls, prefix: str) -> str:
        cleaned = cls._normalize_key(prefix)
        return cleaned if cleaned.endswith("/") else f"{cleaned}/"

    @staticmethod
    def _required_value(env_name: str, provided: str | None) -> str:
        value = str(provided if provided is not None else os.getenv(env_name, "")).strip()
        if not value:
            raise ValueError(f"Missing required BackBlaze credential/config: {env_name}")
        return value

    @staticmethod
    def _resolve_config_value(value: Any) -> str:
        text = str(value or "").strip()
        if text.startswith("${") and text.endswith("}") and len(text) > 3:
            return str(os.getenv(text[2:-1], "")).strip()
        return text

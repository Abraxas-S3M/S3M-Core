"""
BackBlaze B2 S3-compatible connector for sovereign vault operations.

Tactical context:
    Weight artifacts, adapters, and evaluation payloads are strategic
    resources. This connector enforces resilient transfer procedures so
    deployed teams can rehydrate model stacks from the vault during
    contested, disconnected, or degraded operations.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Callable, TypeVar

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("s3m.storage.b2")

T = TypeVar("T")


class B2ConnectorError(RuntimeError):
    """Base exception for storage connector failures."""


class B2ConfigurationError(B2ConnectorError):
    """Raised when required BackBlaze connector configuration is missing."""


class B2OperationError(B2ConnectorError):
    """Raised when an S3-compatible operation cannot be completed safely."""


class B2ChecksumError(B2OperationError):
    """Raised when uploaded object checksum does not match local source data."""


class B2Connector:
    """Unified B2 storage interface for mission artifact transport."""

    def __init__(
        self,
        *,
        key_id: str | None = None,
        app_key: str | None = None,
        bucket_name: str | None = None,
        endpoint: str | None = None,
        region_name: str = "us-west-004",
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
    ) -> None:
        """
        Initialize B2 S3-compatible client from environment or explicit values.

        Tactical context:
            Strong defaults and explicit validation reduce misconfiguration risk
            before high-value model artifacts begin moving through the vault.
        """
        self.key_id = self._required_config(key_id, "S3M_B2_KEY_ID")
        self.app_key = self._required_config(app_key, "S3M_B2_APP_KEY")
        self.endpoint = self._required_config(endpoint, "S3M_B2_ENDPOINT")
        self.bucket_name = (bucket_name or os.getenv("S3M_B2_BUCKET_NAME", "s3m-vault")).strip()
        self.region_name = region_name

        if not self.bucket_name:
            raise B2ConfigurationError("S3M_B2_BUCKET_NAME resolved to an empty value")
        if max_retries <= 0:
            raise ValueError("max_retries must be >= 1")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds must be >= 0")

        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.key_id,
            aws_secret_access_key=self.app_key,
            region_name=self.region_name,
        )

    @classmethod
    def from_env(cls) -> "B2Connector":
        """Construct connector using S3M_B2_* environment variables.

        Tactical context:
            Standardized environment bootstrap keeps vault transfer tooling
            interoperable across Hetzner workers and operator laptops.
        """
        return cls()

    @staticmethod
    def _required_config(value: str | None, env_name: str) -> str:
        resolved = (value or os.getenv(env_name, "")).strip()
        if not resolved:
            raise B2ConfigurationError(f"Missing required BackBlaze configuration: {env_name}")
        return resolved

    @staticmethod
    def _normalize_key(remote_key: str) -> str:
        if not isinstance(remote_key, str):
            raise ValueError("remote_key must be a string")
        key = remote_key.strip().lstrip("/")
        if not key:
            raise ValueError("remote_key must be a non-empty path-like string")
        return key

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        if not isinstance(prefix, str):
            raise ValueError("prefix must be a string")
        normalized = prefix.strip().lstrip("/")
        if not normalized:
            return ""
        if not normalized.endswith("/"):
            normalized = f"{normalized}/"
        return normalized

    @staticmethod
    def _sha256_file(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _with_retries(self, action: str, operation: Callable[[], T]) -> T:
        last_exception: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return operation()
            except Exception as exc:  # nosec B110 - controlled retry wrapper with re-raise
                last_exception = exc
                if attempt >= self.max_retries:
                    break
                delay = self.retry_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "B2 %s failed on attempt %d/%d: %s; retrying in %.2fs",
                    action,
                    attempt,
                    self.max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)

        raise B2OperationError(
            f"B2 {action} failed after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    @staticmethod
    def _safe_local_target(local_dir: Path, relative_path: str) -> Path:
        if not isinstance(relative_path, str):
            raise ValueError("relative_path must be a string")

        candidate = (local_dir / relative_path.lstrip("/")).resolve()
        base_dir = local_dir.resolve()
        if candidate != base_dir and base_dir not in candidate.parents:
            raise ValueError(f"unsafe path traversal detected for key fragment: {relative_path}")
        return candidate

    def upload_file(self, local_path: str | Path, remote_key: str) -> None:
        """
        Upload one local artifact to the B2 vault and verify SHA-256 integrity.

        Tactical context:
            Checksum verification prevents silent corruption of mission-critical
            model payloads before they are staged for downstream pull operations.
        """
        source = Path(local_path)
        if not source.exists() or not source.is_file():
            raise ValueError(f"local_path must point to an existing file: {source}")

        key = self._normalize_key(remote_key)
        checksum = self._sha256_file(source)

        def _operation() -> None:
            self._client.upload_file(
                str(source),
                self.bucket_name,
                key,
                ExtraArgs={"Metadata": {"sha256": checksum}},
            )
            metadata = self._client.head_object(Bucket=self.bucket_name, Key=key).get("Metadata", {})
            remote_checksum = metadata.get("sha256")
            if remote_checksum != checksum:
                raise B2ChecksumError(
                    f"checksum verification failed for key '{key}': "
                    f"expected {checksum}, got {remote_checksum}"
                )

        self._with_retries(f"upload_file key={key}", _operation)
        logger.info("Uploaded %s to b2://%s/%s", source, self.bucket_name, key)

    def download_file(self, remote_key: str, local_path: str | Path) -> None:
        """
        Download one B2 object to local storage.

        Tactical context:
            Precise file recovery supports rapid rebuild of edge-ready runtimes
            when deployed teams need to restore degraded compute nodes.
        """
        key = self._normalize_key(remote_key)
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        def _operation() -> None:
            self._client.download_file(self.bucket_name, key, str(target))

        self._with_retries(f"download_file key={key}", _operation)
        logger.info("Downloaded b2://%s/%s to %s", self.bucket_name, key, target)

    def list_keys(self, prefix: str) -> list[str]:
        """
        List object keys under a B2 prefix.

        Tactical context:
            Deterministic inventory of vault contents enables auditable staging
            plans before synchronizing weights into operational enclaves.
        """
        normalized_prefix = self._normalize_prefix(prefix)

        def _operation() -> list[str]:
            paginator = self._client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=normalized_prefix)
            keys: list[str] = []
            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj.get("Key")
                    if key:
                        keys.append(str(key))
            return keys

        keys = self._with_retries(f"list_keys prefix={normalized_prefix}", _operation)
        logger.info("Listed %d keys under prefix '%s'", len(keys), normalized_prefix)
        return keys

    def sync_down(self, remote_prefix: str, local_dir: str | Path) -> list[Path]:
        """
        Pull all files under a B2 prefix into a local directory.

        Tactical context:
            Bulk synchronization allows forward teams to preload required model
            artifacts before mission windows with constrained connectivity.
        """
        normalized_prefix = self._normalize_prefix(remote_prefix)
        destination = Path(local_dir)
        destination.mkdir(parents=True, exist_ok=True)

        downloaded_paths: list[Path] = []
        for key in self.list_keys(normalized_prefix):
            if key.endswith("/"):
                continue
            relative_fragment = key[len(normalized_prefix) :] if normalized_prefix and key.startswith(normalized_prefix) else key
            target_path = self._safe_local_target(destination, relative_fragment)
            self.download_file(key, target_path)
            downloaded_paths.append(target_path)

        logger.info(
            "Synced down %d files from prefix '%s' into %s",
            len(downloaded_paths),
            normalized_prefix,
            destination,
        )
        return downloaded_paths

    def sync_up(self, local_dir: str | Path, remote_prefix: str) -> list[str]:
        """
        Upload all files from a local directory into a B2 prefix.

        Tactical context:
            Structured promotion of newly trained artifacts keeps the sovereign
            vault aligned with current battlefield model baselines.
        """
        source_dir = Path(local_dir)
        if not source_dir.exists() or not source_dir.is_dir():
            raise ValueError(f"local_dir must point to an existing directory: {source_dir}")

        normalized_prefix = self._normalize_prefix(remote_prefix)
        uploaded_keys: list[str] = []

        for file_path in sorted(path for path in source_dir.rglob("*") if path.is_file()):
            relative_key = file_path.relative_to(source_dir).as_posix()
            remote_key = f"{normalized_prefix}{relative_key}" if normalized_prefix else relative_key
            self.upload_file(file_path, remote_key)
            uploaded_keys.append(remote_key)

        logger.info(
            "Synced up %d files from %s into prefix '%s'",
            len(uploaded_keys),
            source_dir,
            normalized_prefix,
        )
        return uploaded_keys

    def file_exists(self, remote_key: str) -> bool:
        """
        Check whether a specific object exists in B2.

        Tactical context:
            Presence checks help orchestrators avoid redundant transfers and
            quickly decide whether a mission package is combat-ready.
        """
        key = self._normalize_key(remote_key)
        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self._client.head_object(Bucket=self.bucket_name, Key=key)
                return True
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code in {"404", "NoSuchKey", "NotFound"}:
                    logger.info("Key not found in B2: %s", key)
                    return False
                last_exception = exc
            except Exception as exc:  # nosec B110 - controlled retry wrapper with re-raise
                last_exception = exc

            if attempt < self.max_retries:
                delay = self.retry_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "B2 file_exists key=%s failed on attempt %d/%d: %s; retrying in %.2fs",
                    key,
                    attempt,
                    self.max_retries,
                    last_exception,
                    delay,
                )
                time.sleep(delay)

        raise B2OperationError(
            f"B2 file_exists key={key} failed after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    def delete_file(self, remote_key: str) -> None:
        """
        Delete an object from the B2 bucket.

        Tactical context:
            Controlled deletion removes superseded or compromised artifacts from
            distribution channels to protect downstream deployments.
        """
        key = self._normalize_key(remote_key)

        def _operation() -> None:
            self._client.delete_object(Bucket=self.bucket_name, Key=key)

        self._with_retries(f"delete_file key={key}", _operation)
        logger.info("Deleted b2://%s/%s", self.bucket_name, key)

    def get_file_size(self, remote_key: str) -> int:
        """Return object size in bytes for one B2 key.

        Tactical context:
            Size telemetry supports transfer planning and mission cache
            budgeting before edge deployments are synchronized.
        """
        key = self._normalize_key(remote_key)

        def _operation() -> int:
            metadata = self._client.head_object(Bucket=self.bucket_name, Key=key)
            return int(metadata.get("ContentLength", 0))

        return self._with_retries(f"get_file_size key={key}", _operation)

    def get_file_sha256(self, remote_key: str) -> str | None:
        """Return stored SHA-256 metadata for an object when available.

        Tactical context:
            Checksum retrieval allows independent integrity verification
            after long-haul uploads in contested network conditions.
        """
        key = self._normalize_key(remote_key)

        def _operation() -> str | None:
            metadata = self._client.head_object(Bucket=self.bucket_name, Key=key)
            user_meta = metadata.get("Metadata", {})
            if not isinstance(user_meta, dict):
                return None
            checksum = user_meta.get("sha256")
            return str(checksum) if checksum else None

        return self._with_retries(f"get_file_sha256 key={key}", _operation)

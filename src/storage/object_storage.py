"""
Cloudflare R2 S3-compatible connector for sovereign vault operations.

Tactical context:
    Weight artifacts, adapters, and evaluation payloads are strategic resources.
    This connector enforces resilient transfer procedures so deployed teams can
    rehydrate model stacks from the vault during contested, disconnected, or
    degraded operations. Cloudflare R2 shares the same S3 API used by
    boto3 and provides free internal traffic within the Hetzner eu-central zone.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
import warnings
from pathlib import Path
from typing import Callable, TypeVar

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("s3m.storage.object_storage")

T = TypeVar("T")


class ObjectStorageError(RuntimeError):
    """Base exception for storage connector failures."""


class ObjectStorageConfigError(ObjectStorageError):
    """Raised when required object storage connector configuration is missing."""


class ObjectStorageOperationError(ObjectStorageError):
    """Raised when an S3-compatible operation cannot be completed safely."""


class ObjectStorageChecksumError(ObjectStorageOperationError):
    """Raised when uploaded object checksum does not match local source data."""


class ObjectStorageConnector:
    """Unified object storage interface for mission artifact transport."""

    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        key_id: str | None = None,
        app_key: str | None = None,
        bucket_name: str | None = None,
        endpoint: str | None = None,
        endpoint_url: str | None = None,
        region_name: str = "auto",
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        emulation_root: str | Path | None = None,
    ) -> None:
        """
        Initialize object storage S3-compatible client from environment or explicit values.

        Tactical context:
            Strong defaults and explicit validation reduce misconfiguration risk
            before high-value model artifacts begin moving through the vault.
        """
        self._emulation_root: Path | None = None
        if emulation_root is not None:
            root = Path(emulation_root).resolve()
            root.mkdir(parents=True, exist_ok=True)
            self._emulation_root = root
            self.access_key = access_key or ""
            self.secret_key = secret_key or ""
            self.endpoint = (endpoint or endpoint_url or "").strip()
            self.bucket_name = (bucket_name or "s3m-vault").strip()
            self.region_name = region_name
            self.key_id = self.access_key
            self.app_key = self.secret_key
            self.max_retries = max_retries
            self.retry_base_seconds = retry_base_seconds
            self._client = None
            return

        if key_id is not None:
            warnings.warn(
                "key_id is deprecated; use access_key instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if app_key is not None:
            warnings.warn(
                "app_key is deprecated; use secret_key instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        resolved_access_key = access_key if access_key is not None else key_id
        resolved_secret_key = secret_key if secret_key is not None else app_key
        resolved_endpoint = endpoint if endpoint is not None else endpoint_url

        self.access_key = self._required_config(resolved_access_key, "S3M_STORAGE_ACCESS_KEY")
        self.secret_key = self._required_config(resolved_secret_key, "S3M_STORAGE_SECRET_KEY")
        self.endpoint = self._required_config(resolved_endpoint, "S3M_STORAGE_ENDPOINT")
        self.bucket_name = (bucket_name or os.getenv("S3M_STORAGE_BUCKET_NAME", "s3m-vault")).strip()
        self.region_name = region_name
        # Compatibility aliases for transitional integrations.
        self.key_id = self.access_key
        self.app_key = self.secret_key

        if not self.bucket_name:
            raise ObjectStorageConfigError("S3M_STORAGE_BUCKET_NAME resolved to an empty value")
        if max_retries <= 0:
            raise ValueError("max_retries must be >= 1")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds must be >= 0")

        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name,
        )

    @classmethod
    def from_env(cls) -> "ObjectStorageConnector":
        """Construct connector using S3M_STORAGE_* environment variables.

        Tactical context:
            Standardized environment bootstrap keeps vault transfer tooling
            interoperable across Hetzner workers and operator laptops.
        """
        return cls()

    @classmethod
    def from_config(cls, config: dict[str, object]) -> "ObjectStorageConnector":
        """Construct connector from object storage config payload."""
        payload = config.get("object_storage", {}) if isinstance(config, dict) else {}
        section = payload if isinstance(payload, dict) else {}
        return cls(
            access_key=section.get("access_key") if isinstance(section.get("access_key"), str) else None,
            secret_key=section.get("secret_key") if isinstance(section.get("secret_key"), str) else None,
            bucket_name=section.get("bucket_name") if isinstance(section.get("bucket_name"), str) else None,
            endpoint=section.get("endpoint") if isinstance(section.get("endpoint"), str) else None,
            region_name=section.get("region", "auto") if isinstance(section.get("region"), str) else "auto",
            max_retries=int(section.get("max_retries", 3)),
        )

    @classmethod
    def for_cloudflare_r2(
        cls,
        *,
        account_id: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket_name: str = "s3m-vault",
    ) -> "ObjectStorageConnector":
        """Construct connector pre-configured for Cloudflare R2.

        Tactical context:
            R2 provides zero-egress-cost artifact distribution, enabling
            unconstrained model pulls from both Hetzner CPU and RunPod GPU
            nodes without transfer budget pressure during high-tempo training.
        """
        resolved_account_id = (
            account_id or os.getenv("S3M_CF_ACCOUNT_ID", "")
        ).strip()
        if not resolved_account_id:
            raise ObjectStorageConfigError(
                "Cloudflare R2 requires S3M_CF_ACCOUNT_ID"
            )
        return cls(
            access_key=access_key or os.getenv("S3M_R2_ACCESS_KEY_ID"),
            secret_key=secret_key or os.getenv("S3M_R2_SECRET_ACCESS_KEY"),
            endpoint=f"https://{resolved_account_id}.r2.cloudflarestorage.com",
            bucket_name=bucket_name,
            region_name="auto",
        )

    @staticmethod
    def _required_config(value: str | None, env_name: str) -> str:
        resolved = (value or os.getenv(env_name, "")).strip()
        if not resolved:
            raise ObjectStorageConfigError(
                f"Missing required Cloudflare R2 configuration: {env_name}"
            )
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
                    "Object Storage %s failed on attempt %d/%d: %s; retrying in %.2fs",
                    action,
                    attempt,
                    self.max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)

        raise ObjectStorageOperationError(
            f"Object Storage {action} failed after {self.max_retries} attempts: {last_exception}"
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

    def _emulated_path(self, remote_key: str) -> Path:
        if self._emulation_root is None:
            raise RuntimeError("emulated path requested without emulation root")
        return self._safe_local_target(self._emulation_root, self._normalize_key(remote_key))

    def upload_file(self, local_path: str | Path, remote_key: str) -> dict[str, object]:
        """
        Upload one local artifact to object storage and verify SHA-256 integrity.

        Tactical context:
            Checksum verification prevents silent corruption of mission-critical
            model payloads before they are staged for downstream pull operations.
        """
        source = Path(local_path)
        if not source.exists() or not source.is_file():
            raise ValueError(f"local_path must point to an existing file: {source}")

        key = self._normalize_key(remote_key)
        checksum = self._sha256_file(source)
        size_bytes = source.stat().st_size

        if self._emulation_root is not None:
            target = self._emulated_path(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            uploaded_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return {
                "remote_key": key,
                "etag": checksum,
                "size_bytes": int(size_bytes),
                "uploaded_at": uploaded_at,
            }

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
                raise ObjectStorageChecksumError(
                    f"checksum verification failed for key '{key}': "
                    f"expected {checksum}, got {remote_checksum}"
                )

        self._with_retries(f"upload_file key={key}", _operation)
        logger.info("Uploaded %s to storage://%s/%s", source, self.bucket_name, key)
        uploaded_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {
            "remote_key": key,
            "etag": checksum,
            "size_bytes": int(size_bytes),
            "uploaded_at": uploaded_at,
        }

    def download_file(self, remote_key: str, local_path: str | Path) -> dict[str, object]:
        """
        Download one object storage key to local storage.

        Tactical context:
            Precise file recovery supports rapid rebuild of edge-ready runtimes
            when deployed teams need to restore degraded compute nodes.
        """
        key = self._normalize_key(remote_key)
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if self._emulation_root is not None:
            source = self._emulated_path(key)
            if not source.exists() or not source.is_file():
                raise FileNotFoundError(f"Object not found in emulated storage: {key}")
            shutil.copy2(source, target)
            return {"remote_key": key, "size_bytes": int(target.stat().st_size)}

        def _operation() -> None:
            self._client.download_file(self.bucket_name, key, str(target))

        self._with_retries(f"download_file key={key}", _operation)
        logger.info("Downloaded storage://%s/%s to %s", self.bucket_name, key, target)
        size_bytes = int(target.stat().st_size) if target.exists() else 0
        return {"remote_key": key, "size_bytes": size_bytes}

    def list_keys(self, prefix: str) -> list[str]:
        """
        List object keys under an object storage prefix.

        Tactical context:
            Deterministic inventory of vault contents enables auditable staging
            plans before synchronizing weights into operational enclaves.
        """
        normalized_prefix = self._normalize_prefix(prefix)

        if self._emulation_root is not None:
            base = self._emulated_path(normalized_prefix) if normalized_prefix else self._emulation_root
            if base is None or not base.exists():
                return []
            keys: list[str] = []
            if base.is_file():
                return [str(base.relative_to(self._emulation_root).as_posix())]
            for path in base.rglob("*"):
                if path.is_file():
                    keys.append(path.relative_to(self._emulation_root).as_posix())
            return sorted(keys)

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
        Pull all files under an object storage prefix into a local directory.

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
        Upload all files from a local directory into an object storage prefix.

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
        Check whether a specific object exists in object storage.

        Tactical context:
            Presence checks help orchestrators avoid redundant transfers and
            quickly decide whether a mission package is combat-ready.
        """
        key = self._normalize_key(remote_key)
        last_exception: Exception | None = None

        if self._emulation_root is not None:
            path = self._emulated_path(key)
            return path.exists() and path.is_file()

        for attempt in range(1, self.max_retries + 1):
            try:
                self._client.head_object(Bucket=self.bucket_name, Key=key)
                return True
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code in {"404", "NoSuchKey", "NotFound"}:
                    logger.info("Key not found in object storage: %s", key)
                    return False
                last_exception = exc
            except Exception as exc:  # nosec B110 - controlled retry wrapper with re-raise
                last_exception = exc

            if attempt < self.max_retries:
                delay = self.retry_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Object Storage file_exists key=%s failed on attempt %d/%d: %s; retrying in %.2fs",
                    key,
                    attempt,
                    self.max_retries,
                    last_exception,
                    delay,
                )
                time.sleep(delay)

        raise ObjectStorageOperationError(
            f"Object Storage file_exists key={key} failed after {self.max_retries} attempts: {last_exception}"
        ) from last_exception

    def delete_file(self, remote_key: str) -> None:
        """
        Delete an object from the object storage bucket.

        Tactical context:
            Controlled deletion removes superseded or compromised artifacts from
            distribution channels to protect downstream deployments.
        """
        key = self._normalize_key(remote_key)

        if self._emulation_root is not None:
            path = self._emulated_path(key)
            if path.exists():
                path.unlink()
            return

        def _operation() -> None:
            self._client.delete_object(Bucket=self.bucket_name, Key=key)

        self._with_retries(f"delete_file key={key}", _operation)
        logger.info("Deleted storage://%s/%s", self.bucket_name, key)

    def generate_presigned_url(
        self,
        remote_key: str,
        *,
        method: str = "get_object",
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned URL for direct HTTP access from RunPod/Hetzner.

        Tactical context:
            Presigned URLs allow GPU workers to pull large model artifacts
            directly via HTTP without needing boto3 credentials baked into
            ephemeral RunPod containers. Reduces credential surface area.
        """
        key = self._normalize_key(remote_key)
        if self._emulation_root is not None:
            return f"file://{self._emulated_path(key)}"
        return self._client.generate_presigned_url(
            method,
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )

    def multipart_upload(
        self,
        local_path: str | Path,
        remote_key: str,
        *,
        part_size_mb: int = 100,
    ) -> dict[str, object]:
        """Upload large files via S3 multipart upload for reliability.

        Tactical context:
            Model weight files (14-300GB) require multipart transfer to
            survive transient network interruptions during vault seeding.
            Merged FP16 models from RunPod are 28-93 GB each and MUST
            use multipart to avoid timeout failures on single PUT.
        """
        source = Path(local_path)
        if not source.exists() or not source.is_file():
            raise ValueError(f"local_path must point to an existing file: {source}")
        key = self._normalize_key(remote_key)
        checksum = self._sha256_file(source)
        part_size = part_size_mb * 1024 * 1024

        if self._emulation_root is not None:
            return self.upload_file(local_path, remote_key)

        mpu = self._client.create_multipart_upload(
            Bucket=self.bucket_name,
            Key=key,
            Metadata={"sha256": checksum},
        )
        upload_id = mpu["UploadId"]
        parts: list[dict[str, object]] = []
        try:
            with source.open("rb") as fh:
                part_number = 1
                while True:
                    data = fh.read(part_size)
                    if not data:
                        break
                    resp = self._client.upload_part(
                        Bucket=self.bucket_name,
                        Key=key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=data,
                    )
                    parts.append({"PartNumber": part_number, "ETag": resp["ETag"]})
                    logger.info("Uploaded part %d for %s", part_number, key)
                    part_number += 1
            self._client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            self._client.abort_multipart_upload(
                Bucket=self.bucket_name, Key=key, UploadId=upload_id,
            )
            raise
        logger.info("Multipart upload complete: %s (%d parts)", key, len(parts))
        return {
            "remote_key": key,
            "etag": checksum,
            "size_bytes": int(source.stat().st_size),
            "parts": len(parts),
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def get_file_size(self, remote_key: str) -> int:
        """Return object size in bytes for one object storage key.

        Tactical context:
            Size telemetry supports transfer planning and mission cache
            budgeting before edge deployments are synchronized.
        """
        key = self._normalize_key(remote_key)

        if self._emulation_root is not None:
            path = self._emulated_path(key)
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"Object not found in emulated storage: {key}")
            return int(path.stat().st_size)

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

        if self._emulation_root is not None:
            path = self._emulated_path(key)
            if not path.exists() or not path.is_file():
                return None
            return self._sha256_file(path)

        def _operation() -> str | None:
            metadata = self._client.head_object(Bucket=self.bucket_name, Key=key)
            user_meta = metadata.get("Metadata", {})
            if not isinstance(user_meta, dict):
                return None
            checksum = user_meta.get("sha256")
            return str(checksum) if checksum else None

        return self._with_retries(f"get_file_sha256 key={key}", _operation)

    # Compatibility helpers used by sync/oracle tooling.
    def sync_prefix_to_local(
        self,
        *,
        prefix: str,
        local_dir: str | Path,
        blocked_tokens: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, int]:
        tokens = [token.lower() for token in (blocked_tokens or []) if token]
        downloaded = 0
        skipped = 0
        bytes_transferred = 0
        for key in self.list_keys(prefix):
            lowered = key.lower()
            if any(token in lowered for token in tokens):
                skipped += 1
                continue
            if key.endswith("/"):
                skipped += 1
                continue
            normalized_prefix = self._normalize_prefix(prefix)
            relative = key[len(normalized_prefix) :] if normalized_prefix and key.startswith(normalized_prefix) else key
            target = self._safe_local_target(Path(local_dir), relative)
            result = self.download_file(key, target)
            downloaded += 1
            bytes_transferred += int(result.get("size_bytes", 0))
        return {
            "downloaded": downloaded,
            "uploaded": 0,
            "skipped": skipped,
            "bytes_transferred": bytes_transferred,
        }

    def sync_local_to_prefix(self, *, local_dir: str | Path, prefix: str) -> dict[str, int]:
        source = Path(local_dir)
        if not source.exists():
            return {"downloaded": 0, "uploaded": 0, "skipped": 0, "bytes_transferred": 0}
        uploaded = 0
        bytes_transferred = 0
        normalized_prefix = self._normalize_prefix(prefix)
        for file_path in sorted(path for path in source.rglob("*") if path.is_file()):
            remote_key = f"{normalized_prefix}{file_path.relative_to(source).as_posix()}"
            result = self.upload_file(file_path, remote_key)
            uploaded += 1
            bytes_transferred += int(result.get("size_bytes", 0))
        return {
            "downloaded": 0,
            "uploaded": uploaded,
            "skipped": 0,
            "bytes_transferred": bytes_transferred,
        }

    def put_bytes(self, key: str, payload: bytes, content_type: str = "application/octet-stream") -> None:
        normalized_key = self._normalize_key(key)
        if self._emulation_root is not None:
            target = self._emulated_path(normalized_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            return
        self._client.put_object(
            Bucket=self.bucket_name,
            Key=normalized_key,
            Body=payload,
            ContentType=content_type,
        )

    def upload_bytes(self, key: str, payload: bytes, content_type: str = "application/octet-stream") -> dict[str, object]:
        self.put_bytes(key, payload, content_type=content_type)
        return {
            "remote_key": self._normalize_key(key),
            "size_bytes": int(len(payload)),
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def get_bytes(self, key: str) -> bytes:
        normalized_key = self._normalize_key(key)
        if self._emulation_root is not None:
            source = self._emulated_path(normalized_key)
            if not source.exists() or not source.is_file():
                raise FileNotFoundError(f"Object not found in emulated storage: {normalized_key}")
            return source.read_bytes()
        response = self._client.get_object(Bucket=self.bucket_name, Key=normalized_key)
        body = response.get("Body")
        if body is None:
            return b""
        return body.read()

    def put_json(self, key: str, payload: dict[str, object]) -> None:
        import json

        self.put_bytes(key, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")

    def upload_json(self, key: str, payload: dict[str, object]) -> dict[str, object]:
        import json

        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.put_bytes(key, encoded, "application/json")
        return {
            "remote_key": self._normalize_key(key),
            "etag": hashlib.md5(encoded).hexdigest(),
            "size_bytes": int(len(encoded)),
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def get_json(self, key: str) -> dict[str, object]:
        import json

        payload = json.loads(self.get_bytes(key).decode("utf-8"))
        return payload if isinstance(payload, dict) else {"items": payload}

    def exists(self, key: str) -> bool:
        return self.file_exists(key)

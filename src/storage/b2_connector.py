"""BackBlaze B2 (S3 API) connector for deterministic artifact sync.

Military/tactical context:
This connector keeps model/dataset movement deterministic and auditable so
distributed training nodes can recover quickly without exposing data to
non-approved cloud APIs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

try:  # pragma: no cover - import guard for minimal test environments
    import boto3
except Exception:  # pragma: no cover - boto3 may be unavailable in unit-only CI jobs
    boto3 = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency guard
    from botocore.exceptions import ClientError
except Exception:  # pragma: no cover
    ClientError = Exception  # type: ignore[assignment]


class B2Connector:
    """Thin S3-compatible connector for BackBlaze B2 buckets."""

    def __init__(
        self,
        *,
        key_id: str,
        app_key: str,
        bucket_name: str,
        endpoint_url: str,
        region_name: str = "us-east-1",
    ) -> None:
        self.key_id = self._require_text(key_id, "key_id")
        self.app_key = self._require_text(app_key, "app_key")
        self.bucket_name = self._require_text(bucket_name, "bucket_name")
        self.endpoint_url = self._require_text(endpoint_url, "endpoint_url")
        self.region_name = self._require_text(region_name, "region_name")

        if boto3 is None:  # pragma: no cover - exercised only in missing-dep environments
            raise RuntimeError("boto3 is required for B2Connector")

        session = boto3.session.Session()
        self._client = session.client(
            "s3",
            aws_access_key_id=self.key_id,
            aws_secret_access_key=self.app_key,
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
        )

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "B2Connector":
        """Build connector from deployment config map with env support."""
        root = dict(config)
        backblaze = root.get("backblaze", root)
        if not isinstance(backblaze, dict):
            raise ValueError("backblaze config must be a mapping")

        credentials = backblaze.get("credentials", {})
        if not isinstance(credentials, dict):
            credentials = {}

        key_id = cls._resolve_value(
            explicit=backblaze.get("key_id"),
            env_name=credentials.get("key_id_env", "S3M_B2_KEY_ID"),
        )
        app_key = cls._resolve_value(
            explicit=backblaze.get("app_key"),
            env_name=credentials.get("app_key_env", "S3M_B2_APP_KEY"),
        )
        bucket_name = cls._resolve_value(
            explicit=backblaze.get("bucket_name"),
            env_name=backblaze.get("bucket_name_env", "S3M_B2_BUCKET_NAME"),
        )
        endpoint_url = cls._resolve_value(
            explicit=backblaze.get("endpoint"),
            env_name=backblaze.get("endpoint_env", "S3M_B2_ENDPOINT"),
        )
        region_name = str(backblaze.get("region_name", "us-east-1"))

        return cls(
            key_id=key_id,
            app_key=app_key,
            bucket_name=bucket_name,
            endpoint_url=endpoint_url,
            region_name=region_name,
        )

    def list_objects(self, prefix: str) -> list[dict[str, Any]]:
        """List all objects under a prefix."""
        normalized = self._normalize_prefix(prefix)
        objects: list[dict[str, Any]] = []
        token: str | None = None

        while True:
            payload: dict[str, Any] = {"Bucket": self.bucket_name, "Prefix": normalized}
            if token:
                payload["ContinuationToken"] = token
            response = self._client.list_objects_v2(**payload)
            objects.extend(response.get("Contents", []) or [])
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
            if not token:
                break
        return objects

    def sync_prefix_to_local(
        self,
        prefix: str,
        local_dir: str | Path,
        blocked_tokens: Iterable[str] | None = None,
    ) -> dict[str, int]:
        """Mirror remote prefix to local directory without destructive deletes."""
        normalized = self._normalize_prefix(prefix)
        root = Path(local_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        blocked = [str(token).strip().lower() for token in (blocked_tokens or []) if str(token).strip()]

        downloaded = 0
        skipped = 0
        bytes_transferred = 0

        for obj in self.list_objects(normalized):
            key = str(obj.get("Key", ""))
            if not key or key.endswith("/"):
                continue
            if not key.startswith(normalized):
                continue
            lowered_key = key.lower()
            if any(token in lowered_key for token in blocked):
                skipped += 1
                continue

            rel = key[len(normalized) :]
            if not rel:
                rel = Path(key).name
            destination = self._safe_destination(root, rel)
            destination.parent.mkdir(parents=True, exist_ok=True)

            remote_size = int(obj.get("Size", 0))
            if destination.exists() and destination.is_file() and destination.stat().st_size == remote_size:
                skipped += 1
                continue

            self._client.download_file(self.bucket_name, key, str(destination))
            downloaded += 1
            bytes_transferred += remote_size

        return {
            "downloaded": downloaded,
            "uploaded": 0,
            "skipped": skipped,
            "bytes_transferred": bytes_transferred,
        }

    def sync_local_to_prefix(self, local_dir: str | Path, prefix: str) -> dict[str, int]:
        """Upload local directory to remote prefix without remote deletes."""
        root = Path(local_dir).resolve()
        normalized = self._normalize_prefix(prefix)
        if not root.exists():
            return {"downloaded": 0, "uploaded": 0, "skipped": 0, "bytes_transferred": 0}

        uploaded = 0
        skipped = 0
        bytes_transferred = 0

        for path in self._iter_files(root):
            rel = path.relative_to(root).as_posix()
            key = f"{normalized}{rel}"
            local_size = path.stat().st_size

            remote_size = self._remote_size(key)
            if remote_size is not None and int(remote_size) == int(local_size):
                skipped += 1
                continue

            self._client.upload_file(str(path), self.bucket_name, key)
            uploaded += 1
            bytes_transferred += int(local_size)

        return {
            "downloaded": 0,
            "uploaded": uploaded,
            "skipped": skipped,
            "bytes_transferred": bytes_transferred,
        }

    def _remote_size(self, key: str) -> int | None:
        try:
            response = self._client.head_object(Bucket=self.bucket_name, Key=key)
        except ClientError:
            return None
        return int(response.get("ContentLength", 0))

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        text = str(prefix or "").strip().lstrip("/")
        if ".." in text:
            raise ValueError("prefix contains unsupported traversal token")
        if text and not text.endswith("/"):
            text += "/"
        return text

    @staticmethod
    def _safe_destination(root: Path, relative_path: str) -> Path:
        rel = relative_path.strip().lstrip("/")
        destination = (root / rel).resolve()
        if root != destination and root not in destination.parents:
            raise ValueError("resolved destination escapes root directory")
        return destination

    @staticmethod
    def _iter_files(root: Path) -> Iterable[Path]:
        for candidate in sorted(root.rglob("*")):
            if candidate.is_file():
                yield candidate

    @staticmethod
    def _resolve_value(explicit: Any, env_name: Any) -> str:
        if isinstance(explicit, str) and explicit.strip():
            text = explicit.strip()
            if text.startswith("${") and text.endswith("}"):
                env_key = text[2:-1].strip()
                return B2Connector._require_text(os.getenv(env_key), env_key)
            return text
        env_key = str(env_name or "").strip()
        return B2Connector._require_text(os.getenv(env_key), env_key or "env")

    @staticmethod
    def _require_text(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value.strip()

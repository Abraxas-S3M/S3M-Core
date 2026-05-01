"""
Cloudflare R2 storage client for S3M-Engine training vault workflows.

Tactical context:
    Training data and model artifacts are mission-critical assets. This client
    provides controlled upload/download/list operations so pipeline operators can
    maintain a trustworthy catalog of vault contents before edge deployment.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class R2Client:
    """S3-compatible client wrapper for Cloudflare R2 vault operations."""

    def __init__(self) -> None:
        self.bucket = self._required_env("R2_BUCKET")
        self.endpoint = self._required_env("R2_ENDPOINT")
        self.access_key = self._required_env("R2_ACCESS_KEY")
        self.secret_key = self._required_env("R2_SECRET_KEY")
        self.public_base_url = os.getenv("R2_PUBLIC_BASE_URL", "").strip().rstrip("/")

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    @staticmethod
    def _required_env(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise ValueError(f"Missing required environment variable: {name}")
        return value

    @staticmethod
    def _normalize_key(r2_key: str) -> str:
        if not isinstance(r2_key, str):
            raise ValueError("r2_key must be a string")
        key = r2_key.strip().lstrip("/")
        if not key:
            raise ValueError("r2_key must be non-empty")
        if ".." in key.split("/"):
            raise ValueError("r2_key must not include path traversal segments")
        return key

    def _public_url(self, r2_key: str) -> str:
        safe_key = quote(r2_key, safe="/")
        return f"{self.public_base_url}/{safe_key}"

    def upload(self, local_path: Path, r2_key: str) -> str:
        source = Path(local_path)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"local_path does not exist or is not a file: {source}")

        key = self._normalize_key(r2_key)
        self._client.upload_file(str(source), self.bucket, key)
        if self.public_base_url:
            return self._public_url(key)
        return self.get_signed_url(key)

    def download(self, r2_key: str, local_path: Path) -> Path:
        key = self._normalize_key(r2_key)
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self.bucket, key, str(target))
        return target

    def list_files(self, prefix: str = "") -> list[dict[str, Any]]:
        normalized_prefix = prefix.strip().lstrip("/")
        paginator = self._client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self.bucket, Prefix=normalized_prefix)
        records: list[dict[str, Any]] = []

        for page in pages:
            for obj in page.get("Contents", []):
                key = obj.get("Key")
                if not key:
                    continue
                last_modified = obj.get("LastModified")
                records.append(
                    {
                        "key": str(key),
                        "size": int(obj.get("Size", 0)),
                        "last_modified": last_modified.isoformat() if hasattr(last_modified, "isoformat") else str(last_modified or ""),
                    }
                )
        return records

    def exists(self, r2_key: str) -> bool:
        key = self._normalize_key(r2_key)
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def delete(self, r2_key: str) -> bool:
        key = self._normalize_key(r2_key)
        if not self.exists(key):
            return False
        self._client.delete_object(Bucket=self.bucket, Key=key)
        return True

    def get_signed_url(self, r2_key: str, expires: int = 3600) -> str:
        key = self._normalize_key(r2_key)
        if expires <= 0:
            raise ValueError("expires must be > 0 seconds")
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(expires),
        )

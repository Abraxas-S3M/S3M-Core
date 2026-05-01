"""Unit tests for Cloudflare R2 vault client operations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.vault.r2_client import R2Client


@pytest.fixture
def r2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set deterministic R2 env for secure vault bootstrap tests."""
    monkeypatch.setenv("R2_BUCKET", "s3m-training")
    monkeypatch.setenv("R2_ENDPOINT", "https://acct.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY", "unit-test-access")
    monkeypatch.setenv("R2_SECRET_KEY", "unit-test-secret")


@pytest.fixture
def mocked_r2_client() -> tuple[MagicMock, MagicMock]:
    """Patch boto3 client factory and return controllable client mock."""
    with patch("src.vault.r2_client.boto3.client") as client_factory:
        client = MagicMock()
        client_factory.return_value = client
        yield client, client_factory


def test_init_reads_r2_environment(
    r2_env: None, mocked_r2_client: tuple[MagicMock, MagicMock]
) -> None:
    """Vault client binds required env vars into S3-compatible connector."""
    client, client_factory = mocked_r2_client
    r2 = R2Client()

    assert r2.bucket == "s3m-training"
    assert r2.endpoint == "https://acct.r2.cloudflarestorage.com"
    assert r2.access_key == "unit-test-access"
    assert r2.secret_key == "unit-test-secret"
    client_factory.assert_called_once()
    assert client is not None


def test_init_requires_mandatory_env_vars(
    monkeypatch: pytest.MonkeyPatch, mocked_r2_client: tuple[MagicMock, MagicMock]
) -> None:
    """Missing credentials fail closed before any vault data access."""
    monkeypatch.delenv("R2_BUCKET", raising=False)
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    monkeypatch.delenv("R2_ACCESS_KEY", raising=False)
    monkeypatch.delenv("R2_SECRET_KEY", raising=False)

    with pytest.raises(ValueError, match="R2_BUCKET"):
        R2Client()

    _, client_factory = mocked_r2_client
    client_factory.assert_not_called()


def test_upload_returns_public_url_when_configured(
    r2_env: None,
    monkeypatch: pytest.MonkeyPatch,
    mocked_r2_client: tuple[MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    """Public URL mode supports direct dataset distribution lanes."""
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://cdn.s3m.local/vault")
    mock_client, _ = mocked_r2_client
    r2 = R2Client()
    source = tmp_path / "payload.bin"
    source.write_bytes(b"payload")

    url = r2.upload(source, "datasets/track-a/scenario-1/payload.bin")

    mock_client.upload_file.assert_called_once_with(
        str(source),
        "s3m-training",
        "datasets/track-a/scenario-1/payload.bin",
    )
    assert url == "https://cdn.s3m.local/vault/datasets/track-a/scenario-1/payload.bin"


def test_upload_returns_signed_url_without_public_base(
    r2_env: None, mocked_r2_client: tuple[MagicMock, MagicMock], tmp_path: Path
) -> None:
    """Signed URL fallback minimizes exposed public vault surface."""
    r2 = R2Client()
    source = tmp_path / "weights.gguf"
    source.write_bytes(b"weights")

    with patch.object(r2, "get_signed_url", return_value="https://signed.local/object") as signed_mock:
        url = r2.upload(source, "/models/edge/weights.gguf")

    assert url == "https://signed.local/object"
    signed_mock.assert_called_once_with("models/edge/weights.gguf")


def test_download_creates_parent_and_returns_target(
    r2_env: None, mocked_r2_client: tuple[MagicMock, MagicMock], tmp_path: Path
) -> None:
    """Download path creation supports deterministic cache restoration."""
    mock_client, _ = mocked_r2_client
    r2 = R2Client()
    target = tmp_path / "cache" / "weights.gguf"

    resolved = r2.download("models/edge/weights.gguf", target)

    assert target.parent.exists()
    assert resolved == target
    mock_client.download_file.assert_called_once_with(
        "s3m-training",
        "models/edge/weights.gguf",
        str(target),
    )


def test_list_files_returns_key_size_last_modified(
    r2_env: None, mocked_r2_client: tuple[MagicMock, MagicMock]
) -> None:
    """Catalog inventory needs key/size/time tuple for sync diffs."""
    mock_client, _ = mocked_r2_client
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "Contents": [
                {
                    "Key": "datasets/track-a/scenario-1/a.json",
                    "Size": 128,
                    "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
                }
            ]
        }
    ]
    mock_client.get_paginator.return_value = paginator
    r2 = R2Client()

    files = r2.list_files("datasets/track-a")

    assert files == [
        {
            "key": "datasets/track-a/scenario-1/a.json",
            "size": 128,
            "last_modified": "2026-01-01T00:00:00+00:00",
        }
    ]
    paginator.paginate.assert_called_once_with(
        Bucket="s3m-training",
        Prefix="datasets/track-a",
    )


def test_exists_handles_not_found(
    r2_env: None, mocked_r2_client: tuple[MagicMock, MagicMock]
) -> None:
    """Missing key detection avoids unnecessary downstream fetch attempts."""
    mock_client, _ = mocked_r2_client
    mock_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "not found"}},
        "HeadObject",
    )
    r2 = R2Client()

    assert r2.exists("datasets/track-a/missing.json") is False


def test_delete_returns_false_when_object_missing(
    r2_env: None, mocked_r2_client: tuple[MagicMock, MagicMock]
) -> None:
    """Safe delete call reports absence without raising hard failures."""
    mock_client, _ = mocked_r2_client
    r2 = R2Client()

    with patch.object(r2, "exists", return_value=False):
        deleted = r2.delete("datasets/track-a/missing.json")

    assert deleted is False
    mock_client.delete_object.assert_not_called()


def test_delete_returns_true_when_object_deleted(
    r2_env: None, mocked_r2_client: tuple[MagicMock, MagicMock]
) -> None:
    """Deletion confirmation ensures stale artifacts can be retired cleanly."""
    mock_client, _ = mocked_r2_client
    r2 = R2Client()

    with patch.object(r2, "exists", return_value=True):
        deleted = r2.delete("datasets/track-a/stale.json")

    assert deleted is True
    mock_client.delete_object.assert_called_once_with(
        Bucket="s3m-training",
        Key="datasets/track-a/stale.json",
    )


def test_get_signed_url_uses_client_presign(
    r2_env: None, mocked_r2_client: tuple[MagicMock, MagicMock]
) -> None:
    """Presigned access supports time-boxed retrieval by processing nodes."""
    mock_client, _ = mocked_r2_client
    mock_client.generate_presigned_url.return_value = "https://signed.local/object"
    r2 = R2Client()

    url = r2.get_signed_url("/models/edge/weights.gguf", expires=1800)

    assert url == "https://signed.local/object"
    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "s3m-training", "Key": "models/edge/weights.gguf"},
        ExpiresIn=1800,
    )

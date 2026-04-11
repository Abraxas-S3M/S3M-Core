"""Tests for Hetzner Object Storage connector mission-storage operations."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError

from src.storage.object_storage import (
    ObjectStorageConfigError,
    ObjectStorageConnector,
    ObjectStorageOperationError,
)


@pytest.fixture
def object_storage_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide isolated environment variables for object storage bootstrap."""
    monkeypatch.setenv("S3M_STORAGE_ACCESS_KEY", "unit-test-key-id")
    monkeypatch.setenv("S3M_STORAGE_SECRET_KEY", "unit-test-app-key")
    monkeypatch.setenv("S3M_STORAGE_BUCKET_NAME", "unit-test-vault")
    monkeypatch.setenv("S3M_STORAGE_ENDPOINT", "https://s3.test.objectstorage.com")


@pytest.fixture
def mocked_client() -> tuple[MagicMock, MagicMock]:
    """Patch boto3 client construction and return a controllable mock client."""
    with patch("src.storage.object_storage.boto3.client") as client_factory:
        client = MagicMock()
        client_factory.return_value = client
        yield client, client_factory


@pytest.fixture
def connector(object_storage_env: None, mocked_client: tuple[MagicMock, MagicMock]) -> ObjectStorageConnector:
    """Create object storage connector with zero sleep delay for deterministic tests."""
    return ObjectStorageConnector(retry_base_seconds=0.0)


def _client(mocked_client: tuple[MagicMock, MagicMock]) -> MagicMock:
    return mocked_client[0]


def _client_factory(mocked_client: tuple[MagicMock, MagicMock]) -> MagicMock:
    return mocked_client[1]


def test_init_reads_environment_and_builds_s3_client(
    object_storage_env: None,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """Connector bootstraps from S3M_STORAGE_* variables with hardened defaults."""
    ObjectStorageConnector(retry_base_seconds=0.0)

    _client_factory(mocked_client).assert_called_once_with(
        "s3",
        endpoint_url="https://s3.test.objectstorage.com",
        aws_access_key_id="unit-test-key-id",
        aws_secret_access_key="unit-test-app-key",
        region_name="fsn1",
    )


def test_init_requires_mandatory_environment_values(
    monkeypatch: pytest.MonkeyPatch,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """Missing credential variables fail fast before transport begins."""
    monkeypatch.delenv("S3M_STORAGE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("S3M_STORAGE_SECRET_KEY", raising=False)
    monkeypatch.delenv("S3M_STORAGE_ENDPOINT", raising=False)

    with pytest.raises(ObjectStorageConfigError, match="S3M_STORAGE_ACCESS_KEY"):
        ObjectStorageConnector(retry_base_seconds=0.0)

    _client_factory(mocked_client).assert_not_called()


def test_upload_file_writes_metadata_and_verifies_sha256(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    """Upload flow stamps checksum metadata and validates post-write integrity."""
    local_file = tmp_path / "weights.gguf"
    payload = b"mission-payload"
    local_file.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    _client(mocked_client).head_object.return_value = {"Metadata": {"sha256": checksum}}

    connector.upload_file(local_file, "base-weights/phi3-medium/weights.gguf")

    _client(mocked_client).upload_file.assert_called_once_with(
        str(local_file),
        "unit-test-vault",
        "base-weights/phi3-medium/weights.gguf",
        ExtraArgs={"Metadata": {"sha256": checksum}},
    )
    _client(mocked_client).head_object.assert_called_once_with(
        Bucket="unit-test-vault",
        Key="base-weights/phi3-medium/weights.gguf",
    )


def test_upload_file_raises_after_checksum_mismatch_retries(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    """Checksum mismatches are treated as critical transfer failures."""
    local_file = tmp_path / "adapter.bin"
    local_file.write_bytes(b"critical-adapter")
    _client(mocked_client).head_object.return_value = {"Metadata": {"sha256": "invalid"}}

    with pytest.raises(ObjectStorageOperationError, match="upload_file"):
        connector.upload_file(local_file, "adapters/phi3-medium/track-a/adapter.bin")

    assert _client(mocked_client).upload_file.call_count == connector.max_retries
    assert _client(mocked_client).head_object.call_count == connector.max_retries


def test_download_file_creates_parent_directory_and_downloads(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    """Download path preparation supports predictable local recovery layout."""
    target_file = tmp_path / "cache" / "weights.bin"

    connector.download_file("quantized/phi3-medium/weights.bin", target_file)

    assert target_file.parent.exists()
    _client(mocked_client).download_file.assert_called_once_with(
        "unit-test-vault",
        "quantized/phi3-medium/weights.bin",
        str(target_file),
    )


def test_download_file_retries_transient_errors(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    """Transient download faults are retried with exponential backoff policy."""
    target_file = tmp_path / "cache" / "retry.bin"
    transient = ClientError({"Error": {"Code": "500", "Message": "transient"}}, "GetObject")
    _client(mocked_client).download_file.side_effect = [transient, None]

    connector.download_file("quantized/phi3-medium/retry.bin", target_file)

    assert _client(mocked_client).download_file.call_count == 2


def test_list_keys_returns_all_keys_under_prefix(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """Prefix inventory call aggregates keys across paginated responses."""
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Contents": [{"Key": "datasets/red/a.json"}, {"Key": "datasets/red/b.json"}]},
        {"Contents": [{"Key": "datasets/red/scenarios/c.json"}]},
    ]
    _client(mocked_client).get_paginator.return_value = paginator

    keys = connector.list_keys("datasets/red")

    assert keys == [
        "datasets/red/a.json",
        "datasets/red/b.json",
        "datasets/red/scenarios/c.json",
    ]
    paginator.paginate.assert_called_once_with(Bucket="unit-test-vault", Prefix="datasets/red/")


def test_sync_down_downloads_all_non_directory_keys(
    connector: ObjectStorageConnector,
    tmp_path: Path,
) -> None:
    """Bulk pull maps remote key layout into local operational cache tree."""
    destination = tmp_path / "cache"

    with patch.object(
        connector,
        "list_keys",
        return_value=["datasets/red/a.json", "datasets/red/scenarios/c.json", "datasets/red/"],
    ), patch.object(connector, "download_file") as download_mock:
        synced = connector.sync_down("datasets/red", destination)

    expected_a = (destination / "a.json").resolve()
    expected_c = (destination / "scenarios" / "c.json").resolve()

    assert synced == [expected_a, expected_c]
    download_mock.assert_has_calls(
        [
            call("datasets/red/a.json", expected_a),
            call("datasets/red/scenarios/c.json", expected_c),
        ]
    )


def test_sync_up_uploads_all_local_files_with_prefix(
    connector: ObjectStorageConnector,
    tmp_path: Path,
) -> None:
    """Bulk push preserves local relative layout under remote mission prefix."""
    source = tmp_path / "source"
    (source / "root.txt").parent.mkdir(parents=True, exist_ok=True)
    (source / "nested").mkdir(parents=True, exist_ok=True)
    (source / "root.txt").write_text("root", encoding="utf-8")
    (source / "nested" / "leaf.txt").write_text("leaf", encoding="utf-8")

    with patch.object(connector, "upload_file") as upload_mock:
        uploaded = connector.sync_up(source, "adapters/phi3-medium/track-a")

    assert uploaded == [
        "adapters/phi3-medium/track-a/nested/leaf.txt",
        "adapters/phi3-medium/track-a/root.txt",
    ]
    upload_mock.assert_has_calls(
        [
            call(source / "nested" / "leaf.txt", "adapters/phi3-medium/track-a/nested/leaf.txt"),
            call(source / "root.txt", "adapters/phi3-medium/track-a/root.txt"),
        ]
    )


def test_file_exists_returns_true_on_head_success(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """Positive head lookup confirms object readiness for downstream pulls."""
    _client(mocked_client).head_object.return_value = {"Metadata": {}}

    assert connector.file_exists("base-weights/phi3-medium/weights.gguf") is True


def test_file_exists_returns_false_for_missing_object(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """NotFound/404 response is treated as absent object, not hard failure."""
    _client(mocked_client).head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "not found"}},
        "HeadObject",
    )

    assert connector.file_exists("base-weights/missing.gguf") is False
    assert _client(mocked_client).head_object.call_count == 1


def test_file_exists_raises_for_repeated_non_404_errors(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """Persistent non-404 failures bubble up with connector context."""
    _client(mocked_client).head_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "backend failure"}},
        "HeadObject",
    )

    with pytest.raises(ObjectStorageOperationError, match="file_exists"):
        connector.file_exists("base-weights/phi3-medium/weights.gguf")


def test_delete_file_invokes_delete_object(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """Deletion call routes directly to object store key removal operation."""
    connector.delete_file("grok-verdicts/rejected/sample.json")

    _client(mocked_client).delete_object.assert_called_once_with(
        Bucket="unit-test-vault",
        Key="grok-verdicts/rejected/sample.json",
    )

"""Tests for S3-compatible object storage connector mission-storage operations."""

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
        region_name="auto",
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


def test_from_config_defaults_region_to_auto(mocked_client: tuple[MagicMock, MagicMock]) -> None:
    """Config bootstrap falls back to provider-agnostic S3 auto region."""
    ObjectStorageConnector.from_config(
        {
            "object_storage": {
                "access_key": "cfg-key",
                "secret_key": "cfg-secret",
                "endpoint": "https://cfg.objectstorage.test",
            }
        }
    )

    _client_factory(mocked_client).assert_called_once_with(
        "s3",
        endpoint_url="https://cfg.objectstorage.test",
        aws_access_key_id="cfg-key",
        aws_secret_access_key="cfg-secret",
        region_name="auto",
    )


def test_for_cloudflare_r2_uses_account_and_r2_env_credentials(
    monkeypatch: pytest.MonkeyPatch,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """R2 factory assembles endpoint and credentials for zero-egress transfer lane."""
    monkeypatch.setenv("S3M_CF_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("S3M_R2_ACCESS_KEY_ID", "r2-key")
    monkeypatch.setenv("S3M_R2_SECRET_ACCESS_KEY", "r2-secret")

    connector = ObjectStorageConnector.for_cloudflare_r2(bucket_name="r2-vault")

    assert connector.bucket_name == "r2-vault"
    _client_factory(mocked_client).assert_called_once_with(
        "s3",
        endpoint_url="https://acct-123.r2.cloudflarestorage.com",
        aws_access_key_id="r2-key",
        aws_secret_access_key="r2-secret",
        region_name="auto",
    )


def test_for_cloudflare_r2_requires_account_id(
    monkeypatch: pytest.MonkeyPatch,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """Factory fails fast when the Cloudflare account identifier is missing."""
    monkeypatch.delenv("S3M_CF_ACCOUNT_ID", raising=False)

    with pytest.raises(ObjectStorageConfigError, match="S3M_CF_ACCOUNT_ID"):
        ObjectStorageConnector.for_cloudflare_r2()

    _client_factory(mocked_client).assert_not_called()


def test_generate_presigned_url_delegates_to_client(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
) -> None:
    """Presign requests are delegated with normalized key and expiry semantics."""
    _client(mocked_client).generate_presigned_url.return_value = "https://signed.example/object"

    url = connector.generate_presigned_url("/models/phi3.gguf", expires_in=900)

    assert url == "https://signed.example/object"
    _client(mocked_client).generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "unit-test-vault", "Key": "models/phi3.gguf"},
        ExpiresIn=900,
    )


def test_generate_presigned_url_in_emulation_returns_file_url(tmp_path: Path) -> None:
    """Emulation mode returns deterministic file URL without boto3 dependency."""
    connector = ObjectStorageConnector(emulation_root=tmp_path)

    url = connector.generate_presigned_url("models/phi3.gguf")

    assert url == f"file://{(tmp_path / 'models' / 'phi3.gguf').resolve()}"


def test_multipart_upload_sends_parts_and_completes(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    """Multipart transfer chunks large payloads and finalizes manifest cleanly."""
    source = tmp_path / "model.bin"
    source.write_bytes(b"a" * ((1024 * 1024) + 10))
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    client = _client(mocked_client)
    client.create_multipart_upload.return_value = {"UploadId": "upload-1"}
    client.upload_part.side_effect = [{"ETag": "etag-1"}, {"ETag": "etag-2"}]

    result = connector.multipart_upload(source, "weights/model.bin", part_size_mb=1)

    client.create_multipart_upload.assert_called_once_with(
        Bucket="unit-test-vault",
        Key="weights/model.bin",
        Metadata={"sha256": checksum},
    )
    assert client.upload_part.call_count == 2
    client.complete_multipart_upload.assert_called_once_with(
        Bucket="unit-test-vault",
        Key="weights/model.bin",
        UploadId="upload-1",
        MultipartUpload={"Parts": [{"PartNumber": 1, "ETag": "etag-1"}, {"PartNumber": 2, "ETag": "etag-2"}]},
    )
    client.abort_multipart_upload.assert_not_called()
    assert result["remote_key"] == "weights/model.bin"
    assert result["etag"] == checksum
    assert result["parts"] == 2
    assert result["size_bytes"] == source.stat().st_size


def test_multipart_upload_aborts_on_part_failure(
    connector: ObjectStorageConnector,
    mocked_client: tuple[MagicMock, MagicMock],
    tmp_path: Path,
) -> None:
    """Upload failures abort multipart session to avoid orphaned server state."""
    source = tmp_path / "model.bin"
    source.write_bytes(b"critical-data")
    client = _client(mocked_client)
    client.create_multipart_upload.return_value = {"UploadId": "upload-2"}
    client.upload_part.side_effect = RuntimeError("network drop")

    with pytest.raises(RuntimeError, match="network drop"):
        connector.multipart_upload(source, "weights/model.bin", part_size_mb=1)

    client.abort_multipart_upload.assert_called_once_with(
        Bucket="unit-test-vault",
        Key="weights/model.bin",
        UploadId="upload-2",
    )


def test_multipart_upload_in_emulation_delegates_to_upload_file(tmp_path: Path) -> None:
    """Emulated multipart path reuses standard upload behavior for local vault simulation."""
    connector = ObjectStorageConnector(emulation_root=tmp_path)
    source = tmp_path / "input.bin"
    source.write_bytes(b"payload")

    with patch.object(connector, "upload_file", return_value={"remote_key": "weights/input.bin"}) as upload_mock:
        result = connector.multipart_upload(source, "weights/input.bin")

    upload_mock.assert_called_once_with(source, "weights/input.bin")
    assert result["remote_key"] == "weights/input.bin"

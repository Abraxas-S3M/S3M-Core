from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from src.storage.b2_connector import B2Connector, ClientError


class _FakePaginator:
    def __init__(self, client: "_FakeS3Client") -> None:
        self._client = client

    def paginate(self, *, Bucket: str, Prefix: str):  # noqa: N803 - boto compatibility
        _ = Bucket
        contents = []
        for key, row in self._client.objects.items():
            if key.startswith(Prefix):
                contents.append({"Key": key, "Size": len(row["Body"])})
        yield {"Contents": contents}


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.fail_upload_attempts = 0
        self.upload_attempts = 0

    def upload_file(self, Filename: str, Bucket: str, Key: str, ExtraArgs: dict[str, Any] | None = None) -> None:  # noqa: N803
        _ = Bucket
        self.upload_attempts += 1
        if self.fail_upload_attempts > 0:
            self.fail_upload_attempts -= 1
            raise OSError("transient write failure")
        data = Path(Filename).read_bytes()
        metadata = dict((ExtraArgs or {}).get("Metadata", {}))
        self.objects[Key] = {"Body": data, "Metadata": metadata}

    def put_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
        Body: bytes,  # noqa: N803
        ContentType: str,  # noqa: N803
        Metadata: dict[str, Any],  # noqa: N803
    ) -> dict[str, str]:
        _ = Bucket, ContentType
        self.objects[Key] = {"Body": bytes(Body), "Metadata": dict(Metadata)}
        etag = hashlib.md5(Body).hexdigest()
        return {"ETag": f'"{etag}"'}

    def download_file(self, *, Bucket: str, Key: str, Filename: str) -> None:  # noqa: N803
        _ = Bucket
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not found"}}, "GetObject")
        Path(Filename).parent.mkdir(parents=True, exist_ok=True)
        Path(Filename).write_bytes(self.objects[Key]["Body"])

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        _ = Bucket
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not found"}}, "HeadObject")
        body = bytes(self.objects[Key]["Body"])
        etag = hashlib.md5(body).hexdigest()
        return {
            "ContentLength": len(body),
            "Metadata": dict(self.objects[Key]["Metadata"]),
            "ETag": f'"{etag}"',
        }

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        _ = Bucket
        self.objects.pop(Key, None)

    def get_paginator(self, operation_name: str) -> _FakePaginator:
        assert operation_name == "list_objects_v2"
        return _FakePaginator(self)


def _connector(client: _FakeS3Client) -> B2Connector:
    return B2Connector(
        key_id="key",
        app_key="secret",
        bucket_name="s3m-vault",
        endpoint="https://example.invalid",
        client=client,
        max_retries=3,
    )


def test_upload_file_sets_sha256_and_supports_lookup(tmp_path: Path) -> None:
    client = _FakeS3Client()
    connector = _connector(client)
    local_file = tmp_path / "artifact.bin"
    local_file.write_bytes(b"s3m-test-payload")

    result = connector.upload_file(local_file, "models/fp16/phi3-medium/artifact.bin")

    expected_sha = hashlib.sha256(b"s3m-test-payload").hexdigest()
    assert result["sha256"] == expected_sha
    assert connector.get_file_sha256("models/fp16/phi3-medium/artifact.bin") == expected_sha
    assert connector.get_file_size("models/fp16/phi3-medium/artifact.bin") == len(b"s3m-test-payload")


def test_sync_up_and_sync_down_with_exclusions(tmp_path: Path) -> None:
    client = _FakeS3Client()
    connector = _connector(client)

    source = tmp_path / "src"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "keep.txt").write_text("keep", encoding="utf-8")
    (source / "nested" / "skip.tmp").write_text("skip", encoding="utf-8")

    push_stats = connector.sync_up(source, "datasets/nato/scenarios")
    assert push_stats["uploaded"] == 2

    destination = tmp_path / "dst"
    pull_stats = connector.sync_down(
        "datasets/nato/scenarios",
        destination,
        exclude_patterns=["*.tmp"],
    )

    assert pull_stats["downloaded"] == 1
    assert pull_stats["skipped"] == 1
    assert (destination / "nested" / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (destination / "nested" / "skip.tmp").exists()


def test_delete_and_exists_round_trip(tmp_path: Path) -> None:
    client = _FakeS3Client()
    connector = _connector(client)
    test_file = tmp_path / "item.txt"
    test_file.write_text("payload", encoding="utf-8")

    connector.upload_file(test_file, "gui-snapshots/item.txt")
    assert connector.file_exists("gui-snapshots/item.txt") is True

    connector.delete_file("gui-snapshots/item.txt")
    assert connector.file_exists("gui-snapshots/item.txt") is False


def test_upload_retries_transient_failures(tmp_path: Path) -> None:
    client = _FakeS3Client()
    client.fail_upload_attempts = 1
    connector = _connector(client)
    artifact = tmp_path / "retry.bin"
    artifact.write_bytes(b"retry")

    connector.upload_file(artifact, "models/fp16/mistral-7b/retry.bin")
    assert client.upload_attempts == 2

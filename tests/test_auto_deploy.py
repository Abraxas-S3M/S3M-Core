"""Unit tests for authenticated S3M auto-deploy webhook handling."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from scripts.auto_deploy import create_app


def _sign(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_rejects_invalid_signature(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "deploy.log"
    app = create_app(repo_path="/tmp/nonexistent", log_path=str(log_path))
    monkeypatch.setenv("S3M_WEBHOOK_SECRET", "test-secret")

    payload = {"ref": "refs/heads/main"}
    payload_bytes = json.dumps(payload).encode("utf-8")

    with app.test_client() as client:
        response = client.post(
            "/github-webhook",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=bad",
            },
        )

    assert response.status_code == 403
    assert response.get_json() == {"status": "error", "message": "Invalid signature"}


def test_push_to_main_triggers_deploy(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "deploy.log"
    app = create_app(repo_path="/opt/s3m", log_path=str(log_path))
    monkeypatch.setenv("S3M_WEBHOOK_SECRET", "test-secret")

    call_record: dict[str, Any] = {}

    class Completed:
        returncode = 0
        stdout = "Already up to date."
        stderr = ""

    def fake_run(cmd, cwd, capture_output, text, check):  # type: ignore[no-untyped-def]
        call_record["cmd"] = cmd
        call_record["cwd"] = cwd
        call_record["capture_output"] = capture_output
        call_record["text"] = text
        call_record["check"] = check
        return Completed()

    monkeypatch.setattr("scripts.auto_deploy.subprocess.run", fake_run)

    payload = {"ref": "refs/heads/main"}
    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = _sign("test-secret", payload_bytes)

    with app.test_client() as client:
        response = client.post(
            "/github-webhook",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": signature,
            },
        )

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "message": "Deployment triggered"}
    assert call_record == {
        "cmd": ["git", "pull", "origin", "main"],
        "cwd": "/opt/s3m",
        "capture_output": True,
        "text": True,
        "check": False,
    }


def test_non_main_push_is_accepted_without_deploy(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "deploy.log"
    app = create_app(repo_path="/opt/s3m", log_path=str(log_path))
    monkeypatch.setenv("S3M_WEBHOOK_SECRET", "test-secret")

    def should_not_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Deployment command must not run for non-main refs")

    monkeypatch.setattr("scripts.auto_deploy.subprocess.run", should_not_run)

    payload = {"ref": "refs/heads/feature"}
    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = _sign("test-secret", payload_bytes)

    with app.test_client() as client:
        response = client.post(
            "/github-webhook",
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": signature,
            },
        )

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "message": "Webhook received"}

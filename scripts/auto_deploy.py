#!/usr/bin/env python3
"""Authenticated webhook listener for controlled battlefield software updates."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
from typing import Any

from flask import Flask, jsonify, request

REPO_PATH = "/opt/s3m"
LOG_PATH = "/opt/s3m/logs/deploy.log"
MAIN_BRANCH_REF = "refs/heads/main"


def _configure_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger("s3m_autodeploy")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handler = logging.FileHandler(log_path)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def _signature_for_payload(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _verify_signature(payload: bytes, provided_signature: str | None, secret: str) -> bool:
    if not provided_signature:
        return False
    expected_signature = _signature_for_payload(secret, payload)
    return hmac.compare_digest(expected_signature, provided_signature)


def create_app(repo_path: str = REPO_PATH, log_path: str = LOG_PATH) -> Flask:
    app = Flask(__name__)
    logger = _configure_logger(log_path)

    @app.post("/github-webhook")
    def github_webhook() -> tuple[Any, int]:
        secret = os.getenv("S3M_WEBHOOK_SECRET")
        if not secret:
            logger.error("S3M_WEBHOOK_SECRET is not configured.")
            return jsonify({"status": "error", "message": "Webhook secret is not configured"}), 500

        payload = request.get_data(cache=False)
        signature = request.headers.get("X-Hub-Signature-256")
        event_type = request.headers.get("X-GitHub-Event", "unknown")

        if not _verify_signature(payload, signature, secret):
            logger.warning("Rejected webhook: signature verification failed for event=%s", event_type)
            return jsonify({"status": "error", "message": "Invalid signature"}), 403

        try:
            payload_json = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning("Rejected webhook: invalid JSON payload for event=%s", event_type)
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        ref = str(payload_json.get("ref", ""))
        logger.info("Accepted webhook event=%s ref=%s", event_type, ref)

        if event_type == "push" and ref == MAIN_BRANCH_REF:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.stdout:
                logger.info("git pull stdout: %s", result.stdout.strip())
            if result.stderr:
                logger.info("git pull stderr: %s", result.stderr.strip())

            if result.returncode != 0:
                logger.error("Deployment command failed with exit code %s", result.returncode)
                return jsonify({"status": "error", "message": "Deployment failed"}), 500

            logger.info("Deployment command completed successfully.")
            return jsonify({"status": "ok", "message": "Deployment triggered"}), 200

        logger.info("No deployment action required for event=%s ref=%s", event_type, ref)
        return jsonify({"status": "ok", "message": "Webhook received"}), 200

    return app


def main() -> None:
    app = create_app()
    app.run(host="0.0.0.0", port=9090)


if __name__ == "__main__":
    main()

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from integration_sdk.base.provider_adapter import OperatingMode
from integration_sdk.errors.integration_errors import AirgapViolationError, ProviderFetchError
from integration_sdk.http.resilient_client import ResilientHTTPClient


class FlakyHandler(BaseHTTPRequestHandler):
    failure_limit = 3
    calls = 0

    def do_GET(self):
        FlakyHandler.calls += 1
        if FlakyHandler.calls <= FlakyHandler.failure_limit:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "temporary"}).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))

    def log_message(self, format, *args):
        return


@pytest.fixture()
def flaky_server():
    FlakyHandler.calls = 0
    server = HTTPServer(("127.0.0.1", 0), FlakyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=1)


def test_resilient_client_retries_then_succeeds(flaky_server, monkeypatch):
    monkeypatch.setattr("integration_sdk.http.resilient_client.time.sleep", lambda _: None)
    client = ResilientHTTPClient(provider_id="mock", max_retries=3)
    response = client.request("GET", flaky_server)
    assert response["status_code"] == 200
    assert FlakyHandler.calls == 4


def test_resilient_client_airgapped_blocks():
    client = ResilientHTTPClient(provider_id="mock", mode=OperatingMode.AIRGAPPED)
    with pytest.raises(AirgapViolationError):
        client.request("GET", "http://127.0.0.1")

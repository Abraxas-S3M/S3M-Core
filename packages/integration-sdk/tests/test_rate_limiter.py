import threading
import time

from integration_sdk.http.rate_limiter import RateLimiter


def test_rate_limiter_acquire_exhaustion():
    limiter = RateLimiter(rpm=10)
    for _ in range(10):
        assert limiter.acquire() is True
    assert limiter.acquire() is False


def test_rate_limiter_wait_blocks_until_refill(monkeypatch):
    limiter = RateLimiter(rpm=10)
    for _ in range(10):
        assert limiter.acquire() is True

    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        limiter._tokens = 1.0

    monkeypatch.setattr("integration_sdk.http.rate_limiter.time.sleep", fake_sleep)
    limiter.wait()
    assert sleep_calls

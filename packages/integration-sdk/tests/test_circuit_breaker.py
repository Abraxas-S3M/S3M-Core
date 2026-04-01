import time

from integration_sdk.http.circuit_breaker import CircuitBreaker


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout_seconds=0.1)
    for _ in range(5):
        breaker.record_failure()
    assert breaker.get_state() == "open"
    assert breaker.allow_request() is False

    time.sleep(0.11)
    assert breaker.allow_request() is True
    assert breaker.get_state() == "half_open"


def test_circuit_breaker_recovers_on_success():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.0)
    breaker.record_failure()
    assert breaker.get_state() == "open"
    assert breaker.allow_request() is True
    breaker.record_success()
    assert breaker.get_state() == "closed"

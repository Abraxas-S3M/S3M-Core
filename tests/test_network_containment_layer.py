from __future__ import annotations

from datetime import datetime, timedelta, timezone

from s3m_core.defense.network import (
    DNSGuard,
    DNSQuery,
    EgressProxy,
    NetworkPolicy,
    NetworkPolicyEngine,
    NetworkRequest,
    TrafficAnalyzer,
    TrafficEntry,
)


def _base_policy() -> NetworkPolicy:
    return NetworkPolicy(
        allowed_domains=["github.com", "s3m.local"],
        allowed_ips=["10.0.0.0/8"],
        allowed_ports=[80, 443, 53],
        blocked_domains=["pastebin.com"],
        blocked_services=["gist.github.com"],
    )


def test_policy_engine_denies_explicitly_blocked_domain() -> None:
    engine = NetworkPolicyEngine(default_policy=_base_policy())
    request = NetworkRequest(
        destination_host="pastebin.com",
        destination_port=443,
        protocol="https",
        method="POST",
        path="/api",
        body_size=128,
        content_type="application/json",
        body_preview='{"msg":"hello"}',
        session_id="session-a",
    )

    decision = engine.evaluate_request(request)
    assert decision.allowed is False
    assert "explicitly blocked" in decision.reason


def test_policy_engine_flags_and_blocks_credential_patterns() -> None:
    engine = NetworkPolicyEngine(default_policy=_base_policy())
    request = NetworkRequest(
        destination_host="github.com",
        destination_port=443,
        protocol="https",
        method="POST",
        path="/upload",
        body_size=256,
        content_type="text/plain",
        body_preview='api_key="SECRET-KEY-123456"',
        session_id="session-b",
    )

    decision = engine.evaluate_request(request)
    assert decision.allowed is False
    assert "credential" in decision.content_flags


def test_policy_engine_enforces_requests_per_minute() -> None:
    policy = NetworkPolicy(
        allowed_domains=["s3m.local"],
        allowed_ips=[],
        allowed_ports=[443],
        blocked_domains=[],
        blocked_services=[],
        max_requests_per_minute=2,
    )
    engine = NetworkPolicyEngine(default_policy=policy)

    base_request = NetworkRequest(
        destination_host="api.s3m.local",
        destination_port=443,
        protocol="https",
        method="GET",
        path="/status",
        body_size=0,
        content_type="application/json",
        body_preview="",
        session_id="session-c",
    )

    assert engine.evaluate_request(base_request).allowed is True
    assert engine.evaluate_request(base_request).allowed is True
    denied = engine.evaluate_request(base_request)
    assert denied.allowed is False
    assert "exceeded" in denied.reason


def test_policy_engine_generates_container_rule_plan() -> None:
    engine = NetworkPolicyEngine(default_policy=_base_policy())
    engine.apply_to_container("agent-101")
    commands = engine.get_container_rule_plan("agent-101")

    assert commands
    assert any("--dport 443" in command for command in commands)
    assert commands[0].endswith("iptables -P OUTPUT DROP")


def test_egress_proxy_blocks_internal_data_and_logs_alert() -> None:
    engine = NetworkPolicyEngine(default_policy=_base_policy())
    proxy = EgressProxy(policy_engine=engine, listen_port=8443, tls_intercept=True)
    request = NetworkRequest(
        destination_host="github.com",
        destination_port=443,
        protocol="https",
        method="POST",
        path="/repo",
        body_size=1024,
        content_type="text/plain",
        body_preview="CONFIDENTIAL mission plan for sector bravo.",
        session_id="ignored-by-proxy",
    )

    response = proxy.handle_request("session-d", request)
    assert response["status_code"] == 403
    assert response["blocked"] is True
    assert "x-s3m-deny-reason" in response["headers"]

    session_log = proxy.get_traffic_log("session-d")
    assert len(session_log) == 1
    assert session_log[0].blocked is True
    assert "internal_data" in session_log[0].content_flags

    alerts = proxy.get_exfiltration_alerts()
    assert alerts
    assert any(alert.data_type == "internal_data" for alert in alerts)


def test_dns_guard_resolves_allowlist_and_blocks_others() -> None:
    guard = DNSGuard(allowed_domains=["s3m.local"])
    guard.start(listen_port=5353)

    allowed = guard.resolve_query("session-e", "api.s3m.local", "A")
    blocked = guard.resolve_query("session-e", "example.org", "A")

    assert allowed.resolved is True
    assert allowed.response_ip.startswith("198.18.")
    assert blocked.resolved is False
    assert blocked.response_ip == ""
    assert len(guard.get_query_log()) == 2


def test_dns_guard_detects_tunneling_pattern() -> None:
    guard = DNSGuard(allowed_domains=["s3m.local"])
    guard.start()

    for _ in range(26):
        guard.resolve_query(
            "session-f",
            "a9f4c20e11d4aa2be091c9ff8be6f2aa112233445566778899.api.s3m.local",
            "TXT",
        )

    assert guard.detect_tunneling("session-f") is True


def test_traffic_analyzer_marks_critical_risk_for_exfil_indicators() -> None:
    analyzer = TrafficAnalyzer()
    now = datetime.now(timezone.utc)
    traffic_log = [
        TrafficEntry(
            timestamp=now.isoformat(),
            session_id="session-g",
            method="POST",
            url="https://exfil.example.net:443/upload",
            request_size=900_000,
            response_code=403,
            blocked=True,
            block_reason="Blocked: outbound content appears to contain credentials.",
            content_flags=["credential"],
        ),
        TrafficEntry(
            timestamp=(now + timedelta(seconds=20)).isoformat(),
            session_id="session-g",
            method="POST",
            url="https://exfil.example.net:443/upload",
            request_size=1_500_000,
            response_code=403,
            blocked=True,
            block_reason="Blocked: outbound content appears to contain source code.",
            content_flags=["source_code"],
        ),
    ]
    dns_log = [
        DNSQuery(
            timestamp=(now + timedelta(seconds=5)).isoformat(),
            session_id="session-g",
            query_name="f0f1f2f3f4f5f6f7f8f9fa0b0c0d0e0f1a2b3c4d5e6f.exfil.example.net",
            query_type="TXT",
            resolved=False,
            response_ip="",
            tunnel_score=0.91,
        )
    ]

    assessment = analyzer.analyze_session("session-g", traffic_log, dns_log)
    indicator_types = {indicator.type for indicator in assessment.indicators}

    assert assessment.risk_level == "critical"
    assert "credential_exfiltration" in indicator_types
    assert "dns_tunneling" in indicator_types

from src.cortex.xiid_write_envelope import WriteEnvelope


def test_write_envelope_issue_and_verify() -> None:
    key = b"test-signing-key-32-bytes-long!!!"
    envelope = WriteEnvelope.issue(
        operator_id="op-1",
        session_id="sess-1",
        action="narrow_route",
        signing_key=key,
    )
    assert envelope.verify(key) is True
    assert envelope.verify(b"wrong-key") is False

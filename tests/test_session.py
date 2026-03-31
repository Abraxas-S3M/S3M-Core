"""Tests for S3M Session Manager"""

import sys
sys.path.insert(0, ".")

from src.llm_core.session import S3MSession


def test_session_creation():
    session = S3MSession()
    assert session.pool is not None
    assert len(session.query_log) == 0
    print("PASS: Session creates successfully")


def test_session_status():
    session = S3MSession()
    status = session.status()
    assert status["total_engines"] == 4
    assert status["total_queries"] == 0
    print("PASS: Session status correct")


def test_session_query_without_models():
    session = S3MSession()
    result = session.query("test tactical query")
    assert result is not None
    assert len(session.query_log) == 1
    print("PASS: Session handles query without loaded models")


def test_session_shutdown():
    session = S3MSession()
    session.shutdown()
    status = session.status()
    assert status["loaded"] == 0
    print("PASS: Session shutdown works")


if __name__ == "__main__":
    test_session_creation()
    test_session_status()
    test_session_query_without_models()
    test_session_shutdown()
    print("\nAll session tests passed")

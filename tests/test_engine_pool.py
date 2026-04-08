"""Tests for S3M Engine Pool"""

import sys
sys.path.insert(0, ".")

from src.llm_core.engine_pool import EnginePool
from src.llm_core.engine_registry import EngineID, TaskDomain


def test_pool_initialization():
    pool = EnginePool()
    assert len(pool.engines) == 4
    print("PASS: Pool creates all 4 engine slots")


def test_pool_status():
    pool = EnginePool()
    status = pool.pool_status()
    assert status["total_engines"] == 4
    assert status["loaded"] == 0
    assert len(status["engines"]) == 4
    print("PASS: Pool status reports correctly")


def test_domain_classification():
    pool = EnginePool()
    assert pool._classify("enemy position at grid 123") == TaskDomain.TACTICAL
    assert pool._classify("analyze the strategic implications") == TaskDomain.REASONING
    assert pool._classify("generate a logistics plan") == TaskDomain.PLANNING
    assert pool._classify("translate this arabic document") == TaskDomain.ARABIC_NLP
    print("PASS: Pool domain classification works")


def test_query_unloaded_engine():
    pool = EnginePool()
    result = pool.query_engine(EngineID.PHI3_MEDIUM, "test query")
    assert "[ERROR]" in result.response
    print("PASS: Unloaded engine returns error gracefully")


if __name__ == "__main__":
    test_pool_initialization()
    test_pool_status()
    test_domain_classification()
    test_query_unloaded_engine()
    print("\nAll engine pool tests passed")

"""Tests for S3M Orchestrator"""

import sys
sys.path.insert(0, ".")

from src.llm_core.orchestrator import Orchestrator, QueryRequest
from src.llm_core.engine_registry import TaskDomain


def test_domain_classification():
    orch = Orchestrator()
    assert orch.classify_domain("enemy position at grid 123") == TaskDomain.TACTICAL
    assert orch.classify_domain("analyze the threat implications") == TaskDomain.REASONING
    assert orch.classify_domain("generate a logistics plan") == TaskDomain.PLANNING
    assert orch.classify_domain("translate this arabic text") == TaskDomain.ARABIC_NLP
    print("PASS: Domain classification works")


def test_single_query():
    orch = Orchestrator()
    request = QueryRequest(prompt="report enemy contact at sector 7")
    response = orch.execute_single(request)
    assert response.engine_id.value == "phi3-mini"
    print("PASS: Single query routing works")


def test_consensus_query():
    orch = Orchestrator()
    request = QueryRequest(prompt="full threat assessment", require_consensus=True)
    result = orch.execute_consensus(request)
    assert len(result.responses) == 4
    print("PASS: Consensus query hits all 4 engines")


if __name__ == "__main__":
    test_domain_classification()
    test_single_query()
    test_consensus_query()
    print("\nAll orchestrator tests passed")

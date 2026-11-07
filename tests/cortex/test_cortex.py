#!/usr/bin/env python3
"""Regression tests for Cortex reachability fixtures."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.cortex.fixtures import cctv_reachability_graph
from src.cortex.reachability import plan_mrc


def test_cctv_fixture_baseline_risk():
    graph = cctv_reachability_graph()
    assert graph.system_risk() == pytest.approx(0.307, abs=0.01)


def test_cctv_fixture_mrc_reduces_risk():
    graph = cctv_reachability_graph()
    plan = plan_mrc(graph, budget=1.0)
    assert plan.initial_risk == pytest.approx(0.307, abs=0.01)
    assert plan.final_risk == pytest.approx(0.022, abs=0.01)
    assert plan.required_flows_ok

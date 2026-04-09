"""LLM_ROS2 HMI integration adapter for S3M."""

from __future__ import annotations

import importlib

LlmRos2Adapter = importlib.import_module("packages.integrations.hmi.llm-ros2.adapter").LlmRos2Adapter

__all__ = ["LlmRos2Adapter"]

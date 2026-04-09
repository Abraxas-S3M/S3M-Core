"""ROS Voice Assistant HMI integration adapter for S3M."""

from __future__ import annotations

import importlib

RosVoiceAssistantAdapter = importlib.import_module(
    "packages.integrations.hmi.ros-voice-assistant.adapter"
).RosVoiceAssistantAdapter

__all__ = ["RosVoiceAssistantAdapter"]

#!/usr/bin/env python3
"""S3M Phase 13 cyber training demonstration script."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cyber.training import CyberTrainingManager


def main() -> None:
    manager = CyberTrainingManager()
    print("=" * 70)
    print("S3M PHASE 13 CYBER TRAINING DEMO")
    print("=" * 70)
    print()

    for scenario in manager.list_exercise_types():
        exercise = manager.create_exercise(scenario)
        events = exercise["events"]
        scorecard = manager.run_exercise(events)
        print(f"[{scenario}]")
        print(f"  Event count: {len(events)}")
        print(f"  Cases created: {scorecard['cases_created']}")
        print(f"  Playbooks triggered: {scorecard['playbooks_triggered']}")
        print(f"  Case creation rate: {scorecard['cases_created'] / max(1, len(events)):.3f}")
        print()

    history = manager.get_exercise_history()
    if history:
        sample = history[0]
        evaluation = manager.evaluate_response(sample["exercise_id"])
        print("Sample scorecard:")
        print(f"  Exercise ID: {sample['exercise_id']}")
        print(f"  Events processed: {sample['events_processed']}")
        print(f"  Cases created: {sample['cases_created']}")
        print(f"  Playbooks triggered: {sample['playbooks_triggered']}")
        print("Recommendations:")
        print(f"  {evaluation['recommendations']}")


if __name__ == "__main__":
    main()

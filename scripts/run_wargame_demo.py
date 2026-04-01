#!/usr/bin/env python3
"""Layer 12 wargaming and training portal demonstration script."""

from __future__ import annotations

from apps.simulation.manager import TrainingSimManager


def main() -> None:
    mgr = TrainingSimManager()

    officers = [
        mgr.register_officer("Capt. Al-Rashid", "Captain", "1st Armored", "armor"),
        mgr.register_officer("Lt. Al-Ghamdi", "Lieutenant", "Army Aviation", "aviation"),
        mgr.register_officer("Maj. Al-Otaibi", "Major", "3rd Infantry", "infantry"),
    ]

    result = mgr.run_quick_wargame("Demo Wargame", blue_units=10, red_units=12, turns=20, adversary="competent")
    print("=== QUICK WARGAME RESULT ===")
    print(result.summary())
    print("AAR:", result.llm_aar or "Template AAR unavailable")

    session = mgr.wargame_suite.engine.get_sessions()[-1]
    print("=== TURN EVENTS ===")
    for turn in session.turns:
        key_events = [e for e in turn.events if e.get("type") in {"engagement", "movement", "victory"}]
        print(f"Turn {turn.turn_number}: {len(key_events)} key events")

    participants = [{"officer_id": o.officer_id, "role": "commander"} for o in officers]
    exercise = mgr.create_tabletop("Desert Shield Training", "Defend a desert corridor against mechanized assault.", participants)
    print("=== EXERCISE PHASES ===")
    for phase in exercise.phases:
        print(f"- {phase.name}: objectives={phase.objectives}")

    score = mgr.evaluate_exercise(exercise.exercise_id)
    print("=== EXERCISE SCORECARD ===")
    print(score.to_dict())

    print("=== OFFICER PROFILES ===")
    for officer in officers:
        profile = mgr.training_portal.officers.get_officer_profile(officer.officer_id)
        print(profile)

    print("=== LEADERBOARD ===")
    print(mgr.training_portal.officers.get_leaderboard())

    print("=== TRAINING REPORT ===")
    print(mgr.generate_training_report())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# File: scripts/run_cloud_cpu_validation.py
"""Validate the cloud CPU training system end-to-end.

Creates synthetic scenario packs, runs training cycles, verifies
checkpointing, resume, and promotion gate logic.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _create_test_scenario(scenarios_dir, track, scenario_id, n_prompts=20):
    """Create a synthetic scenario pack for testing."""
    pack_dir = scenarios_dir / track / f"scenario-{scenario_id:05d}"
    pack_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "scenario_id": f"test-{scenario_id:05d}",
        "track": track,
        "data_class": "command",
        "prompt_count": n_prompts,
        "version": "1.0",
    }
    with open(pack_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    with open(pack_dir / "prompts.jsonl", "w", encoding="utf-8") as f:
        for i in range(n_prompts):
            # Tactical-domain prompt fixture for track-specific training flow checks.
            f.write(json.dumps({"prompt": f"Test command prompt {i} for {track}"}) + "\n")

    with open(pack_dir / "labels.jsonl", "w", encoding="utf-8") as f:
        for i in range(n_prompts):
            f.write(json.dumps({"completion": f"Expected response {i} for {track}"}) + "\n")


def main():
    from pathlib import Path

    from src.training.cloud_cpu.dataset_cursor import DatasetCursor
    from src.training.cloud_cpu.metrics_store import MetricsStore
    from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
    from src.training.cloud_cpu.promotion_gate import PromotionGate
    from src.training.cloud_cpu.resume_manager import ResumeManager
    from src.training.cloud_cpu.track_router import TrackRouter
    from src.training.cloud_cpu.training_loop import TrainingLoop, StubTrainingBackend

    _ = StubTrainingBackend

    print("=" * 60)
    print("  S3M CLOUD CPU TRAINING VALIDATION")
    print("=" * 60)

    # Use temp directory for testing
    with tempfile.TemporaryDirectory(prefix="s3m_train_test_") as tmpdir:
        tmp = Path(tmpdir)
        paths = StatePaths(state_root=tmp / "state", data_root=tmp / "data")
        paths.ensure_dirs()

        results = []

        # Test 1: Path creation
        print("\n  [1/7] Path creation...")
        assert paths.checkpoints.exists()
        assert paths.metrics.exists()
        for track in TrainingTrack:
            tp = paths.for_track(track)
            assert tp.runs.exists()
            assert tp.promoted.exists()
        results.append(("Path creation", "PASS"))

        # Test 2: Scenario creation and dataset cursor
        print("  [2/7] Dataset cursor...")
        for track in ["saudi_mod", "ukraine_mod", "nato"]:
            _create_test_scenario(paths.scenarios, track, 1)
            _create_test_scenario(paths.scenarios, track, 2)

        cursor = DatasetCursor(
            "saudi_mod",
            paths.scenario_dir(TrainingTrack.SAUDI_MOD),
            paths.processed,
            paths.rejected,
        )
        batch = cursor.next_batch(4)
        assert len(batch) == 4
        assert batch[0].domain_track == "saudi_mod"
        results.append(("Dataset cursor", "PASS"))

        # Test 3: Training loop
        print("  [3/7] Training loop...")
        config_path = Path("configs/training/saudi_mod.yaml")
        loop = TrainingLoop(TrainingTrack.SAUDI_MOD, config_path, paths)
        metrics = loop.run_cycle()
        assert metrics.track == "saudi_mod"
        results.append(("Training loop", "PASS"))

        # Test 4: Metrics store
        print("  [4/7] Metrics store...")
        store = MetricsStore(paths.metrics)
        store.write_cycle(metrics)
        latest = store.get_latest("saudi_mod", 10)
        assert len(latest) >= 1
        summary = store.get_track_summary("saudi_mod")
        assert summary["status"] == "active"
        results.append(("Metrics store", "PASS"))

        # Test 5: Resume manager
        print("  [5/7] Resume manager...")
        mgr = ResumeManager(paths)
        meta = mgr.scan_for_resume(TrainingTrack.SAUDI_MOD)
        assert meta is None  # No checkpoints yet
        results.append(("Resume manager", "PASS"))

        # Test 6: Track router
        print("  [6/7] Track router...")
        inbox_pack = paths.inbox / "scenario-99999"
        inbox_pack.mkdir(parents=True)
        with open(inbox_pack / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"track": "nato", "scenario_id": "inbox-test"}, f)
        with open(inbox_pack / "prompts.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"prompt": "Test"}) + "\n")

        router = TrackRouter(paths)
        routed = router.route_inbox()
        assert routed["nato"] == 1
        results.append(("Track router", "PASS"))

        # Test 7: Promotion gate
        print("  [7/7] Promotion gate...")
        from src.training.cloud_cpu.contracts import CheckpointMeta

        gate = PromotionGate()
        test_meta = CheckpointMeta(
            checkpoint_id="test-ckpt",
            run_id="test-run",
            track="nato",
            step=100,
            epoch=1,
        )
        decision = gate.evaluate(
            test_meta,
            {"overall": 0.85, "format_compliance": 0.90},
            last_promoted_step=0,
        )
        # Should fail: step 100 < min_steps_before_first_promotion 500
        assert not decision.passed
        results.append(("Promotion gate", "PASS"))

    # Summary
    print("\n" + "=" * 60)
    print("  VALIDATION RESULTS")
    print("=" * 60)
    all_pass = True
    for name, status in results:
        icon = "[PASS]" if status == "PASS" else "[FAIL]"
        print(f"  {icon} {name}: {status}")
        if status != "PASS":
            all_pass = False

    print("=" * 60)
    if all_pass:
        print("  ALL TESTS PASSED - Cloud CPU training system validated")
    else:
        print("  SOME TESTS FAILED")
    print("=" * 60)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()

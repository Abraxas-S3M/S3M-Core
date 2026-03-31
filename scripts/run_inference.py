"""
S3M Quick Inference Runner
Usage: python scripts/run_inference.py
"""

import sys
sys.path.insert(0, ".")

from src.llm_core.session import S3MSession
from src.llm_core.engine_registry import EngineID


def main():
    print("=" * 60)
    print("S3M QUAD-ENGINE INFERENCE SYSTEM")
    print("=" * 60)

    session = S3MSession(n_gpu_layers=-1)

    print("\n--- System Status ---")
    status = session.status()
    print(f"Total engines: {status['total_engines']}")
    print(f"Loaded engines: {status['loaded']}")
    for name, info in status["engines"].items():
        available = "YES" if info["model_file_exists"] else "NO"
        loaded = "LOADED" if info["loaded"] else "NOT LOADED"
        print(f"  {name}: file={available} status={loaded}")

    print("\n--- Loading Available Engines ---")
    load_results = session.startup()
    for engine, success in load_results.items():
        status_text = "OK" if success else "SKIPPED"
        print(f"  {engine}: {status_text}")

    loaded_count = sum(1 for v in load_results.values() if v)
    if loaded_count == 0:
        print("\nNo models loaded. Download model weights first.")
        print("Use WeightManager to pull from HuggingFace and stage to models/ directory.")
        session.shutdown()
        return

    print(f"\n--- {loaded_count} Engine(s) Ready ---")

    test_queries = [
        ("Report enemy contact at grid 38SMB4012", "tactical"),
        ("Analyze the implications of increased patrol activity in sector 7", "reasoning"),
        ("Generate a 3-phase logistics plan for FOB resupply", "planning"),
    ]

    for prompt, domain in test_queries:
        print(f"\n[QUERY] ({domain}) {prompt}")
        result = session.query(prompt, domain=domain)
        print(f"[ENGINE] {result.model_name}")
        print(f"[RESPONSE] {result.response[:200]}")
        print(f"[STATS] {result.tokens_generated} tokens | {result.latency_ms:.0f}ms | {result.tokens_per_second:.1f} tok/s")

    if loaded_count >= 2:
        print("\n--- Consensus Query ---")
        results = session.consensus("Assess current threat level in AO THUNDER")
        for r in results:
            print(f"  [{r.model_name}] {r.response[:100]}...")

    session.shutdown()
    print("\nS3M Session complete.")


if __name__ == "__main__":
    main()

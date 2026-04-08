"""Verify all GUI Bridge endpoints are reachable and return valid shapes.

Usage:
    # Start server first:  uvicorn src.api.server:app --port 8080
    # Then run:  python scripts/verify_gui_bridge.py
"""

import json
import sys
import requests

BASE = "http://localhost:8080/api/v1"

CHECKS = [
    ("GET",  "/workspaces/command/operational-context", ["threats", "decisions", "directives"]),
    ("GET",  "/workspaces/command/timeline-events",     ["events"]),
    ("GET",  "/workspaces/cop/tracks",                  ["tracks"]),
    ("GET",  "/workspaces/cop/threat-tracks",           ["tracks"]),
    ("GET",  "/workspaces/decisions/queue",             ["decisions", "queueCounts"]),
    ("GET",  "/workspaces/risk/metrics",                ["composite", "domains", "forecast", "drivers"]),
    ("GET",  "/workspaces/readiness/summary",           ["personnel", "equipment", "unitStatus"]),
    ("GET",  "/workspaces/surveillance/assets",         ["assets", "taskingQueue", "targetBoard"]),
    ("GET",  "/workspaces/communication/messages",      ["inbox"]),
    ("GET",  "/workspaces/cyber/incidents",             ["incidents"]),
    ("GET",  "/workspaces/cyber/resilience",            ["resilience"]),
    ("GET",  "/workspaces/cyber/model-security",        ["modelSecurity", "updatedAt"]),
    ("GET",  "/workspaces/cyber/trust-fabric",          ["crypto", "zeroKnowledge", "updatedAt"]),
    ("GET",  "/workspaces/cyber/attack-capabilities",   ["capabilities", "updatedAt"]),
    ("POST", "/workspaces/cyber/attack/plan",           ["status", "plan", "updatedAt"]),
    ("POST", "/workspaces/cyber/attack/execute",        ["status", "execution", "updatedAt"]),
    ("GET",  "/workspaces/simulation/scenarios",        ["scenarios"]),
    ("GET",  "/workspaces/sustainment/fleet",           ["units"]),
    ("GET",  "/workspaces/sustainment/supply",          ["categories"]),
    ("GET",  "/workspaces/planning/phases",             ["phases"]),
    ("GET",  "/workspaces/planning/coas",               ["coursesOfAction"]),
    ("POST", "/auth/login",                             ["token", "user"]),
    ("POST", "/ai/chat",                                ["response", "engine"]),
]


def main():
    passed = 0
    failed = 0

    for method, path, required_keys in CHECKS:
        url = f"{BASE}{path}"
        try:
            if method == "GET":
                r = requests.get(url, timeout=10)
            else:
                if "login" in path:
                    r = requests.post(url, json={"username": "commander", "password": "s3m-cmd-2026"}, timeout=10)
                elif "chat" in path:
                    r = requests.post(url, json={"prompt": "Status report", "language": "EN"}, timeout=10)
                else:
                    r = requests.post(url, json={}, timeout=10)

            if r.status_code != 200:
                print(f"  FAIL  {method:4s} {path} → HTTP {r.status_code}")
                failed += 1
                continue

            data = r.json()
            missing = [k for k in required_keys if k not in data]
            if missing:
                print(f"  FAIL  {method:4s} {path} → missing keys: {missing}")
                failed += 1
            else:
                print(f"  PASS  {method:4s} {path}")
                passed += 1

        except requests.exceptions.ConnectionError:
            print(f"  FAIL  {method:4s} {path} → Connection refused (is server running?)")
            failed += 1
        except Exception as e:
            print(f"  FAIL  {method:4s} {path} → {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'='*60}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

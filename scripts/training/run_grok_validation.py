#!/usr/bin/env python3
"""Run the Grok validation oracle against pending training artifacts.

Military/tactical context:
This CLI is intended for scheduled quality-gate enforcement so only verified
adapters are promoted into sync paths consumed by operational nodes.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import asdict

from src.training.validation.grok_oracle import GrokValidationOracle

LOGGER = logging.getLogger("s3m.training.grok_oracle")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending Grok validation requests.")
    parser.add_argument(
        "--mode",
        default="offline",
        choices=["offline", "api"],
        help="Oracle mode: offline heuristic checks or xAI API-backed scoring.",
    )
    parser.add_argument(
        "--xai-key",
        default=None,
        help="xAI API key used only in --mode api.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate and print results without moving objects between lanes.",
    )
    parser.add_argument(
        "--track",
        default=None,
        help="Optional track filter (e.g., saudi_mod, nato, ukraine_mod).",
    )
    parser.add_argument(
        "--promote-approved",
        action="store_true",
        help="After verdict processing, copy approved adapters into live adapters/ path.",
    )
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def main() -> int:
    args = parse_args()
    configure_logging()

    oracle = GrokValidationOracle(mode=args.mode, xai_api_key=args.xai_key)
    pending = oracle.scan_pending()
    if args.track:
        pending = [request for request in pending if request.track == args.track]

    if not pending:
        LOGGER.info("No pending Grok validation requests found.")
        return 0

    verdicts = []
    for request in pending:
        verdict = oracle.evaluate_artifact(request)
        verdicts.append(verdict)
        LOGGER.info(
            "artifact_id=%s track=%s passed=%s score=%.3f reason=%s",
            request.artifact_id,
            request.track,
            verdict.passed,
            verdict.score,
            verdict.reason,
        )

        if args.dry_run:
            continue
        if verdict.passed:
            oracle.move_to_approved(request, verdict)
        else:
            oracle.move_to_rejected(request, verdict)

    if args.promote_approved and not args.dry_run:
        oracle.promote_approved_adapters()

    approved = sum(1 for verdict in verdicts if verdict.passed)
    rejected = len(verdicts) - approved
    LOGGER.info("Validation summary: approved=%d rejected=%d total=%d", approved, rejected, len(verdicts))

    if args.dry_run:
        print(
            "\n".join(
                [
                    "DRY RUN RESULTS",
                    "---------------",
                    *[
                        f"{payload['artifact_id']}: passed={payload['passed']} score={payload['score']:.3f}"
                        for payload in (asdict(verdict) for verdict in verdicts)
                    ],
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

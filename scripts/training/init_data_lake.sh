#!/usr/bin/env bash
set -euo pipefail

cd /mnt/s3m-weights/datasets
dvc init
mkdir -p tactical planning threat arabic cyber sustainment readiness comms surveillance
# Each domain is isolated for tactical retraining provenance in the offline vault.

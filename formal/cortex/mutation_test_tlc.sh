#!/usr/bin/env bash
# Removes one guard at a time and expects TLC to report an invariant violation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${ROOT}/CyberAuthority.tla"
CFG="${ROOT}/CyberAuthority.cfg"
MUTATED_DIR="${ROOT}/.mutation_workspace"
TLA_JAR="${TLA_JAR:-${ROOT}/../../tools/bin/tla2tools.jar}"

if [[ ! -f "${TLA_JAR}" ]]; then
  echo "missing TLC jar at ${TLA_JAR}" >&2
  exit 2
fi

run_tlc() {
  java -cp "${TLA_JAR}" tlc2.TLC -config "$2" "$1" 2>&1
}

mkdir -p "${MUTATED_DIR}"

echo "=== BASELINE TLC ==="
baseline_out="$(run_tlc "${MODEL}" "${CFG}")"
echo "${baseline_out}"
echo "${baseline_out}" | grep -q "Model checking completed"
if echo "${baseline_out}" | grep -qi "Error:"; then
  echo "baseline TLC reported an error" >&2
  exit 1
fi

python3 - "${MODEL}" "${MUTATED_DIR}" <<'PY'
import sys
from pathlib import Path

model_path = Path(sys.argv[1])
mut_dir = Path(sys.argv[2])
text = model_path.read_text(encoding="utf-8")

mutations = {
    "envelope_guard": (
        "  /\\ action \\in parentGrants[actor]\n  /\\ childGrants'",
        "  /\\ childGrants'",
    ),
    "duress_guard": (
        "  /\\ duressApprovals' = duressApprovals \\union {change}\n"
        "  /\\ UNCHANGED <<parentGrants, childGrants, need, regularApprovals, executed, verified, rolledBack>>",
        "  /\\ duressApprovals' = duressApprovals \\union {change}\n"
        "  /\\ need' = [need EXCEPT ![change] = need[change] - 1]\n"
        "  /\\ UNCHANGED <<parentGrants, childGrants, regularApprovals, executed, verified, rolledBack>>",
    ),
    "exclusive_guard": (
        "  /\\ change \\notin rolledBack\n  /\\ verified'",
        "  /\\ verified'",
    ),
    "execution_guard": (
        "  /\\ change \\in executed\n  /\\ change \\notin verified",
        "  /\\ change \\notin verified",
    ),
}

import shutil

for name, (needle, repl) in mutations.items():
    if needle not in text:
        raise SystemExit(f"mutation needle not found for {name}")
    mutated = text.replace(needle, repl, 1)
    case_dir = mut_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "CyberAuthority.tla").write_text(mutated, encoding="utf-8")
    shutil.copy2(Path(sys.argv[1]).with_name("CyberAuthority.cfg"), case_dir / "CyberAuthority.cfg")

print("wrote", len(mutations), "mutated models")
PY

failures=0
for case_dir in "${MUTATED_DIR}"/*; do
  [[ -d "${case_dir}" ]] || continue
  base="$(basename "${case_dir}")"
  echo "=== MUTATION ${base} ==="
  set +e
  out="$(run_tlc "${case_dir}/CyberAuthority.tla" "${case_dir}/CyberAuthority.cfg")"
  status=$?
  set -e
  echo "${out}"
  if [[ ${status} -ne 0 ]] || echo "${out}" | grep -qi "Error:"; then
    echo "mutation ${base}: violation detected"
  else
    echo "mutation ${base}: FAIL — TLC passed without catching removed guard" >&2
    failures=$((failures + 1))
  fi
done

if [[ ${failures} -gt 0 ]]; then
  echo "${failures} mutation(s) were not caught" >&2
  exit 1
fi

echo "All mutations were caught by TLC."

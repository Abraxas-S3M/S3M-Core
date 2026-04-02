"""Bayesian threat network for tactical uncertainty reasoning.

The DAG captures doctrinal dependencies between sensor quality, threat class,
intent, capability, and resulting engagement risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Dict, Iterable, List, Sequence, Tuple


@dataclass
class _Factor:
    """Discrete factor used by exact variable-elimination inference."""

    variables: List[str]
    table: Dict[Tuple[str, ...], float]

    def sum_out(self, variable: str, domains: Dict[str, List[str]]) -> "_Factor":
        if variable not in self.variables:
            return _Factor(list(self.variables), dict(self.table))
        idx = self.variables.index(variable)
        out_vars = [v for v in self.variables if v != variable]
        out_table: Dict[Tuple[str, ...], float] = {}
        if not out_vars:
            total = 0.0
            for value in domains[variable]:
                key = [value]
                total += self.table.get(tuple(key), 0.0)
            return _Factor([], {(): total})
        for assignment in product(*(domains[v] for v in out_vars)):
            total = 0.0
            for value in domains[variable]:
                full = list(assignment)
                full.insert(idx, value)
                total += self.table.get(tuple(full), 0.0)
            out_table[tuple(assignment)] = total
        return _Factor(out_vars, out_table)

    def restrict(self, evidence: Dict[str, str]) -> "_Factor":
        if not evidence:
            return _Factor(list(self.variables), dict(self.table))
        out_table: Dict[Tuple[str, ...], float] = {}
        for key, value in self.table.items():
            keep = True
            for idx, var in enumerate(self.variables):
                ev = evidence.get(var)
                if ev is not None and key[idx] != ev:
                    keep = False
                    break
            if keep:
                out_table[key] = value
        return _Factor(list(self.variables), out_table)

    @staticmethod
    def multiply(factors: Sequence["_Factor"], domains: Dict[str, List[str]]) -> "_Factor":
        if not factors:
            return _Factor([], {(): 1.0})
        vars_union: List[str] = []
        for f in factors:
            for var in f.variables:
                if var not in vars_union:
                    vars_union.append(var)

        out_table: Dict[Tuple[str, ...], float] = {}
        for assignment in product(*(domains[v] for v in vars_union)):
            val = 1.0
            for factor in factors:
                if not factor.variables:
                    val *= factor.table.get((), 0.0)
                    continue
                key = tuple(assignment[vars_union.index(v)] for v in factor.variables)
                val *= factor.table.get(key, 0.0)
            out_table[assignment] = val
        return _Factor(vars_union, out_table)


class BayesianThreatNet:
    """7-node Bayesian network for military threat assessment."""

    def __init__(self) -> None:
        self.domains: Dict[str, List[str]] = {
            "sensor_return": ["none", "weak", "strong"],
            "threat_category": ["civilian", "unknown", "military"],
            "threat_intent": ["benign", "monitor", "attack"],
            "electronic_signature": ["none", "low", "high"],
            "behavior_pattern": ["normal", "suspicious", "aggressive"],
            "threat_capability": ["low", "medium", "high"],
            "engagement_risk": ["low", "medium", "high"],
        }
        self.parents: Dict[str, List[str]] = {
            "sensor_return": [],
            "threat_category": ["sensor_return"],
            "threat_intent": ["threat_category"],
            "electronic_signature": [],
            "behavior_pattern": [],
            "threat_capability": ["electronic_signature", "behavior_pattern"],
            "engagement_risk": ["threat_capability", "threat_intent"],
        }
        self._cpts = self._build_cpts()

    def _build_cpts(self) -> Dict[str, Dict[Tuple[str, ...], Dict[str, float]]]:
        """CPT priors tuned for tactical sensing and engagement context."""
        cpts: Dict[str, Dict[Tuple[str, ...], Dict[str, float]]] = {}
        cpts["sensor_return"] = {
            (): {"none": 0.20, "weak": 0.45, "strong": 0.35},
        }
        cpts["electronic_signature"] = {
            (): {"none": 0.30, "low": 0.45, "high": 0.25},
        }
        cpts["behavior_pattern"] = {
            (): {"normal": 0.45, "suspicious": 0.35, "aggressive": 0.20},
        }

        cpts["threat_category"] = {
            ("none",): {"civilian": 0.65, "unknown": 0.30, "military": 0.05},
            ("weak",): {"civilian": 0.25, "unknown": 0.50, "military": 0.25},
            ("strong",): {"civilian": 0.05, "unknown": 0.30, "military": 0.65},
        }
        cpts["threat_intent"] = {
            ("civilian",): {"benign": 0.75, "monitor": 0.22, "attack": 0.03},
            ("unknown",): {"benign": 0.30, "monitor": 0.50, "attack": 0.20},
            ("military",): {"benign": 0.08, "monitor": 0.37, "attack": 0.55},
        }

        capability: Dict[Tuple[str, ...], Dict[str, float]] = {}
        for es in self.domains["electronic_signature"]:
            for bp in self.domains["behavior_pattern"]:
                if es == "high" and bp == "aggressive":
                    capability[(es, bp)] = {"low": 0.05, "medium": 0.25, "high": 0.70}
                elif es in {"low", "high"} and bp == "suspicious":
                    capability[(es, bp)] = {"low": 0.10, "medium": 0.55, "high": 0.35}
                elif es == "none" and bp == "normal":
                    capability[(es, bp)] = {"low": 0.80, "medium": 0.17, "high": 0.03}
                else:
                    capability[(es, bp)] = {"low": 0.35, "medium": 0.45, "high": 0.20}
        cpts["threat_capability"] = capability

        risk: Dict[Tuple[str, ...], Dict[str, float]] = {}
        for cap in self.domains["threat_capability"]:
            for intent in self.domains["threat_intent"]:
                if cap == "high" and intent == "attack":
                    risk[(cap, intent)] = {"low": 0.03, "medium": 0.17, "high": 0.80}
                elif cap == "medium" and intent in {"monitor", "attack"}:
                    risk[(cap, intent)] = {"low": 0.18, "medium": 0.57, "high": 0.25}
                elif cap == "low" and intent == "benign":
                    risk[(cap, intent)] = {"low": 0.88, "medium": 0.10, "high": 0.02}
                else:
                    risk[(cap, intent)] = {"low": 0.45, "medium": 0.40, "high": 0.15}
        cpts["engagement_risk"] = risk
        return cpts

    def _factors(self) -> List[_Factor]:
        factors: List[_Factor] = []
        for node, parents in self.parents.items():
            rows = self._cpts[node]
            vars_for_factor = list(parents) + [node]
            table: Dict[Tuple[str, ...], float] = {}
            for parent_values, distribution in rows.items():
                for value, prob in distribution.items():
                    key = tuple(parent_values) + (value,)
                    table[key] = float(prob)
            factors.append(_Factor(vars_for_factor, table))
        return factors

    def infer(self, query: str, evidence: Dict[str, str]) -> Dict[str, float]:
        """Exact inference using variable elimination."""
        if query not in self.domains:
            raise KeyError(f"unknown query variable: {query}")
        for key, val in evidence.items():
            if key not in self.domains:
                raise KeyError(f"unknown evidence variable: {key}")
            if val not in self.domains[key]:
                raise ValueError(f"invalid value '{val}' for {key}")

        factors = [f.restrict(evidence) for f in self._factors()]
        hidden = [
            var
            for var in self.domains
            if var != query and var not in evidence
        ]

        for var in hidden:
            related = [f for f in factors if var in f.variables]
            if not related:
                continue
            factors = [f for f in factors if var not in f.variables]
            combined = _Factor.multiply(related, self.domains)
            factors.append(combined.sum_out(var, self.domains))

        final_factor = _Factor.multiply(factors, self.domains)
        result: Dict[str, float] = {}
        total = 0.0
        q_idx = final_factor.variables.index(query) if query in final_factor.variables else -1
        for value in self.domains[query]:
            p = 0.0
            for assignment, prob in final_factor.table.items():
                if q_idx == -1:
                    p += prob
                elif assignment[q_idx] == value:
                    p += prob
            result[value] = p
            total += p
        if total <= 0.0:
            uniform = 1.0 / float(len(self.domains[query]))
            return {value: uniform for value in self.domains[query]}
        return {k: v / total for k, v in result.items()}

    def threat_score(self, evidence: Dict[str, str]) -> float:
        """Aggregate risk score in [0, 1] from engagement-risk posterior."""
        posterior = self.infer("engagement_risk", evidence)
        return float(
            (posterior.get("low", 0.0) * 0.1)
            + (posterior.get("medium", 0.0) * 0.55)
            + (posterior.get("high", 0.0) * 0.95)
        )

    def assess(self, evidence: Dict[str, str]) -> Dict[str, object]:
        """Return full tactical threat assessment payload."""
        category = self.infer("threat_category", evidence)
        intent = self.infer("threat_intent", evidence)
        capability = self.infer("threat_capability", evidence)
        risk = self.infer("engagement_risk", evidence)
        return {
            "category": category,
            "intent": intent,
            "capability": capability,
            "engagement_risk": risk,
            "threat_score": self.threat_score(evidence),
        }


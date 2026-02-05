from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


def _load_yaml(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


@dataclass(frozen=True)
class ScorecardResult:
    scenario_id: str
    scenario_name: str
    score: float
    guardrail_pass: bool
    guardrail_notes: List[str]
    metrics: Dict[str, float]
    weighted_terms: Dict[str, float]


def load_scorecard(path: str = "configs/scorecard.yaml") -> Dict[str, Any]:
    cfg = _load_yaml(path)
    if "scorecard" not in cfg:
        raise ValueError("configs/scorecard.yaml must contain top-level key: scorecard")
    sc = cfg["scorecard"] or {}
    if "weights" not in sc or not isinstance(sc["weights"], dict) or not sc["weights"]:
        raise ValueError("scorecard.weights must be a non-empty mapping")
    sc.setdefault("guardrails", {})
    return sc


def compute_score(
    *,
    scenario_id: str,
    scenario_name: str,
    final_metrics: Dict[str, Any],
    scorecard: Dict[str, Any],
) -> ScorecardResult:
    weights: Dict[str, float] = {k: _safe_float(v) for k, v in (scorecard.get("weights") or {}).items()}
    guardrails: Dict[str, Any] = scorecard.get("guardrails") or {}

    metrics = {k: _safe_float(final_metrics.get(k, 0.0)) for k in weights.keys()}

    weighted_terms: Dict[str, float] = {}
    score = 0.0
    for k, w in weights.items():
        term = metrics.get(k, 0.0) * w
        weighted_terms[k] = term
        score += term

    notes: List[str] = []
    guardrail_pass = True

    # Guardrails (optional)
    min_rep = guardrails.get("min_reputation", None)
    if min_rep is not None:
        rep = _safe_float(final_metrics.get("reputation_capital", 0.0))
        if rep < _safe_float(min_rep):
            guardrail_pass = False
            notes.append(f"reputation_capital {rep:.3f} < min_reputation {float(min_rep):.3f}")

    max_con = guardrails.get("max_constraints", None)
    if max_con is not None:
        con = _safe_float(final_metrics.get("regulatory_constraint_level", 0.0))
        if con > _safe_float(max_con):
            guardrail_pass = False
            notes.append(f"regulatory_constraint_level {con:.3f} > max_constraints {float(max_con):.3f}")

    return ScorecardResult(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        score=float(score),
        guardrail_pass=guardrail_pass,
        guardrail_notes=notes,
        metrics=metrics,
        weighted_terms=weighted_terms,
    )


def rank_results(results: List[ScorecardResult]) -> List[ScorecardResult]:
    # Prefer guardrail pass, then higher score
    return sorted(results, key=lambda r: (r.guardrail_pass, r.score), reverse=True)
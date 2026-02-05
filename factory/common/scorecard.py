from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
import pandas as pd


# -----------------------------
# Low-level helpers
# -----------------------------
def _load_yaml(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        # handle strings like "0.8"
        return float(x)
    except Exception:
        return default


# -----------------------------
# Public result type
# -----------------------------
@dataclass(frozen=True)
class ScorecardResult:
    scenario_id: str
    scenario_name: str
    score: float

    # main boolean the UI should use
    guardrail_pass: bool
    guardrail_notes: List[str]

    # diagnostics
    metrics: Dict[str, float]
    weighted_terms: Dict[str, float]

    # Compatibility: some pages might expect guardrails_pass
    @property
    def guardrails_pass(self) -> bool:
        return self.guardrail_pass


# -----------------------------
# Scorecard config loading
# -----------------------------
def load_scorecard(path: str = "configs/scorecard.yaml") -> Dict[str, Any]:
    """
    Expected:
    scorecard:
      id: scorecard_v1
      weights: {metric: weight, ...}
      guardrails: { ... }
    """
    cfg = _load_yaml(path)
    if "scorecard" not in cfg:
        raise ValueError("configs/scorecard.yaml must contain top-level key: scorecard")
    sc = cfg["scorecard"] or {}

    if "weights" not in sc or not isinstance(sc["weights"], dict) or not sc["weights"]:
        raise ValueError("scorecard.weights must be a non-empty mapping")

    # guardrails are optional
    if "guardrails" not in sc or sc["guardrails"] is None:
        sc["guardrails"] = {}

    # id is optional but nice
    sc.setdefault("id", "scorecard_v1")
    sc.setdefault("description", "")

    return sc


# -----------------------------
# Core scoring
# -----------------------------
def compute_score(
    *,
    scenario_id: str,
    scenario_name: str,
    final_metrics: Dict[str, Any],
    scorecard: Dict[str, Any],
) -> ScorecardResult:
    """
    Computes a weighted score + guardrails.

    Convention:
      - Higher score is better.
      - Negative weights mean "lower is better" (e.g. regulatory_constraint_level).
    """
    weights: Dict[str, float] = {k: _safe_float(v) for k, v in (scorecard.get("weights") or {}).items()}
    guardrails: Dict[str, Any] = scorecard.get("guardrails") or {}

    # compute only the metrics referenced by weights
    metrics: Dict[str, float] = {k: _safe_float(final_metrics.get(k, 0.0)) for k in weights.keys()}

    weighted_terms: Dict[str, float] = {}
    score = 0.0
    for k, w in weights.items():
        term = metrics.get(k, 0.0) * w
        weighted_terms[k] = float(term)
        score += float(term)

    notes: List[str] = []
    guardrail_pass = True

    # --- Guardrails (optional but recommended) ---
    # 1) Minimum reputation
    if "min_reputation" in guardrails and guardrails["min_reputation"] is not None:
        min_rep = _safe_float(guardrails["min_reputation"])
        rep = _safe_float(final_metrics.get("reputation_capital", 0.0))
        if rep < min_rep:
            guardrail_pass = False
            notes.append(f"reputation_capital {rep:.3f} < min_reputation {min_rep:.3f}")

    # 2) Maximum constraints
    if "max_constraints" in guardrails and guardrails["max_constraints"] is not None:
        max_con = _safe_float(guardrails["max_constraints"])
        con = _safe_float(final_metrics.get("regulatory_constraint_level", 0.0))
        if con > max_con:
            guardrail_pass = False
            notes.append(f"regulatory_constraint_level {con:.3f} > max_constraints {max_con:.3f}")

    # 3) Optional: minimum market access
    if "min_market_access" in guardrails and guardrails["min_market_access"] is not None:
        min_ma = _safe_float(guardrails["min_market_access"])
        ma = _safe_float(final_metrics.get("market_access_factor", 0.0))
        if ma < min_ma:
            guardrail_pass = False
            notes.append(f"market_access_factor {ma:.3f} < min_market_access {min_ma:.3f}")

    return ScorecardResult(
        scenario_id=str(scenario_id),
        scenario_name=str(scenario_name),
        score=float(score),
        guardrail_pass=guardrail_pass,
        guardrail_notes=notes,
        metrics=metrics,
        weighted_terms=weighted_terms,
    )


def compute_score_from_yaml(
    *,
    scenario_id: str,
    scenario_name: str,
    final_metrics: Dict[str, Any],
    scorecard_path: str = "configs/scorecard.yaml",
) -> ScorecardResult:
    """
    Convenience wrapper used by dashboards.
    """
    sc = load_scorecard(scorecard_path)
    return compute_score(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        final_metrics=final_metrics,
        scorecard=sc,
    )


# -----------------------------
# Ranking + dataframe helpers
# -----------------------------
def rank_results(results: List[ScorecardResult]) -> List[ScorecardResult]:
    """
    Prefer guardrail pass, then higher score.
    """
    return sorted(results, key=lambda r: (r.guardrail_pass, r.score), reverse=True)


def to_row(r: ScorecardResult) -> Dict[str, Any]:
    return {
        "scenario_id": r.scenario_id,
        "scenario_name": r.scenario_name,
        "score": r.score,
        "guardrail_pass": r.guardrail_pass,
        "guardrail_notes": "; ".join(r.guardrail_notes) if r.guardrail_notes else "",
        **{f"metric__{k}": v for k, v in r.metrics.items()},
        **{f"term__{k}": v for k, v in r.weighted_terms.items()},
    }


def results_to_dataframe(results: List[ScorecardResult]) -> pd.DataFrame:
    rows = [to_row(r) for r in results]
    return pd.DataFrame(rows)
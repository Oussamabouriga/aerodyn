from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

from factory.simulate.run import run_simulation


@dataclass
class ScenarioRunSummary:
    scenario_id: str
    scenario_name: str
    knobs_used: Dict[str, float]
    final_metrics: Dict[str, float]
    df: pd.DataFrame


def extract_final_metrics(df: pd.DataFrame) -> Dict[str, float]:
    """
    Standardize what we compare on the dashboard.
    Uses last row (end of horizon).
    """
    last = df.iloc[-1]

    def get(col: str, default: float = 0.0) -> float:
        return float(last[col]) if col in df.columns else float(default)

    return {
        "deals_won_per_year": get("deals_won_per_year"),
        "reputation_capital": get("reputation_capital"),
        "regulatory_constraint_level": get("regulatory_constraint_level"),
        "market_access_factor": get("market_access_factor"),
        "opportunity_pipeline": get("opportunity_pipeline"),
        "ai_rnd_capability": get("ai_rnd_capability"),
        "public_backlash_index": get("public_backlash_index"),
        "win_rate": get("win_rate"),
    }


def run_scenarios(
    scenarios: List[Dict[str, Any]],
    knob_overrides_by_id: Optional[Dict[str, Dict[str, float]]] = None,
) -> List[ScenarioRunSummary]:
    """
    Runs each scenario via factory.simulate.run.run_simulation and returns:
      - the full df
      - final metrics
      - knobs_used = scenario knobs merged with optional per-scenario overrides
    """
    knob_overrides_by_id = knob_overrides_by_id or {}
    results: List[ScenarioRunSummary] = []

    for s in scenarios:
        sid = str(s.get("id"))
        name = str(s.get("name", sid))
        knobs = {k: float(v) for k, v in (s.get("knobs") or {}).items()}

        # apply extra overrides for this scenario
        extra = knob_overrides_by_id.get(sid, {})
        for k, v in extra.items():
            knobs[k] = float(v)

        df = run_simulation(sid, knob_overrides=extra if extra else None)
        final_metrics = extract_final_metrics(df)

        results.append(
            ScenarioRunSummary(
                scenario_id=sid,
                scenario_name=name,
                knobs_used=knobs,
                final_metrics=final_metrics,
                df=df,
            )
        )

    return results


def to_comparison_dataframe(runs: List[ScenarioRunSummary]) -> pd.DataFrame:
    """
    Returns a table for Year-10 comparison across scenarios.
    """
    rows = []
    for r in runs:
        row = {"scenario_id": r.scenario_id, "scenario_name": r.scenario_name}
        row.update(r.final_metrics)
        rows.append(row)
    return pd.DataFrame(rows)
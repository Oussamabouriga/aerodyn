from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import yaml
import pandas as pd


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def load_yaml(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class SimConfig:
    dt_months: int
    horizon_years: int
    params: Dict[str, float]
    knobs: Dict[str, float]
    initials: Dict[str, float]


def build_sim_config(scenario_id: str = "baseline", knob_overrides: Dict[str, float] | None = None) -> SimConfig:
    variables = load_yaml("configs/variables.yaml")["variables"]
    model_cfg = load_yaml("configs/model.yaml")["model"]
    scenarios = load_yaml("configs/scenarios.yaml")["scenarios"]

    scenario = next(s for s in scenarios if s["id"] == scenario_id)
    knobs = {k: float(v) for k, v in scenario.get("knobs", {}).items()}

    # Apply overrides (UI sliders) on top of scenario knobs
    if knob_overrides:
        for k, v in knob_overrides.items():
            knobs[k] = float(v)

    # Initial values for stocks from variables.yaml
    initials: Dict[str, float] = {}
    for v in variables:
        if v["type"] == "stock":
            initials[v["id"]] = float(v["initial"])

    return SimConfig(
        dt_months=int(model_cfg["time_step_months"]),
        horizon_years=int(model_cfg["horizon_years"]),
        params={k: float(v) for k, v in model_cfg["parameters"].items()},
        knobs=knobs,
        initials=initials,
    )


def run_simulation(scenario_id: str = "baseline", knob_overrides: Dict[str, float] | None = None) -> pd.DataFrame:
    cfg = build_sim_config(scenario_id=scenario_id, knob_overrides=knob_overrides)

    # Stocks
    pipeline = cfg.initials["opportunity_pipeline"]
    rep = cfg.initials["reputation_capital"]
    cons = cfg.initials["regulatory_constraint_level"]
    cap = cfg.initials["ai_rnd_capability"]

    # Knobs (now from scenario + overrides)
    invest = cfg.knobs["investment_intensity"]
    incident = cfg.knobs["incident_rate"]
    pr = cfg.knobs["pr_transparency_effort"]
    trend = cfg.knobs["policy_tightening_trend"]

    p = cfg.params
    months = cfg.horizon_years * 12
    rows = []

    for t in range(months + 1):
        exposure = clamp(p["exposure_w_investment"] * invest + p["exposure_w_capability"] * cap, 0, 1)
        market_access = clamp(1.0 - cons, 0, 1)

        backlash = (
            p["backlash_w_incident"] * incident
            + p["backlash_w_exposure"] * exposure
            - p["backlash_w_pr"] * pr
            + p["backlash_w_constraints"] * cons
        )
        public_backlash = clamp(backlash, 0, 1)

        win = (
            p["base_win_rate"]
            + p["win_w_capability"] * cap
            + p["win_w_reputation"] * rep
            - p["win_w_constraints"] * cons
        )
        win_rate = clamp(win, p["win_min"], p["win_max"])

        inflow = p["base_opportunity_inflow_per_month"] * (0.7 + 0.6 * rep) * market_access
        close = pipeline * p["pipeline_close_rate_per_month"] * win_rate
        loss = pipeline * p["pipeline_loss_rate_per_month"] * (0.5 + 0.5 * public_backlash)

        rep_gain = p["reputation_recovery_rate_per_month"] * pr * (1 - rep)
        rep_loss = p["reputation_decay_rate_per_month"] * public_backlash * rep

        tighten_pressure = clamp(public_backlash + max(trend, 0), 0, 2)
        relax_pressure = clamp(pr - max(trend, 0), 0, 1)

        cons_tighten = p["constraint_tighten_rate_per_month"] * tighten_pressure * (1 - cons)
        cons_relax = p["constraint_relax_rate_per_month"] * relax_pressure * cons

        cap_grow = p["capability_growth_rate_per_month"] * invest * (1 - cap)
        cap_decay = p["capability_decay_rate_per_month"] * cap

        rows.append(
            {
                "month": t,
                "year": t / 12.0,
                "opportunity_pipeline": pipeline,
                "reputation_capital": rep,
                "regulatory_constraint_level": cons,
                "ai_rnd_capability": cap,
                "market_access_factor": market_access,
                "public_backlash_index": public_backlash,
                "win_rate": win_rate,
                "deals_closed_per_month": close,
                "deals_won_per_year": close * 12.0,
            }
        )

        if t < months:
            pipeline = clamp(pipeline + (inflow - close - loss) * cfg.dt_months, 0, 1e9)
            rep = clamp(rep + (rep_gain - rep_loss) * cfg.dt_months, 0, 1)
            cons = clamp(cons + (cons_tighten - cons_relax) * cfg.dt_months, 0, 1)
            cap = clamp(cap + (cap_grow - cap_decay) * cfg.dt_months, 0, 1)

    return pd.DataFrame(rows)


def save_run(df: pd.DataFrame, scenario_id: str) -> Path:
    out_dir = Path("runs") / pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S") / scenario_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "results.csv"
    df.to_csv(out_path, index=False)
    return out_path


if __name__ == "__main__":
    df = run_simulation("baseline")
    path = save_run(df, "baseline")
    print(f"✅ Saved results to: {path}")

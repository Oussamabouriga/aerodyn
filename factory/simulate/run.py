from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
import pandas as pd


# -----------------------------
# Helpers
# -----------------------------
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def load_yaml(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# -----------------------------
# Config container (UNCHANGED)
# -----------------------------
@dataclass
class SimConfig:
    dt_months: int
    horizon_years: int
    params: Dict[str, float]
    knobs: Dict[str, float]
    initials: Dict[str, float]


def build_sim_config(scenario_id: str = "baseline", knob_overrides: Dict[str, float] | None = None) -> SimConfig:
    """
    Reads:
      - configs/variables.yaml (stock initials)
      - configs/model.yaml (time_step_months, horizon_years, parameters)
      - configs/scenarios.yaml (scenario knobs)
    and returns a single merged runtime config.

    (Same behavior as your original file.)
    """
    variables_cfg = load_yaml("configs/variables.yaml")
    model_cfg = load_yaml("configs/model.yaml")
    scenarios_cfg = load_yaml("configs/scenarios.yaml")

    variables = variables_cfg.get("variables", [])
    core = (model_cfg.get("model") or {})
    scenarios = scenarios_cfg.get("scenarios", [])

    scenario = next(s for s in scenarios if s.get("id") == scenario_id)
    knobs = {k: float(v) for k, v in (scenario.get("knobs", {}) or {}).items()}

    # Apply overrides (UI sliders) on top of scenario knobs
    if knob_overrides:
        for k, v in knob_overrides.items():
            knobs[k] = float(v)

    # Initial values for stocks from variables.yaml
    initials: Dict[str, float] = {}
    for v in variables:
        if isinstance(v, dict) and v.get("type") == "stock":
            initials[str(v["id"])] = float(v.get("initial", 0.0))

    return SimConfig(
        dt_months=int(core.get("time_step_months", 1)),
        horizon_years=int(core.get("horizon_years", 10)),
        params={k: float(v) for k, v in (core.get("parameters") or {}).items()},
        knobs=knobs,
        initials=initials,
    )


# -----------------------------
# Step 5: Config-driven engine (safe opt-in)
# -----------------------------
def _should_use_config_engine() -> bool:
    """
    Opt-in behavior:
    - Use YAML-driven engine ONLY when both files exist and contain expected keys.
    - Otherwise fallback to original hardcoded v0.1.
    """
    structure = load_yaml("configs/structure.yaml")
    equations = load_yaml("configs/equations.yaml")

    if not structure or not equations:
        return False

    s = structure.get("structure") or {}
    eqs = equations.get("equations") or []

    # minimal sanity checks
    if not isinstance(s, dict) or not isinstance(eqs, list):
        return False
    if not s.get("stocks") or not s.get("flows") or not s.get("aux"):
        return False
    if len(eqs) < 5:
        return False

    return True


def _run_simulation_from_yaml(cfg: SimConfig) -> pd.DataFrame:
    """
    YAML-driven model execution (Step 5).
    - Keeps output columns compatible with dashboard.
    - If something is invalid, it raises, and caller will fallback to hardcoded model.
    """
    # Lazy imports: your app still works even if you haven't created these files yet.
    from factory.assemble.model_builder import build_model_spec, simulate as simulate_rows

    # Merge params + knobs into one dict for the builder
    knobs = dict(cfg.params)
    knobs.update(cfg.knobs)

    spec = build_model_spec(knobs=knobs)
    rows = simulate_rows(spec)
    df = pd.DataFrame(rows)

    # Ensure the exact columns your dashboard expects exist or are derivable
    if "month" not in df.columns and "year" in df.columns:
        # recreate month from year using dt_months
        dt_years = cfg.dt_months / 12.0
        df["month"] = (df["year"] / dt_years).round().astype(int)

    # Maintain backward compatible fields
    if "deals_closed_per_month" not in df.columns and "opportunity_conversion" in df.columns:
        df["deals_closed_per_month"] = df["opportunity_conversion"] / 12.0
    if "deals_won_per_year" not in df.columns and "opportunity_conversion" in df.columns:
        df["deals_won_per_year"] = df["opportunity_conversion"]

    # Stable ordering (optional)
    preferred = [
        "month",
        "year",
        "opportunity_pipeline",
        "reputation_capital",
        "regulatory_constraint_level",
        "ai_rnd_capability",
        "market_access_factor",
        "public_backlash_index",
        "win_rate",
        "deals_closed_per_month",
        "deals_won_per_year",
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[cols]

    return df


# -----------------------------
# Original v0.1 hardcoded engine (fallback)
# -----------------------------
def _run_simulation_hardcoded(cfg: SimConfig) -> pd.DataFrame:
    # Stocks
    pipeline = cfg.initials["opportunity_pipeline"]
    rep = cfg.initials["reputation_capital"]
    cons = cfg.initials["regulatory_constraint_level"]
    cap = cfg.initials["ai_rnd_capability"]

    # Knobs (scenario + overrides)
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


# -----------------------------
# Public API (UNCHANGED)
# -----------------------------
def run_simulation(scenario_id: str = "baseline", knob_overrides: Dict[str, float] | None = None) -> pd.DataFrame:
    """
    Public function used by Streamlit dashboard.
    Keeps compatibility with your existing UI.

    Behavior:
      1) Try YAML-driven Step-5 engine if structure/equations exist and are valid.
      2) If anything fails, fallback to the current hardcoded v0.1 equations.
    """
    cfg = build_sim_config(scenario_id=scenario_id, knob_overrides=knob_overrides)

    if _should_use_config_engine():
        try:
            return _run_simulation_from_yaml(cfg)
        except Exception:
            # Safety: never break the dashboard; fallback to known working model.
            return _run_simulation_hardcoded(cfg)

    return _run_simulation_hardcoded(cfg)


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
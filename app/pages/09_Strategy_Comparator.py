import sys
from pathlib import Path
from typing import Dict, Any, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
import pandas as pd
import plotly.express as px
import yaml

from factory.simulate.batch import run_scenarios
from factory.common.scorecard import (
    compute_score_from_yaml,
    rank_results,
    results_to_dataframe,
)


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


st.set_page_config(page_title="Strategy Comparator", page_icon="🏁", layout="wide")
st.title("Strategy Comparator")
st.caption("CEO view: compare strategies, rank by scorecard, enforce guardrails, and inspect trade-offs.")

# -------------------------
# Load scenarios
# -------------------------
sc_cfg = load_yaml("configs/scenarios.yaml")
scenarios: List[Dict[str, Any]] = sc_cfg.get("scenarios", []) or []
if not scenarios:
    st.error("No scenarios found in configs/scenarios.yaml")
    st.stop()

scenario_ids = [s["id"] for s in scenarios]
labels = {s["id"]: f"{s.get('name','(no name)')} ({s['id']})" for s in scenarios}

# -------------------------
# UI: choose scenarios to compare
# -------------------------
with st.sidebar:
    st.header("Compare scenarios")
    default_sel = ["baseline"] if "baseline" in scenario_ids else [scenario_ids[0]]

    selected = st.multiselect(
        "Scenarios",
        options=scenario_ids,
        default=[x for x in default_sel if x in scenario_ids],
        format_func=lambda x: labels.get(x, x),
    )

    st.caption("Tip: add more scenarios in configs/scenarios.yaml and they appear here automatically.")

    st.divider()
    st.header("Optional: Override knobs for all selected scenarios")
    st.caption("Leave blank to use scenario knobs as defined in YAML.")

    override_invest = st.checkbox("Override investment_intensity")
    override_incident = st.checkbox("Override incident_rate")
    override_pr = st.checkbox("Override pr_transparency_effort")
    override_trend = st.checkbox("Override policy_tightening_trend")

    overrides: Dict[str, float] = {}
    if override_invest:
        overrides["investment_intensity"] = float(st.slider("investment_intensity", 0.0, 1.0, 0.5, 0.01))
    if override_incident:
        overrides["incident_rate"] = float(st.slider("incident_rate", 0.0, 1.0, 0.2, 0.01))
    if override_pr:
        overrides["pr_transparency_effort"] = float(st.slider("pr_transparency_effort", 0.0, 1.0, 0.5, 0.01))
    if override_trend:
        overrides["policy_tightening_trend"] = float(st.slider("policy_tightening_trend", -1.0, 1.0, 0.0, 0.05))

    run_btn = st.button("Run comparison", type="primary", use_container_width=True)

if not selected:
    st.info("Select at least one scenario to compare.")
    st.stop()

# Apply same overrides to each selected scenario (optional)
knob_overrides_by_id: Dict[str, Dict[str, float]] = {}
if overrides:
    for sid in selected:
        knob_overrides_by_id[sid] = dict(overrides)

selected_scenarios = [s for s in scenarios if s["id"] in selected]

# -------------------------
# Run
# -------------------------
if "comparison_runs" not in st.session_state:
    st.session_state.comparison_runs = None

if run_btn or st.session_state.comparison_runs is None:
    with st.spinner("Running scenarios…"):
        runs = run_scenarios(
            selected_scenarios,
            knob_overrides_by_id=knob_overrides_by_id if overrides else None,
        )
    st.session_state.comparison_runs = runs

runs = st.session_state.comparison_runs
if not runs:
    st.stop()

# -------------------------
# Scorecard evaluation
# -------------------------
score_results = []
violations = []

for r in runs:
    sc_res = compute_score_from_yaml(
        scenario_id=r.scenario_id,
        scenario_name=r.scenario_name,
        final_metrics=r.final_metrics,
        scorecard_path="configs/scorecard.yaml",
    )
    score_results.append(sc_res)

    if not sc_res.guardrail_pass:
        violations.append(
            {"scenario_id": r.scenario_id, "violations": "; ".join(sc_res.guardrail_notes)}
        )

# Rank results (guardrails pass first, then score)
score_results = rank_results(score_results)

df_scores = results_to_dataframe(score_results)

# Add a cleaner "display" columns set for CEO view
metric_cols = [c for c in df_scores.columns if c.startswith("metric__")]
base_cols = ["scenario_name", "scenario_id", "guardrail_pass", "score", "guardrail_notes"]
display_cols = base_cols + metric_cols

st.subheader("Year-10 Comparison (Ranked)")
st.caption("Rank prefers guardrail-passing scenarios, then highest score.")
st.dataframe(df_scores[display_cols], use_container_width=True)

if violations:
    st.warning("Some scenarios violate guardrails.")
    st.dataframe(pd.DataFrame(violations), use_container_width=True)

st.divider()

# -------------------------
# Winner card
# -------------------------
winner_res = score_results[0]
winner_label = labels.get(winner_res.scenario_id, winner_res.scenario_id)

st.subheader("Recommended Strategy (Scorecard + Guardrails)")
if winner_res.guardrail_pass:
    st.success(f"✅ Best: {winner_label} — score={winner_res.score:.3f}")
else:
    st.error(f"⛔ Highest score violates guardrails: {winner_label} — score={winner_res.score:.3f}")
    if winner_res.guardrail_notes:
        st.write("Violations:")
        for v in winner_res.guardrail_notes:
            st.write(f"- {v}")

st.divider()

# -------------------------
# Delta vs baseline
# -------------------------
baseline_res = next((r for r in score_results if r.scenario_id == "baseline"), None)

if baseline_res:
    st.subheader("Delta vs Baseline (Year 10)")

    # Use scorecard metrics (the weighted metrics) for delta table
    metrics = list(winner_res.metrics.keys())

    delta_rows = []
    for m in metrics:
        wv = float(winner_res.metrics.get(m, 0.0))
        bv = float(baseline_res.metrics.get(m, 0.0))
        delta_rows.append(
            {
                "metric": m,
                "winner": wv,
                "baseline": bv,
                "delta": wv - bv,
            }
        )

    st.dataframe(pd.DataFrame(delta_rows), use_container_width=True)
else:
    st.info("Baseline not selected (or not present), so delta vs baseline is not shown.")

st.divider()

# -------------------------
# Curves: compare time series for key KPIs
# -------------------------
st.subheader("Scenario Curves (Time Series)")
metric = st.selectbox(
    "Metric",
    [
        "deals_won_per_year",
        "opportunity_pipeline",
        "reputation_capital",
        "regulatory_constraint_level",
        "market_access_factor",
        "public_backlash_index",
        "ai_rnd_capability",
        "win_rate",
    ],
    index=0,
)

long_rows = []
for r in runs:
    dd = r.df.copy()
    if metric not in dd.columns:
        continue
    dd["scenario_name"] = r.scenario_name
    long_rows.append(dd[["year", metric, "scenario_name"]])

if not long_rows:
    st.info("Selected metric is not available in the simulation output.")
else:
    long_df = pd.concat(long_rows, ignore_index=True)
    fig = px.line(long_df, x="year", y=metric, color="scenario_name", title=f"{metric} over time")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# -------------------------
# Explain scorecard (weights + guardrails)
# -------------------------
with st.expander("Scorecard details (weights + guardrails)"):
    sc = load_yaml("configs/scorecard.yaml").get("scorecard", {})
    st.write(sc)
    st.caption("Edit configs/scorecard.yaml to change board priorities and constraints.")
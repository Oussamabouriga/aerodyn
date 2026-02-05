from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure repo root import works
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import streamlit as st
import plotly.express as px
import yaml

from factory.simulate.run import run_simulation
from factory.common.scorecard import load_scorecard, compute_score, rank_results


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def scenario_options() -> List[Dict[str, Any]]:
    return load_yaml("configs/scenarios.yaml").get("scenarios", [])


def final_metrics_from_df(df: pd.DataFrame) -> Dict[str, float]:
    last = df.iloc[-1]
    keys = [
        "deals_won_per_year",
        "opportunity_pipeline",
        "reputation_capital",
        "regulatory_constraint_level",
        "market_access_factor",
        "public_backlash_index",
    ]
    out: Dict[str, float] = {}
    for k in keys:
        out[k] = float(last.get(k, 0.0))
    return out


st.set_page_config(page_title="Board View", page_icon="🏛️", layout="wide")
st.title("Board View — Portfolio & Ranking")
st.caption("Run multiple scenarios, compare final outcomes, and rank strategies using configs/scorecard.yaml.")

scenarios = scenario_options()
if not scenarios:
    st.error("No scenarios found in configs/scenarios.yaml")
    st.stop()

scenario_ids = [s["id"] for s in scenarios]
scenario_labels = {s["id"]: f"{s['name']} ({s['id']})" for s in scenarios}
scenario_by_id = {s["id"]: s for s in scenarios}

# Sidebar controls
with st.sidebar:
    st.header("Portfolio controls")

    default_selected = ["baseline"] if "baseline" in scenario_ids else [scenario_ids[0]]
    selected = st.multiselect(
        "Scenarios to run",
        options=scenario_ids,
        default=default_selected,
        format_func=lambda x: scenario_labels.get(x, x),
    )

    st.divider()
    st.subheader("Scorecard")
    st.caption("Loaded from configs/scorecard.yaml")
    run_portfolio = st.button("Run portfolio", type="primary", use_container_width=True)

if not selected:
    st.info("Select at least one scenario in the sidebar.")
    st.stop()

# Load scorecard now (fail early if invalid)
try:
    scorecard = load_scorecard("configs/scorecard.yaml")
except Exception as e:
    st.error(f"Scorecard error: {e}")
    st.stop()

st.subheader("Scorecard definition")
with st.expander("Show scorecard.yaml (transparent scoring)", expanded=False):
    st.code(Path("configs/scorecard.yaml").read_text(encoding="utf-8"), language="yaml")

# Run portfolio
if "portfolio" not in st.session_state:
    st.session_state.portfolio = None

if run_portfolio:
    portfolio: Dict[str, pd.DataFrame] = {}
    with st.spinner("Running scenarios…"):
        for sid in selected:
            df = run_simulation(sid, knob_overrides=None)
            portfolio[sid] = df
    st.session_state.portfolio = portfolio

portfolio = st.session_state.portfolio
if not portfolio:
    st.info("Click **Run portfolio** to execute scenarios and compare results.")
    st.stop()

# Compute scorecard results
results = []
rows = []
for sid, df in portfolio.items():
    s = scenario_by_id.get(sid, {"name": sid})
    metrics = final_metrics_from_df(df)
    res = compute_score(
        scenario_id=sid,
        scenario_name=s.get("name", sid),
        final_metrics=metrics,
        scorecard=scorecard,
    )
    results.append(res)

    row = {
        "scenario_id": sid,
        "scenario_name": res.scenario_name,
        "score": res.score,
        "guardrail_pass": res.guardrail_pass,
        "guardrail_notes": "; ".join(res.guardrail_notes) if res.guardrail_notes else "",
        **metrics,
    }
    rows.append(row)

ranked = rank_results(results)
df_table = pd.DataFrame(rows)

# Sort table by guardrail then score
df_table = df_table.sort_values(by=["guardrail_pass", "score"], ascending=[False, False]).reset_index(drop=True)

# Headline recommendation
top = ranked[0]
st.subheader("Board recommendation (scorecard)")
if top.guardrail_pass:
    st.success(f"✅ Recommended: **{top.scenario_name} ({top.scenario_id})** — score={top.score:.3f}")
else:
    st.warning(
        f"⚠️ Highest score fails guardrails: **{top.scenario_name} ({top.scenario_id})** — score={top.score:.3f}\n\n"
        f"Guardrail notes: {', '.join(top.guardrail_notes) if top.guardrail_notes else 'n/a'}"
    )

st.divider()

# Comparison table
st.subheader("Scenario comparison (final year)")
st.dataframe(
    df_table[
        [
            "scenario_name",
            "scenario_id",
            "guardrail_pass",
            "score",
            "deals_won_per_year",
            "opportunity_pipeline",
            "reputation_capital",
            "regulatory_constraint_level",
            "market_access_factor",
            "public_backlash_index",
            "guardrail_notes",
        ]
    ],
    use_container_width=True,
)

# Quick charts: show top 3 by score
top_ids = [r.scenario_id for r in ranked[:3] if r.scenario_id in portfolio]
if len(top_ids) >= 1:
    st.subheader("Top scenarios — trajectories (quick view)")
    metric = st.selectbox(
        "Metric to plot",
        ["deals_won_per_year", "opportunity_pipeline", "reputation_capital", "regulatory_constraint_level", "market_access_factor"],
        index=0,
    )

    long_rows = []
    for sid in top_ids:
        df = portfolio[sid].copy()
        df["scenario_id"] = sid
        df["scenario_name"] = scenario_by_id.get(sid, {}).get("name", sid)
        long_rows.append(df[["year", metric, "scenario_name"]])

    long_df = pd.concat(long_rows, ignore_index=True)
    fig = px.line(long_df, x="year", y=metric, color="scenario_name", title=f"{metric} over time (top scenarios)")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.caption("Note: This ranking is transparent and editable (scorecard.yaml). Guardrails prevent recommending unacceptable profiles.")
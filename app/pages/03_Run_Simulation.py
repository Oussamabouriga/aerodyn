import sys
from pathlib import Path

# Ensure repo root is importable (pages are in app/pages -> go 2 levels up)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from typing import Dict, Any, Optional  # noqa: E402

import yaml  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import plotly.express as px  # noqa: E402

from factory.simulate.run import run_simulation, save_run  # noqa: E402
from factory.common.recommendation import recommend  # noqa: E402


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_param_meta() -> Dict[str, Dict[str, float]]:
    variables = load_yaml("configs/variables.yaml").get("variables", [])
    meta: Dict[str, Dict[str, float]] = {}
    for v in variables:
        if v.get("type") == "param":
            bounds = v.get("bounds", {})
            meta[v["id"]] = {
                "default": float(v.get("default", 0.0)),
                "min": float(bounds.get("min", 0.0)),
                "max": float(bounds.get("max", 1.0)),
            }
    return meta


def scenario_options():
    return load_yaml("configs/scenarios.yaml").get("scenarios", [])


st.set_page_config(page_title="Run Simulation", page_icon="📈", layout="wide")
st.title("Run Simulation")
st.caption("AeroDyn v0.1 — scenario runner with editable knobs (scenario + overrides).")

# -------------------------
# Session state init
# -------------------------
if "df" not in st.session_state:
    st.session_state.df = None
if "baseline_df" not in st.session_state:
    st.session_state.baseline_df = None
if "last_scenario" not in st.session_state:
    st.session_state.last_scenario = None
if "last_knobs" not in st.session_state:
    st.session_state.last_knobs = None
if "llm_analysis" not in st.session_state:
    st.session_state.llm_analysis = None

# -------------------------
# Sidebar controls
# -------------------------
with st.sidebar:
    st.header("Controls")

    scenarios = scenario_options()
    if not scenarios:
        st.error("No scenarios found in configs/scenarios.yaml")
        st.stop()

    scenario_ids = [s["id"] for s in scenarios]
    scenario_labels = {s["id"]: f"{s['name']} ({s['id']})" for s in scenarios}

    chosen = st.selectbox(
        "Scenario",
        options=scenario_ids,
        format_func=lambda x: scenario_labels.get(x, x),
        index=scenario_ids.index("baseline") if "baseline" in scenario_ids else 0,
    )

    compare_with_baseline = st.checkbox("Compare with baseline", value=True)

    scenario = next(s for s in scenarios if s["id"] == chosen)
    knobs_from_yaml = scenario.get("knobs", {})

    meta = get_param_meta()
    required = [
        "investment_intensity",
        "incident_rate",
        "pr_transparency_effort",
        "policy_tightening_trend",
    ]
    missing = [k for k in required if k not in meta]
    if missing:
        st.error(f"Missing param definitions in configs/variables.yaml: {missing}")
        st.stop()

    st.subheader("Decision knobs")

    investment_intensity = st.slider(
        "Investment intensity",
        min_value=meta["investment_intensity"]["min"],
        max_value=meta["investment_intensity"]["max"],
        value=float(knobs_from_yaml.get("investment_intensity", meta["investment_intensity"]["default"])),
        step=0.01,
    )

    incident_rate = st.slider(
        "Incident rate",
        min_value=meta["incident_rate"]["min"],
        max_value=meta["incident_rate"]["max"],
        value=float(knobs_from_yaml.get("incident_rate", meta["incident_rate"]["default"])),
        step=0.01,
    )

    pr_transparency_effort = st.slider(
        "Transparency & PR effort",
        min_value=meta["pr_transparency_effort"]["min"],
        max_value=meta["pr_transparency_effort"]["max"],
        value=float(knobs_from_yaml.get("pr_transparency_effort", meta["pr_transparency_effort"]["default"])),
        step=0.01,
    )

    policy_tightening_trend = st.slider(
        "Policy tightening trend",
        min_value=meta["policy_tightening_trend"]["min"],
        max_value=meta["policy_tightening_trend"]["max"],
        value=float(knobs_from_yaml.get("policy_tightening_trend", meta["policy_tightening_trend"]["default"])),
        step=0.05,
    )

    st.divider()
    run_clicked = st.button("Run simulation", use_container_width=True)

knob_overrides = {
    "investment_intensity": float(investment_intensity),
    "incident_rate": float(incident_rate),
    "pr_transparency_effort": float(pr_transparency_effort),
    "policy_tightening_trend": float(policy_tightening_trend),
}

# -------------------------
# Run simulation
# -------------------------
if run_clicked:
    with st.spinner("Running simulation…"):
        df = run_simulation(chosen, knob_overrides=knob_overrides)

        baseline_df: Optional[pd.DataFrame] = None
        if compare_with_baseline and chosen != "baseline":
            baseline_df = run_simulation("baseline", knob_overrides={})

    st.session_state.df = df
    st.session_state.baseline_df = baseline_df
    st.session_state.last_scenario = chosen
    st.session_state.last_knobs = knob_overrides

    # Clear old analysis after a new run
    st.session_state.llm_analysis = None

df: pd.DataFrame | None = st.session_state.df
if df is None:
    st.info("Use the sidebar and click **Run simulation**.")
    st.stop()

baseline_df: Optional[pd.DataFrame] = st.session_state.baseline_df

# -------------------------
# KPI cards
# -------------------------
last = df.iloc[-1]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Deals won / year (Y10)", f"{last['deals_won_per_year']:.2f}")
k2.metric("Pipeline (deals)", f"{last['opportunity_pipeline']:.1f}")
k3.metric("Reputation", f"{last['reputation_capital']:.3f}")
k4.metric("Constraints", f"{last['regulatory_constraint_level']:.3f}")
k5.metric("Market access", f"{last['market_access_factor']:.3f}")

# -------------------------
# Board Recommendation (rule-based)
# -------------------------
final_metrics = {
    "deals_won_per_year": float(last["deals_won_per_year"]),
    "reputation_capital": float(last["reputation_capital"]),
    "regulatory_constraint_level": float(last["regulatory_constraint_level"]),
    "market_access_factor": float(last["market_access_factor"]),
}

rec = recommend(final_metrics, rule_id="rec_rule_v1")

st.subheader("Board Recommendation (deterministic rule)")
if rec.severity == "success":
    st.success(f"✅ {rec.label} — {rec.reason}")
elif rec.severity == "warning":
    st.warning(f"⚠️ {rec.label} — {rec.reason}")
else:
    st.error(f"⛔ {rec.label} — {rec.reason}")

st.divider()

# -------------------------
# Charts + AI Analyst
# -------------------------
tab1, tab2, tab_ai, tab3 = st.tabs(["Business", "Risk & Constraints", "AI Analyst", "Data"])

with tab1:
    c1, c2 = st.columns(2)
    fig = px.line(df, x="year", y="deals_won_per_year", title="Deals won per year")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    c1.plotly_chart(fig, use_container_width=True)

    fig = px.line(df, x="year", y="opportunity_pipeline", title="Opportunity pipeline")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    c2.plotly_chart(fig, use_container_width=True)

    if baseline_df is not None:
        st.caption("Baseline comparison enabled (use AI Analyst tab for narrative deltas).")

with tab2:
    c1, c2 = st.columns(2)
    fig = px.line(df, x="year", y="reputation_capital", title="Reputation capital")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    c1.plotly_chart(fig, use_container_width=True)

    fig = px.line(df, x="year", y="regulatory_constraint_level", title="Regulatory constraint level")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    c2.plotly_chart(fig, use_container_width=True)

    fig = px.line(df, x="year", y="public_backlash_index", title="Public backlash index")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

with tab_ai:
    st.subheader("AI Analyst (LLM)")
    st.caption("CEO-grade narrative based on outputs + baseline comparison + assumptions. (Business decision support only.)")

    # Convert rule-based recommendation to a dict for the analyst context
    rec_payload = {
        "rule_id": getattr(rec, "rule_id", "rec_rule_v1"),
        "severity": getattr(rec, "severity", "info"),
        "label": getattr(rec, "label", ""),
        "reason": getattr(rec, "reason", ""),
        "final_metrics": final_metrics,
    }

    if baseline_df is None:
        st.info("Baseline comparison is OFF (or you ran baseline). Turn on **Compare with baseline** for richer analysis.")

    gen = st.button("🤖 Generate AI analysis", type="primary", use_container_width=True)

    if gen:
        try:
            from factory.extract.llm_analyst import analyze_run
        except Exception as e:
            st.error(f"Cannot import LLM analyst module: {e}")
            st.stop()

        with st.spinner("Generating CEO-grade analysis…"):
            st.session_state.llm_analysis = analyze_run(
                df,
                scenario_id=st.session_state.last_scenario or chosen,
                knobs_used=st.session_state.last_knobs or {},
                recommendation=rec_payload,
                baseline_df=baseline_df,
            )

    analysis = st.session_state.llm_analysis
    if analysis is None:
        st.info("Click **Generate AI analysis** to get a narrative + recommended actions.")
        st.stop()

    st.markdown("## Executive summary")
    for b in analysis.executive_summary:
        st.write(f"- {b}")

    st.markdown("## Key drivers")
    for d in analysis.key_drivers:
        st.write(f"- {d}")

    st.markdown("## Risks & constraints")
    for r in analysis.risks_and_constraints:
        st.write(f"- {r}")

    st.markdown("## Recommended actions (knob changes)")
    for i, a in enumerate(analysis.recommended_actions, start=1):
        st.markdown(f"**{i}. {a['action']}**")
        st.write(a["rationale"])
        st.caption(f"Expected effect: {a['expected_effect']}")
        st.json(a["knob_changes"])

    st.markdown(f"**Confidence:** `{analysis.confidence}`")

    st.markdown("## Limitations (model + uncertainty)")
    for l in analysis.limitations:
        st.write(f"- {l}")

with tab3:
    st.subheader("Knobs used")
    st.json(st.session_state.last_knobs)
    st.subheader("Preview")
    st.dataframe(df.head(25), use_container_width=True)

# -------------------------
# Save run
# -------------------------
st.divider()
left, right = st.columns([1, 3])

with left:
    if st.button("Save run to /runs", use_container_width=True):
        path = save_run(df, st.session_state.last_scenario or "baseline")
        st.success(f"Saved: {path}")

with right:
    st.caption("Saved runs go to `runs/<timestamp>/<scenario_id>/results.csv` for reproducibility.")
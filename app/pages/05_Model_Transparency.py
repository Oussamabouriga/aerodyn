import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st  # noqa: E402
import pandas as pd  # noqa: E402

from factory.config.io import load_yaml  # noqa: E402


st.set_page_config(page_title="Model Transparency", page_icon="🔎", layout="wide")
st.title("Model Transparency")
st.caption("Traceability view: Evidence → Assumptions → Variables/Params. (Audit-ready foundation)")

variables_yaml = load_yaml("configs/variables.yaml")
evidence_yaml = load_yaml("configs/evidence.yaml")
assumptions_yaml = load_yaml("configs/assumptions.yaml")

variables = variables_yaml.get("variables", [])
evidence = evidence_yaml.get("evidence", [])
assumptions = assumptions_yaml.get("assumptions", [])

if not variables:
    st.warning("No variables found in configs/variables.yaml")
if not evidence:
    st.warning("No evidence found in configs/evidence.yaml")
if not assumptions:
    st.warning("No assumptions found in configs/assumptions.yaml")

# Build lookups
var_ids = [v.get("id") for v in variables if isinstance(v, dict)]
param_ids = [v.get("id") for v in variables if isinstance(v, dict) and v.get("type") == "param"]
evidence_ids = {e.get("id") for e in evidence if isinstance(e, dict)}

# Coverage
linked_vars = set()
linked_params = set()
broken_assumptions = []

for a in assumptions:
    if not isinstance(a, dict):
        continue
    for vid in a.get("linked_variables", []) or []:
        linked_vars.add(vid)
    for pid in a.get("linked_params", []) or []:
        linked_params.add(pid)

    # detect missing evidence ids
    missing_evs = [x for x in (a.get("evidence_ids") or []) if x not in evidence_ids]
    if missing_evs:
        broken_assumptions.append({"assumption_id": a.get("id"), "missing_evidence_ids": missing_evs})

vars_covered = len([v for v in var_ids if v in linked_vars])
params_covered = len([p for p in param_ids if p in linked_params])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Variables", len(var_ids))
c2.metric("Params", len(param_ids))
c3.metric("Vars covered by assumptions", vars_covered)
c4.metric("Evidence items", len(evidence))

st.divider()

tab1, tab2, tab3 = st.tabs(["Evidence", "Assumptions", "Coverage & Gaps"])

with tab1:
    st.subheader("Evidence library")
    df = pd.DataFrame(evidence) if evidence else pd.DataFrame()
    if df.empty:
        st.info("Add evidence items in configs/evidence.yaml")
    else:
        # quick filters
        tag = st.text_input("Filter by tag (contains)", "")
        if tag.strip():
            df = df[df["tags"].astype(str).str.contains(tag.strip(), case=False, na=False)]
        st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Assumptions register")
    df = pd.DataFrame(assumptions) if assumptions else pd.DataFrame()
    if df.empty:
        st.info("Add assumptions in configs/assumptions.yaml")
    else:
        var_filter = st.selectbox("Filter by linked variable", ["(all)"] + sorted(set(var_ids)))
        if var_filter != "(all)":
            df = df[df["linked_variables"].astype(str).str.contains(var_filter, na=False)]
        st.dataframe(df, use_container_width=True)

        if broken_assumptions:
            st.warning("Some assumptions reference missing evidence IDs.")
            st.dataframe(pd.DataFrame(broken_assumptions), use_container_width=True)

with tab3:
    st.subheader("Coverage")
    missing_vars = sorted([v for v in var_ids if v not in linked_vars])
    missing_params = sorted([p for p in param_ids if p not in linked_params])

    colA, colB = st.columns(2)
    with colA:
        st.markdown("### Variables with **no** assumption link")
        if missing_vars:
            st.code("\n".join(missing_vars))
        else:
            st.success("All variables are linked to at least one assumption.")

    with colB:
        st.markdown("### Params with **no** assumption link")
        if missing_params:
            st.code("\n".join(missing_params))
        else:
            st.success("All params are linked to at least one assumption.")

    st.markdown("---")
    st.markdown(
        "✅ Goal: reach *high traceability coverage* so any board recommendation can cite the assumptions + evidence behind it."
    )
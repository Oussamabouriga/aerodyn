import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
import pandas as pd

from factory.config.io import load_yaml, validate_by_filename
from factory.assemble.model_builder import build_model_spec


st.set_page_config(page_title="Model Structure", page_icon="🧩", layout="wide")
st.title("Model Structure & Equations")
st.caption("Transparent model spec: stocks/flows/aux + equations + quick validation.")

structure = load_yaml("configs/structure.yaml")
equations = load_yaml("configs/equations.yaml")
variables = load_yaml("configs/variables.yaml")
model = load_yaml("configs/model.yaml")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Stocks", len((structure.get("structure") or {}).get("stocks") or []))
c2.metric("Flows", len((structure.get("structure") or {}).get("flows") or []))
c3.metric("Aux", len((structure.get("structure") or {}).get("aux") or []))
c4.metric("Equations", len(equations.get("equations") or []))

st.divider()

tab1, tab2, tab3 = st.tabs(["Structure", "Equations", "Validate"])

with tab1:
    st.subheader("Stocks")
    st.dataframe(pd.DataFrame((structure.get("structure") or {}).get("stocks") or []), use_container_width=True)

    st.subheader("Flows")
    st.write((structure.get("structure") or {}).get("flows") or [])

    st.subheader("Aux")
    st.write((structure.get("structure") or {}).get("aux") or [])

with tab2:
    st.subheader("Equations")
    df = pd.DataFrame(equations.get("equations") or [])
    if df.empty:
        st.info("No equations found in configs/equations.yaml")
    else:
        st.dataframe(df, use_container_width=True)

with tab3:
    st.subheader("Config validation")
    try:
        validate_by_filename("variables.yaml", variables)
        validate_by_filename("model.yaml", model)
        validate_by_filename("structure.yaml", structure)
        validate_by_filename("equations.yaml", equations)
        st.success("YAML syntax + business validation: OK")
    except Exception as e:
        st.error(f"Validation failed: {e}")
        st.stop()

    st.subheader("Build + sanity check")
    if st.button("Build model spec", type="primary"):
        try:
            spec = build_model_spec(knobs={})
            st.success("Model spec built successfully.")
            st.json(
                {
                    "time_step_months": spec.time_step_months,
                    "horizon_years": spec.horizon_years,
                    "stocks": spec.stocks,
                    "flows": spec.flows,
                    "aux": spec.aux,
                }
            )
        except Exception as e:
            st.error(f"Build failed: {e}")
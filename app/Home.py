import sys
from pathlib import Path

# Ensure repo root is importable (so `import factory...` works)
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="AeroDyn Model Factory",
    page_icon="🛰️",
    layout="wide",
)

st.title("AeroDyn Model Factory")
st.caption("Board-facing system dynamics dashboard — v0.1")

st.subheader("System status")
c1, c2, c3 = st.columns(3)

with c1:
    st.metric("Config folder", "OK" if Path("configs").exists() else "Missing")

with c2:
    st.metric("Runs folder", "OK" if Path("runs").exists() else "Missing")

with c3:
    st.metric("Simulation engine", "OK" if Path("factory/simulate/run.py").exists() else "Missing")

st.divider()

st.subheader("What this dashboard does")
st.write(
    """
This tool helps AeroDyn leadership explore 5–10 year scenarios for investing in AI-enabled lethal autonomy.

It combines:
- **Editable knobs** (investment, incidents, policy tightening, transparency),
- A **transparent system-dynamics model** (stocks/flows + delays),
- **Scenario simulation** and **traceable outputs** saved in `runs/`.
"""
)

st.info(
    "Next: open **Run Simulation** from the left sidebar to adjust knobs and run scenarios.",
    icon="ℹ️",
)

st.divider()

st.subheader("Quick actions")
b1, b2 = st.columns(2)

with b1:
    if st.button("Show configs location", use_container_width=True):
        st.code("configs/", language="text")

with b2:
    if st.button("Show latest saved run (if any)", use_container_width=True):
        run_paths = sorted(Path("runs").glob("*/**/results.csv"))
        if not run_paths:
            st.warning("No saved runs found yet. Go to **Run Simulation** and click **Save run**.")
        else:
            latest = run_paths[-1]
            st.success(f"Latest saved run: {latest}")
            st.code(str(latest), language="text")

st.caption("v0.1 — Step 3 is complete when Run Simulation works with sliders + charts + save.")
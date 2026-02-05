import sys
from pathlib import Path
from typing import Dict, Any, List

# Ensure repo root is importable (pages are in app/pages -> go 2 levels up)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from factory.config.io import load_yaml, safe_write_with_backup, yaml_roundtrip_dump, validate_by_filename  # noqa: E402
from factory.common.cld import Edge, build_graph, find_cycles, loops_from_cycles, circular_layout  # noqa: E402


st.set_page_config(page_title="CLD View", page_icon="🧠", layout="wide")
st.title("Causal Loop Diagram (CLD) — from approved claims")
st.caption("Approved claims → graph → loop detection (R/B) → export loops.yaml (audit-ready).")

CLAIMS_PATH = "configs/claims.yaml"
LOOPS_PATH = "configs/loops.yaml"

# -------------------------
# Load YAML
# -------------------------
claims_yaml = load_yaml(CLAIMS_PATH)
variables_yaml = load_yaml("configs/variables.yaml")

variables = variables_yaml.get("variables", []) or []
var_name_by_id = {v.get("id"): v.get("name", v.get("id")) for v in variables if isinstance(v, dict) and v.get("id")}

claims = claims_yaml.get("claims", []) or []
if not claims:
    st.warning("No claims found. Create claims using the Claim Review page, approve some, then Save.")
    st.stop()

# validate claims.yaml if you added schema (recommended)
try:
    validate_by_filename("claims.yaml", claims_yaml)
except Exception as e:
    st.error(f"claims.yaml business validation failed: {e}")
    st.stop()

# -------------------------
# Controls
# -------------------------
with st.sidebar:
    st.header("CLD controls")
    status_filter = st.multiselect(
        "Claim status to include",
        options=["approved", "proposed", "rejected"],
        default=["approved"],
    )
    max_loop_len = st.slider("Max loop length", min_value=2, max_value=12, value=8, step=1)
    st.caption("Tip: start with approved-only for clean loops.")

# -------------------------
# Parse edges
# -------------------------
edges: List[Edge] = []
bad_rows = []

for c in claims:
    if not isinstance(c, dict):
        continue
    if c.get("status") not in status_filter:
        continue

    cid = str(c.get("id", "")).strip()
    src = str(c.get("from_var", "")).strip()
    dst = str(c.get("to_var", "")).strip()
    polarity = str(c.get("polarity", "+")).strip()
    delay = int(c.get("delay_months") or 0)
    conf = float(c.get("confidence") or 0.6)

    if not cid or not src or not dst:
        bad_rows.append(c)
        continue

    edges.append(
        Edge(
            claim_id=cid,
            src=src,
            dst=dst,
            polarity="-" if polarity == "-" else "+",
            delay_months=max(delay, 0),
            confidence=min(max(conf, 0.0), 1.0),
        )
    )

if not edges:
    st.warning("No edges after filtering. Try including 'proposed' or approve some claims first.")
    st.stop()

# -------------------------
# Diagnostics
# -------------------------
nodes_set, adj = build_graph(edges)
nodes = sorted(nodes_set)

missing_from_variables = sorted([n for n in nodes if n not in var_name_by_id])
if missing_from_variables:
    st.warning(
        "Some nodes are not defined in configs/variables.yaml. "
        "They will still appear in the CLD, but you should add them for full traceability:\n\n"
        + "\n".join(missing_from_variables)
    )

c1, c2, c3 = st.columns(3)
c1.metric("Nodes", len(nodes))
c2.metric("Edges (claims)", len(edges))
c3.metric("Included statuses", ", ".join(status_filter))

st.divider()

# -------------------------
# Table of included claims
# -------------------------
st.subheader("Included claims")
df_claims = pd.DataFrame(
    [
        {
            "id": c.get("id"),
            "status": c.get("status"),
            "from_var": c.get("from_var"),
            "to_var": c.get("to_var"),
            "polarity": c.get("polarity"),
            "delay_months": c.get("delay_months"),
            "confidence": c.get("confidence"),
            "evidence_id": c.get("evidence_id"),
            "statement": c.get("statement"),
        }
        for c in claims
        if isinstance(c, dict) and c.get("status") in status_filter
    ]
)
st.dataframe(df_claims, use_container_width=True, height=260)

# -------------------------
# Loop detection
# -------------------------
edge_by_id: Dict[str, Edge] = {e.claim_id: e for e in edges}
cycles = find_cycles(adj, max_len=max_loop_len)
loops = loops_from_cycles(cycles, edge_by_id)

st.subheader("Detected loops")
if not loops:
    st.info("No loops detected (yet). Approve more claims that close feedback cycles, or increase max loop length.")
else:
    loops_df = pd.DataFrame(
        [
            {
                "loop_id": L.loop_id,
                "type": L.loop_type,
                "sign": "+1 (R)" if L.sign == 1 else "-1 (B)",
                "nodes": " → ".join(L.nodes + [L.nodes[0]]) if L.nodes else "",
                "edge_claim_ids": ", ".join(L.edge_claim_ids),
            }
            for L in loops
        ]
    )
    st.dataframe(loops_df, use_container_width=True, height=220)

# -------------------------
# CLD Visualization (Plotly)
# -------------------------
st.subheader("CLD graph")
pos = circular_layout(nodes, radius=1.0)

# edges as line segments
edge_x = []
edge_y = []
for e in edges:
    x0, y0 = pos.get(e.src, (0.0, 0.0))
    x1, y1 = pos.get(e.dst, (0.0, 0.0))
    edge_x += [x0, x1, None]
    edge_y += [y0, y1, None]

edge_trace = go.Scatter(
    x=edge_x,
    y=edge_y,
    mode="lines",
    hoverinfo="none",
)

# nodes as points
node_x = []
node_y = []
node_text = []
node_hover = []
for n in nodes:
    x, y = pos[n]
    node_x.append(x)
    node_y.append(y)
    node_text.append(var_name_by_id.get(n, n))
    node_hover.append(f"{var_name_by_id.get(n, n)}<br><b>{n}</b>")

node_trace = go.Scatter(
    x=node_x,
    y=node_y,
    mode="markers+text",
    text=node_text,
    textposition="bottom center",
    hovertext=node_hover,
    hoverinfo="text",
)

# edge labels (polarity + delay) at midpoint
ann = []
for e in edges:
    x0, y0 = pos.get(e.src, (0.0, 0.0))
    x1, y1 = pos.get(e.dst, (0.0, 0.0))
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    label = f"{e.polarity}  d={e.delay_months}m"
    ann.append(
        dict(
            x=xm,
            y=ym,
            text=label,
            showarrow=False,
            font=dict(size=10),
        )
    )

fig = go.Figure(data=[edge_trace, node_trace])
fig.update_layout(
    showlegend=False,
    margin=dict(l=10, r=10, t=10, b=10),
    annotations=ann,
    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    height=560,
)
st.plotly_chart(fig, use_container_width=True)

# -------------------------
# Export loops.yaml
# -------------------------
st.divider()
st.subheader("Export loops.yaml")

st.caption("This writes detected loops into configs/loops.yaml (with backups in runs/audit).")
export_btn = st.button("💾 Save loops.yaml (with backup)", type="primary")

if export_btn:
    loops_payload = {
        "loops": [
            {
                "id": L.loop_id,
                "type": L.loop_type,
                "sign": int(L.sign),
                "nodes": L.nodes,
                "edge_claim_ids": L.edge_claim_ids,
                "notes": "",
            }
            for L in loops
        ]
    }
    normalized = yaml_roundtrip_dump(loops_payload)
    backup = safe_write_with_backup(LOOPS_PATH, normalized, audit_dir="runs/audit")
    st.success(f"Saved {LOOPS_PATH}")
    st.caption(f"Backup created: {backup}")
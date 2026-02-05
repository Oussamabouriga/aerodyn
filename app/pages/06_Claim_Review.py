import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import streamlit as st

from factory.config.io import (
    load_yaml,
    yaml_roundtrip_dump,
    safe_write_with_backup,
    validate_by_filename,
    compute_diff,
)
from factory.extract.llm_claim_extractor import extract_claims
from factory.audit.log import append_audit_event

st.set_page_config(page_title="Claim Review", page_icon="✅", layout="wide")
st.title("Claim Review (Mechanism Extraction)")
st.caption("LLM proposes causal claims → humans approve/reject → saved to configs/claims.yaml (validated + auditable).")

# Load current claims
current = load_yaml("configs/claims.yaml") or {"claims": []}
claims = current.get("claims", []) or []

# Sidebar: input
with st.sidebar:
    st.header("Extract candidate claims")
    max_claims = st.slider("Max claims", 3, 20, 12, 1)
    run_extract = st.button("🤖 Extract from text", type="primary", use_container_width=True)

    st.divider()
    save_btn = st.button("💾 Save reviewed claims", use_container_width=True)
    reload_btn = st.button("↻ Reload from file", use_container_width=True)

if reload_btn:
    st.rerun()

st.subheader("1) Provide text to extract from")
text = st.text_area(
    "Paste notes / policy summary / meeting notes (unstructured is OK)",
    height=180,
    placeholder="Example: Incidents trigger backlash, backlash increases constraints, constraints reduce market access, ...",
)

# Run extraction
if run_extract:
    if not text.strip():
        st.warning("Paste some text first.")
    else:
        with st.spinner("Extracting claims with LLM…"):
            new_cfg = extract_claims(text, max_claims=max_claims)
        # Merge with existing claims (by id)
        existing_by_id = {c["id"]: c for c in claims if isinstance(c, dict) and "id" in c}
        for c in new_cfg.claims:
            existing_by_id[c.id] = c.model_dump()
        claims = list(existing_by_id.values())
        st.success(f"Added/updated {len(new_cfg.claims)} claims. Review below before saving.")

# Show editor
st.subheader("2) Review & approve/reject")
if not claims:
    st.info("No claims yet. Extract claims or add manually in configs/claims.yaml.")
    st.stop()

df = pd.DataFrame(claims)

# Ensure columns exist (stable UI)
wanted_cols = [
    "id",
    "status",
    "statement",
    "from_var",
    "to_var",
    "polarity",
    "delay_months",
    "evidence_id",
    "evidence_snippet",
    "confidence",
    "reviewer_note",
]
for c in wanted_cols:
    if c not in df.columns:
        df[c] = ""

edited = st.data_editor(
    df[wanted_cols],
    use_container_width=True,
    num_rows="dynamic",
    hide_index=True,
)

# Save
if save_btn:
    new_data = {"claims": edited.to_dict(orient="records")}

    # Business validation
    try:
        validate_by_filename("claims.yaml", new_data)
    except Exception as e:
        st.error(f"Validation FAILED: {e}")
        st.stop()

    # Diff preview (optional)
    diff = compute_diff(current, new_data)
    if diff:
        st.subheader("Diff preview (old → new)")
        st.json(diff)

    # Write with backup
    normalized = yaml_roundtrip_dump(new_data)
    backup = safe_write_with_backup("configs/claims.yaml", normalized, audit_dir="runs/audit")

    # Audit event
    append_audit_event(
        {
            "event": "claims_saved",
            "file": "configs/claims.yaml",
            "backup": str(backup),
            "counts": {
                "total": int(len(new_data["claims"])),
                "approved": int(sum(1 for c in new_data["claims"] if c.get("status") == "approved")),
                "rejected": int(sum(1 for c in new_data["claims"] if c.get("status") == "rejected")),
                "proposed": int(sum(1 for c in new_data["claims"] if c.get("status") == "proposed")),
            },
        }
    )

    st.success("Saved configs/claims.yaml (with backup + audit log).")
    st.caption(f"Backup: {backup}")
    st.rerun()
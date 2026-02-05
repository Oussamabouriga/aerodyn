import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st  # noqa: E402

from factory.extract.llm_config_agent import propose_change, generate_patch  # noqa: E402
from factory.config.io import load_yaml, compute_diff, safe_write_with_backup, validate_by_filename  # noqa: E402

st.set_page_config(page_title="Chat → Edit Model", page_icon="🤖", layout="wide")
st.title("Chat → Edit Model (LLM-assisted)")
st.caption("Describe changes in natural language → review → approve → apply safely (diff + validation + backups).")

if "proposal" not in st.session_state:
    st.session_state.proposal = None
if "patch_bundle" not in st.session_state:
    st.session_state.patch_bundle = None

user_request = st.text_area(
    "What do you want to change?",
    placeholder="Example: Constraints rise too fast. Make regulation more delayed and add a stricter-world scenario. Also document assumptions.",
    height=120,
)

colA, colB = st.columns([1, 1])
with colA:
    propose_btn = st.button("Generate proposal", type="primary", use_container_width=True)
with colB:
    clear_btn = st.button("Clear", use_container_width=True)

if clear_btn:
    st.session_state.proposal = None
    st.session_state.patch_bundle = None
    st.rerun()

if propose_btn and user_request.strip():
    with st.spinner("Thinking… (proposal)"):
        st.session_state.proposal = propose_change(user_request)
        st.session_state.patch_bundle = None

proposal = st.session_state.proposal
if not proposal:
    st.info("Write a request and click **Generate proposal**.")
    st.stop()

st.subheader("1) Assistant proposal")
st.markdown("**Human interpretation**")
st.write(proposal.intent_human)

st.markdown("**Technical interpretation**")
st.write(proposal.intent_technical)

st.markdown("**Files to edit**")
st.write([f"configs/{x}" for x in proposal.files_to_edit])

st.markdown("**Expected effects**")
st.write(proposal.expected_effects)

if proposal.questions:
    st.markdown("**Clarifying questions**")
    for q in proposal.questions:
        st.write(f"- {q}")

user_answers = st.text_area(
    "Your answers / constraints (optional)",
    placeholder="Example: reduce tightening rate by ~30% and add 6-month delay; keep baseline unchanged.",
    height=90,
)

approve = st.checkbox("I approve this plan. Generate patch.", value=False)

if approve:
    gen_patch_btn = st.button("Generate patch", use_container_width=True)
    if gen_patch_btn:
        with st.spinner("Generating YAML patch…"):
            st.session_state.patch_bundle = generate_patch(user_request, proposal, user_answers=user_answers)

bundle = st.session_state.patch_bundle
if not bundle:
    st.stop()

st.subheader("2) Patch preview")
st.write(bundle.summary)

# Show per-file diff + validation
for patch in bundle.patches:
    st.markdown(f"### {patch.path}")

    # old data
    old_data = load_yaml(patch.path)
    # try parse new YAML
    try:
        import yaml
        new_data = yaml.safe_load(patch.new_content) or {}
    except Exception as e:
        st.error(f"Patch YAML is invalid for {patch.path}: {e}")
        st.stop()

    # Business validate (blocks apply if invalid)
    try:
        filename = Path(patch.path).name
        validate_by_filename(filename, new_data)
        st.success("Business validation: OK")
    except Exception as e:
        st.error(f"Business validation FAILED: {e}")
        st.stop()

    diff = compute_diff(old_data, new_data)
    if diff:
        st.json(diff)
    else:
        st.info("No diff (same content).")

st.divider()
apply_btn = st.button("✅ Apply patch (with backups)", type="primary", use_container_width=True)

if apply_btn:
    backups = []
    for patch in bundle.patches:
        backup = safe_write_with_backup(patch.path, patch.new_content, audit_dir="runs/audit")
        backups.append(str(backup))
    st.success("Patch applied successfully.")
    st.caption("Backups created:")
    st.write(backups)
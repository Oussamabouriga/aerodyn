import sys
from pathlib import Path

# Make repo root importable (Streamlit pages run with different working dirs)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st  # noqa: E402

from factory.config.io import (  # noqa: E402
    load_yaml,
    yaml_roundtrip_load,
    yaml_roundtrip_dump,
    compute_diff,
    safe_write_with_backup,
    validate_by_filename,
)

st.set_page_config(page_title="Config Editor", page_icon="🛠️", layout="wide")

st.title("Config Editor")
st.caption("Safely edit YAML configs with YAML + business validation, diff, and backups (audit-ready).")

CONFIG_DIR = Path("configs")
AUDIT_DIR = Path("runs/audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

files = sorted([p.name for p in CONFIG_DIR.glob("*.yaml")])
if not files:
    st.error("No YAML files found in configs/")
    st.stop()

# -----------------------
# Layout
# -----------------------
colL, colR = st.columns([1, 2])

with colL:
    st.subheader("Select config")
    selected = st.selectbox("YAML file", files, key="selected_yaml_file")

    st.markdown("**Actions**")
    validate_btn = st.button("Validate", use_container_width=True)
    save_btn = st.button("Save (with backup)", type="primary", use_container_width=True)
    reset_btn = st.button("Reset editor to file", use_container_width=True)

    st.divider()
    st.caption("Backups are saved in `runs/audit/` with timestamps.")

# File path + original content/data
path = CONFIG_DIR / selected
original_text = path.read_text(encoding="utf-8") if path.exists() else ""
original_data = load_yaml(path)

# -----------------------
# Editor state
# -----------------------
if "editor_text" not in st.session_state:
    st.session_state.editor_text = ""

if "last_file" not in st.session_state:
    st.session_state.last_file = None

# If file changed (or first load), load its content
if st.session_state.last_file != selected:
    st.session_state.editor_text = original_text
    st.session_state.last_file = selected

# Reset button loads file again
if reset_btn:
    st.session_state.editor_text = original_text
    st.info("Editor reset to current file content.")

# -----------------------
# Editor UI
# -----------------------
with colR:
    st.subheader("YAML editor")
    edited_text = st.text_area(
        "Edit YAML",
        value=st.session_state.editor_text,
        height=560,
        help="Edit carefully. Use Validate before Save. Save is blocked if validation fails.",
    )
    st.session_state.editor_text = edited_text

# -----------------------
# Validate YAML + Business rules
# -----------------------
parsed_new = None
is_valid_yaml = False
is_valid_business = False
errors = []

if validate_btn or save_btn:
    # 1) YAML parse
    try:
        parsed_new = yaml_roundtrip_load(st.session_state.editor_text)
        is_valid_yaml = True
        st.success("✅ YAML syntax OK (parsed successfully).")
    except Exception as e:
        errors.append(f"YAML parsing error: {e}")
        st.error(f"❌ YAML parsing error: {e}")

    # 2) Business validation (only if YAML parsed)
    if is_valid_yaml and parsed_new is not None:
        try:
            validate_by_filename(selected, parsed_new)
            is_valid_business = True
            st.success("✅ Business validation OK (schema + rules).")
        except Exception as e:
            errors.append(f"Business validation failed: {e}")
            st.error(f"❌ Business validation failed: {e}")
            parsed_new = None  # block diff/save

# -----------------------
# Diff viewer (only if parsed)
# -----------------------
if parsed_new is not None:
    st.subheader("Diff (old → new)")
    diff = compute_diff(original_data, parsed_new)
    if diff:
        st.json(diff)
    else:
        st.info("No changes detected.")

# -----------------------
# Save (only if valid)
# -----------------------
if save_btn:
    if not is_valid_yaml:
        st.warning("Fix YAML syntax errors before saving.")
    elif not is_valid_business:
        st.warning("Fix business validation errors before saving.")
    elif parsed_new is None:
        st.warning("Nothing to save (parsing/validation failed).")
    else:
        # normalize formatting to keep YAML tidy & consistent
        normalized = yaml_roundtrip_dump(parsed_new)
        backup_path = safe_write_with_backup(path, normalized, audit_dir=AUDIT_DIR)

        st.success(f"✅ Saved `{selected}`")
        st.caption(f"Backup created: {backup_path}")

        # refresh original_data/text so next diff is correct
        original_text = path.read_text(encoding="utf-8")
        original_data = load_yaml(path)
        st.session_state.editor_text = original_text
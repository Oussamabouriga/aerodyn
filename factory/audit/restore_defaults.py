from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from factory.config.io import load_yaml, validate_by_filename, safe_write_with_backup


def restore_configs_from_defaults(
    defaults_dir: str | Path = "configs_defaults",
    target_dir: str | Path = "configs",
    audit_dir: str | Path = "runs/audit",
    files: List[str] | None = None,
) -> List[str]:
    """
    Restore YAML configs from configs_defaults/ to configs/.
    - Creates backups of current target files in runs/audit/
    - Validates restored content with business validation
    Returns list of restored filenames.
    """
    defaults_dir = Path(defaults_dir)
    target_dir = Path(target_dir)

    if not defaults_dir.exists():
        raise FileNotFoundError(f"Defaults folder not found: {defaults_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)

    # choose which files
    default_files = sorted([p.name for p in defaults_dir.glob("*.yaml")])
    if files is None:
        files = default_files
    else:
        # keep only existing in defaults
        files = [f for f in files if (defaults_dir / f).exists()]

    restored = []
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    for fname in files:
        src = defaults_dir / fname
        dst = target_dir / fname

        # Backup current dst (if exists) using our existing safe backup mechanism
        if dst.exists():
            safe_write_with_backup(dst, dst.read_text(encoding="utf-8"), audit_dir=audit_dir)

        # Copy default into place (atomic write style)
        new_text = src.read_text(encoding="utf-8")
        tmp = dst.with_suffix(".yaml.tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(dst)

        # Validate restored file (business rules)
        parsed = load_yaml(dst)
        validate_by_filename(fname, parsed)

        restored.append(fname)

    return restored
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml
from deepdiff import DeepDiff
from ruamel.yaml import YAML

# Business-schema validation (Step 4.2)
from factory.common.schemas import (
    VariablesConfig,
    ScenariosConfig,
    ModelConfig,
    RecommendationRulesConfig,
)


# -----------------------------
# YAML IO
# -----------------------------
def load_yaml(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def yaml_roundtrip_load(text: str) -> Any:
    y = YAML()
    return y.load(text)


def yaml_roundtrip_dump(data: Any) -> str:
    y = YAML()
    y.preserve_quotes = True
    y.width = 120
    from io import StringIO

    buf = StringIO()
    y.dump(data, buf)
    return buf.getvalue()


# -----------------------------
# Diff + Safe Save (audit)
# -----------------------------
def compute_diff(old: Any, new: Any) -> Dict[str, Any]:
    return DeepDiff(old, new, ignore_order=True).to_dict()


def safe_write_with_backup(
    path: str | Path,
    new_text: str,
    audit_dir: str | Path = "runs/audit",
) -> Path:
    path = Path(path)
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = audit_dir / f"{path.name}.{ts}.bak"

    # Backup old file (if exists)
    if path.exists():
        shutil.copy2(path, backup_path)

    # Atomic write
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(new_text, encoding="utf-8")
    tmp_path.replace(path)

    return backup_path


# -----------------------------
# Business validation (Step 4.2)
# -----------------------------
def validate_variables_cfg(data: Dict[str, Any]) -> VariablesConfig:
    """
    Validates configs/variables.yaml:
    - schema ok
    - bounds ok
    - stock must have 'initial'
    - param must have 'default'
    - variable IDs must be unique
    """
    cfg = VariablesConfig.model_validate(data)

    ids = [v.id for v in cfg.variables]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate variable ids found in variables.yaml")

    return cfg


def validate_scenarios_cfg(data: Dict[str, Any], variables_cfg: VariablesConfig) -> ScenariosConfig:
    """
    Validates configs/scenarios.yaml:
    - schema ok
    - scenario knobs must exist as param variables in variables.yaml
    """
    cfg = ScenariosConfig.model_validate(data)

    param_ids = {v.id for v in variables_cfg.variables if v.type == "param"}
    for s in cfg.scenarios:
        for k in s.knobs.keys():
            if k not in param_ids:
                raise ValueError(
                    f"Scenario '{s.id}' uses knob '{k}' which is not defined as a param in variables.yaml"
                )

    return cfg


def validate_model_cfg(data: Dict[str, Any]) -> ModelConfig:
    """
    Validates configs/model.yaml:
    - schema ok (model.time_step_months, horizon_years, parameters dict)
    """
    return ModelConfig.model_validate(data)


def validate_reco_rules_cfg(data: Dict[str, Any]) -> RecommendationRulesConfig:
    """
    Validates configs/recommendation_rules.yaml:
    - schema ok
    - rule IDs unique
    """
    cfg = RecommendationRulesConfig.model_validate(data)

    ids = [r.id for r in cfg.recommendation_rules]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate rule ids found in recommendation_rules.yaml")

    return cfg


def validate_by_filename(filename: str, parsed_yaml: Dict[str, Any]) -> None:
    """
    Convenience validator called by UI:
    - picks the correct business validation based on the YAML filename.
    Raises ValueError on invalid config.
    """
    if filename == "variables.yaml":
        validate_variables_cfg(parsed_yaml)
        return

    if filename == "scenarios.yaml":
        vars_cfg = validate_variables_cfg(load_yaml("configs/variables.yaml"))
        validate_scenarios_cfg(parsed_yaml, vars_cfg)
        return

    if filename == "model.yaml":
        validate_model_cfg(parsed_yaml)
        return

    if filename == "recommendation_rules.yaml":
        validate_reco_rules_cfg(parsed_yaml)
        return

    # For other YAML files (evidence.yaml, assumptions.yaml, etc.)
    # we currently only guarantee YAML syntax validity.
    return
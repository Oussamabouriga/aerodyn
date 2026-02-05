from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml
from deepdiff import DeepDiff
from ruamel.yaml import YAML


from factory.common.schemas import (
    VariablesConfig,
    ScenariosConfig,
    ModelConfig,
    RecommendationRulesConfig,
    ClaimsConfig,
    LoopsConfig,
    EvidenceConfig,
    AssumptionsConfig,
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
    if filename == "evidence.yaml":
        validate_evidence_cfg(parsed_yaml)
        return

    if filename == "assumptions.yaml":
        validate_assumptions_cfg(parsed_yaml)
        return
    
    if filename == "claims.yaml":
        validate_claims_cfg(parsed_yaml)
        return
    
    if filename == "claims.yaml":
        validate_claims_cfg(parsed_yaml)
        return

    if filename == "loops.yaml":
        validate_loops_cfg(parsed_yaml)
        return
    
    if filename == "structure.yaml":
        # for now: YAML syntax only; you can add strict schema later
        return

    if filename == "equations.yaml":
        # for now: YAML syntax only; you can add strict schema later
        return
    
    # For other YAML files (evidence.yaml, assumptions.yaml, etc.)
    # we currently only guarantee YAML syntax validity.
    return


def validate_evidence_cfg(data: Dict[str, Any]) -> EvidenceConfig:
    """
    Validates configs/evidence.yaml:
    - schema ok
    - evidence IDs unique
    """
    cfg = EvidenceConfig.model_validate(data)

    ids = [e.id for e in cfg.evidence]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate evidence ids found in evidence.yaml")

    return cfg


def validate_assumptions_cfg(data: Dict[str, Any]) -> AssumptionsConfig:
    """
    Validates configs/assumptions.yaml:
    - schema ok
    - assumption IDs unique
    - referenced evidence_ids exist in configs/evidence.yaml
    - linked_variables exist in configs/variables.yaml (optional but recommended)
    - linked_params exist in configs/variables.yaml as param (optional but recommended)
    """
    cfg = AssumptionsConfig.model_validate(data)

    # unique assumption IDs
    ids = [a.id for a in cfg.assumptions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate assumption ids found in assumptions.yaml")

    # evidence references must exist
    ev_cfg = validate_evidence_cfg(load_yaml("configs/evidence.yaml"))
    ev_ids = {e.id for e in ev_cfg.evidence}

    missing_evidence = []
    for a in cfg.assumptions:
        for eid in (a.evidence_ids or []):
            if eid not in ev_ids:
                missing_evidence.append((a.id, eid))

    if missing_evidence:
        msg = ", ".join([f"{aid}->{eid}" for aid, eid in missing_evidence])
        raise ValueError(f"assumptions.yaml references unknown evidence_ids: {msg}")

    # optional: validate linked variables/params against variables.yaml
    vars_cfg = validate_variables_cfg(load_yaml("configs/variables.yaml"))
    var_ids = {v.id for v in vars_cfg.variables}
    param_ids = {v.id for v in vars_cfg.variables if v.type == "param"}

    missing_vars = []
    missing_params = []
    for a in cfg.assumptions:
        for vid in (a.linked_variables or []):
            if vid not in var_ids:
                missing_vars.append((a.id, vid))
        for pid in (a.linked_params or []):
            if pid not in param_ids:
                missing_params.append((a.id, pid))

    if missing_vars:
        msg = ", ".join([f"{aid}->{vid}" for aid, vid in missing_vars])
        raise ValueError(f"assumptions.yaml references unknown linked_variables: {msg}")

    if missing_params:
        msg = ", ".join([f"{aid}->{pid}" for aid, pid in missing_params])
        raise ValueError(f"assumptions.yaml references unknown linked_params (param vars): {msg}")

    return cfg


def validate_claims_cfg(data: Dict[str, Any]) -> ClaimsConfig:
    """
    Validates configs/claims.yaml:
    - schema ok
    - claim IDs unique
    - from_var/to_var must exist in variables.yaml
    - evidence_id must exist in evidence.yaml
    """
    cfg = ClaimsConfig.model_validate(data)

    vars_cfg = validate_variables_cfg(load_yaml("configs/variables.yaml"))
    var_ids = {v.id for v in vars_cfg.variables}

    ev_cfg = validate_evidence_cfg(load_yaml("configs/evidence.yaml"))
    ev_ids = {e.id for e in ev_cfg.evidence}

    for c in cfg.claims:
        if c.from_var not in var_ids:
            raise ValueError(f"Claim '{c.id}' references unknown from_var '{c.from_var}'")
        if c.to_var not in var_ids:
            raise ValueError(f"Claim '{c.id}' references unknown to_var '{c.to_var}'")
        if c.evidence_id not in ev_ids:
            raise ValueError(f"Claim '{c.id}' references unknown evidence_id '{c.evidence_id}'")

    return cfg

def validate_claims_cfg(data: Dict[str, Any]) -> ClaimsConfig:
    """
    Validates configs/claims.yaml:
    - schema ok
    - claim IDs unique
    """
    cfg = ClaimsConfig.model_validate(data)
    ids = [c.id for c in cfg.claims]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate claim ids found in claims.yaml")
    return cfg


def validate_loops_cfg(data: Dict[str, Any]) -> LoopsConfig:
    """
    Validates configs/loops.yaml:
    - schema ok
    - loop IDs unique
    """
    cfg = LoopsConfig.model_validate(data)
    ids = [l.id for l in cfg.loops]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate loop ids found in loops.yaml")
    return cfg
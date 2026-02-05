from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from factory.config.io import load_yaml, validate_by_filename
from factory.assemble.safe_eval import SafeEval, clamp


@dataclass
class ModelSpec:
    time_step_months: int
    horizon_years: int
    parameters: Dict[str, float]

    stocks: List[str]
    flows: List[str]
    aux: List[str]

    stock_inflows: Dict[str, List[str]]
    stock_outflows: Dict[str, List[str]]
    stock_clamps: Dict[str, Dict[str, float]]

    equations: Dict[str, str]  # var_id -> formula
    equation_kind: Dict[str, str]  # var_id -> 'flow' or 'aux'


def _parse_structure() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    data = load_yaml("configs/structure.yaml")
    validate_by_filename("structure.yaml", data)  # if you add validation later, still ok
    structure = data.get("structure") or {}
    stocks = structure.get("stocks") or []
    return structure, stocks


def _parse_equations() -> List[Dict[str, Any]]:
    data = load_yaml("configs/equations.yaml")
    validate_by_filename("equations.yaml", data)  # if you add validation later, still ok
    return data.get("equations") or []


def build_model_spec(knobs: Dict[str, float] | None = None) -> ModelSpec:
    knobs = knobs or {}

    # model core config
    model_cfg = load_yaml("configs/model.yaml") or {}
    validate_by_filename("model.yaml", model_cfg)
    core = (model_cfg.get("model") or {})
    time_step_months = int(core.get("time_step_months", 1))
    horizon_years = int(core.get("horizon_years", 10))
    parameters = dict(core.get("parameters") or {})

    # variables define defaults/bounds/initial
    variables_cfg = load_yaml("configs/variables.yaml") or {}
    validate_by_filename("variables.yaml", variables_cfg)
    variables = variables_cfg.get("variables") or []

    # apply param defaults
    for v in variables:
        if isinstance(v, dict) and v.get("type") == "param":
            vid = v.get("id")
            if vid and "default" in v and vid not in parameters:
                parameters[vid] = float(v["default"])

    # apply knobs override (scenario + sliders)
    for k, val in knobs.items():
        parameters[k] = float(val)

    # structure
    structure, stocks_list = _parse_structure()
    flows = structure.get("flows") or []
    aux = structure.get("aux") or []

    stock_ids = [s.get("id") for s in stocks_list if isinstance(s, dict)]
    stock_inflows = {s["id"]: list(s.get("inflows") or []) for s in stocks_list if isinstance(s, dict) and s.get("id")}
    stock_outflows = {s["id"]: list(s.get("outflows") or []) for s in stocks_list if isinstance(s, dict) and s.get("id")}
    stock_clamps = {s["id"]: dict(s.get("clamp") or {}) for s in stocks_list if isinstance(s, dict) and s.get("id")}

    # equations
    eq_rows = _parse_equations()
    equations: Dict[str, str] = {}
    kinds: Dict[str, str] = {}

    for row in eq_rows:
        if not isinstance(row, dict):
            continue
        vid = row.get("id")
        if not vid:
            continue
        equations[vid] = str(row.get("formula", "")).strip()
        kinds[vid] = str(row.get("kind", "")).strip()

    # basic completeness checks
    needed = set(flows) | set(aux)
    missing_eq = sorted([x for x in needed if x not in equations])
    if missing_eq:
        raise ValueError(f"Missing equations for: {missing_eq}. Add them in configs/equations.yaml")

    return ModelSpec(
        time_step_months=time_step_months,
        horizon_years=horizon_years,
        parameters=parameters,
        stocks=stock_ids,
        flows=list(flows),
        aux=list(aux),
        stock_inflows=stock_inflows,
        stock_outflows=stock_outflows,
        stock_clamps=stock_clamps,
        equations=equations,
        equation_kind=kinds,
    )


def initial_state_from_variables() -> Dict[str, float]:
    variables_cfg = load_yaml("configs/variables.yaml") or {}
    variables = variables_cfg.get("variables") or []
    state: Dict[str, float] = {}
    for v in variables:
        if isinstance(v, dict) and v.get("type") == "stock":
            vid = v.get("id")
            if vid is not None:
                state[vid] = float(v.get("initial", 0.0))
    return state


def simulate(spec: ModelSpec) -> List[Dict[str, float]]:
    """
    Euler integration.
    Flows in equations.yaml are defined per YEAR.
    dt_years = time_step_months / 12
    """
    evaluator = SafeEval()
    dt_years = spec.time_step_months / 12.0
    steps = int(spec.horizon_years * 12 / spec.time_step_months)

    state = initial_state_from_variables()
    # ensure all stocks exist
    for s in spec.stocks:
        state.setdefault(s, 0.0)

    rows: List[Dict[str, float]] = []

    for step in range(steps + 1):
        year = step * dt_years

        # build env for equations
        env: Dict[str, float] = {}
        env.update(spec.parameters)
        env.update(state)
        env["year"] = float(year)
        env["dt_years"] = float(dt_years)

        # compute aux + flows (order: aux first then flows is fine; formulas can refer to flows if needed)
        computed: Dict[str, float] = {}

        # compute aux
        for var_id in spec.aux:
            expr = spec.equations[var_id]
            computed[var_id] = float(evaluator.eval(expr, {**env, **computed}))

        # compute flows (per year)
        for var_id in spec.flows:
            expr = spec.equations[var_id]
            computed[var_id] = float(evaluator.eval(expr, {**env, **computed}))

        # record row before updating stocks (current state + computed)
        row = {"year": float(year)}
        row.update({k: float(v) for k, v in state.items()})
        row.update({k: float(v) for k, v in computed.items()})
        rows.append(row)

        # update stocks
        new_state = dict(state)
        for stock_id in spec.stocks:
            inflows = spec.stock_inflows.get(stock_id, [])
            outflows = spec.stock_outflows.get(stock_id, [])
            net = sum(computed.get(f, 0.0) for f in inflows) - sum(computed.get(f, 0.0) for f in outflows)

            new_val = float(state.get(stock_id, 0.0) + net * dt_years)

            # clamp if specified
            cl = spec.stock_clamps.get(stock_id) or {}
            if "min" in cl:
                new_val = max(float(cl["min"]), new_val)
            if "max" in cl:
                new_val = min(float(cl["max"]), new_val)

            new_state[stock_id] = new_val

        state = new_state

    return rows
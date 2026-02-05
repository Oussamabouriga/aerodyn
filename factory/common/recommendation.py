from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import yaml


@dataclass
class Recommendation:
    label: str        # INVEST / PAUSE / PIVOT
    severity: str     # success / warning / error
    reason: str


def _load_rules() -> Dict[str, Any]:
    path = Path("configs/recommendation_rules.yaml")
    if not path.exists():
        raise FileNotFoundError("configs/recommendation_rules.yaml not found")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def recommend(final_metrics: Dict[str, float], rule_id: str = "rec_rule_v1") -> Recommendation:
    data = _load_rules()
    rules = data.get("recommendation_rules", [])
    rule = next((r for r in rules if r.get("id") == rule_id), None)
    if not rule:
        raise ValueError(f"Rule '{rule_id}' not found in configs/recommendation_rules.yaml")

    th = rule.get("thresholds", {})

    deals = float(final_metrics.get("deals_won_per_year", 0.0))
    rep = float(final_metrics.get("reputation_capital", 0.0))
    cons = float(final_metrics.get("regulatory_constraint_level", 1.0))
    access = float(final_metrics.get("market_access_factor", 0.0))

    # Thresholds
    min_deals = float(th.get("min_deals_won_per_year", 2.0))
    min_rep = float(th.get("min_reputation", 0.35))
    max_cons = float(th.get("max_constraints", 0.80))
    min_access = float(th.get("min_market_access", 0.20))

    # Decision logic (simple v0.1)
    if cons > max_cons or access < min_access:
        return Recommendation(
            label="PAUSE",
            severity="error",
            reason="Regulatory constraints too high and/or market access too low.",
        )

    if rep < min_rep:
        return Recommendation(
            label="PIVOT",
            severity="warning",
            reason="Reputation too low: prioritize governance, transparency, and safer positioning.",
        )

    if deals >= min_deals:
        return Recommendation(
            label="INVEST",
            severity="success",
            reason="Business performance acceptable under constraints; proceed with controlled investment.",
        )

    return Recommendation(
        label="PIVOT",
        severity="warning",
        reason="Insufficient deal performance: adjust strategy or revisit assumptions.",
    )
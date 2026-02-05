from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd
from openai import OpenAI

from factory.config.io import load_yaml


# -----------------------------
# Guardrails: high-stakes domain
# -----------------------------
SYSTEM_GUARDRAILS = """
You are an AI analyst embedded in a strategic "model factory" dashboard for a defense manufacturer.
Your role is BUSINESS & RISK DECISION SUPPORT ONLY.

Hard constraints:
- Do NOT provide operational targeting guidance, weapon optimization, lethal decision procedures, or advice that enables harm.
- Focus on corporate strategy: revenue/pipeline, regulation/export constraints, reputation/public opinion, risk management.
- Be explicit about uncertainty, assumptions, and model limitations.
- Keep language CEO-friendly: concise, structured, actionable.
"""


@dataclass
class AnalystResult:
    executive_summary: list[str]
    key_drivers: list[str]
    risks_and_constraints: list[str]
    recommended_actions: list[dict]
    confidence: str
    limitations: list[str]


def _ensure_openai_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing in environment (.env not loaded).")
    return OpenAI()


def _get_model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o")


def _safe_last(df: pd.DataFrame) -> Dict[str, float]:
    last = df.iloc[-1]
    keys = [
        "deals_won_per_year",
        "opportunity_pipeline",
        "reputation_capital",
        "regulatory_constraint_level",
        "market_access_factor",
        "public_backlash_index",
        "ai_rnd_capability",
        "win_rate",
    ]
    out: Dict[str, float] = {}
    for k in keys:
        if k in df.columns:
            out[k] = float(last[k])
    out["year"] = float(last["year"]) if "year" in df.columns else float(len(df) - 1)
    return out


def _delta(selected_last: Dict[str, float], baseline_last: Optional[Dict[str, float]]) -> Dict[str, float]:
    if not baseline_last:
        return {}
    d: Dict[str, float] = {}
    for k, v in selected_last.items():
        if k in baseline_last and k != "year":
            d[k] = float(v) - float(baseline_last[k])
    return d


def analyze_run(
    df: pd.DataFrame,
    *,
    scenario_id: str,
    knobs_used: Dict[str, Any],
    recommendation: Dict[str, Any],
    baseline_df: Optional[pd.DataFrame] = None,
) -> AnalystResult:
    """
    Returns an executive narrative + actions based on model outputs.
    Uses structured JSON output (schema) for reliability.
    """
    client = _ensure_openai_client()
    model = _get_model_name()

    assumptions = load_yaml("configs/assumptions.yaml").get("assumptions", [])
    decision_questions = load_yaml("configs/decision_questions.yaml").get("decision_questions", [])
    rec_rules = load_yaml("configs/recommendation_rules.yaml").get("recommendation_rules", [])

    selected_last = _safe_last(df)
    baseline_last = _safe_last(baseline_df) if baseline_df is not None else None
    deltas = _delta(selected_last, baseline_last)

    context = {
        "scenario_id": scenario_id,
        "knobs_used": knobs_used,
        "selected_final_metrics": selected_last,
        "baseline_final_metrics": baseline_last,
        "delta_vs_baseline": deltas,
        "rule_based_recommendation": recommendation,
        "decision_questions": decision_questions[:3],  # keep short
        "assumptions": assumptions[:10],               # keep short
        "recommendation_rules": rec_rules[:3],         # keep short
        "notes": "All values are from an internal toy system-dynamics model v0.1 (not calibrated).",
    }

    # JSON schema for structured, reliable UI rendering
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "executive_summary": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 7},
            "key_drivers": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
            "risks_and_constraints": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 10},
            "recommended_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {"type": "string"},
                        "rationale": {"type": "string"},
                        "expected_effect": {"type": "string"},
                        "knob_changes": {
                            "type": "object",
                            "additionalProperties": {"type": "number"},
                        },
                    },
                    "required": ["action", "rationale", "expected_effect", "knob_changes"],
                },
                "minItems": 3,
                "maxItems": 6,
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "limitations": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
        },
        "required": [
            "executive_summary",
            "key_drivers",
            "risks_and_constraints",
            "recommended_actions",
            "confidence",
            "limitations",
        ],
    }

    instructions = f"""
{SYSTEM_GUARDRAILS}

Task:
Given the system-dynamics outputs + scenario knobs, produce a CEO-grade analysis:
- Explain what happened, why it happened (drivers), and what it implies.
- Tie to reputation/regulation/market access/contract pipeline.
- Use baseline comparison if provided.
- Provide 3–6 recommended actions expressed as knob changes (numbers) + rationale.
- Mention limitations clearly.

Output MUST be valid JSON matching the schema exactly.
"""

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": str(context)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "aerodyn_llm_analysis",
                "schema": schema,
                "strict": True,
            }
        },
        temperature=0.2,
    )

    data = resp.output_text
    # output_text is JSON text; parse safely:
    import json
    obj = json.loads(data)

    return AnalystResult(
        executive_summary=obj["executive_summary"],
        key_drivers=obj["key_drivers"],
        risks_and_constraints=obj["risks_and_constraints"],
        recommended_actions=obj["recommended_actions"],
        confidence=obj["confidence"],
        limitations=obj["limitations"],
    )
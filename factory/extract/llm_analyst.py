from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI


@dataclass
class LLMAnalysis:
    executive_summary: List[str]
    key_drivers: List[str]
    risks_and_constraints: List[str]
    recommended_actions: List[Dict[str, Any]]
    confidence: str
    limitations: List[str]


def _ensure_client() -> OpenAI:
    load_dotenv()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in .env (or environment).")
    return OpenAI(api_key=api_key)


def _model_name() -> str:
    load_dotenv()
    return (os.getenv("OPENAI_MODEL") or "gpt-4o").strip().strip('"').strip("'")


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _final_metrics(df: pd.DataFrame) -> Dict[str, float]:
    last = df.iloc[-1]
    keys = [
        "deals_won_per_year",
        "opportunity_pipeline",
        "reputation_capital",
        "regulatory_constraint_level",
        "market_access_factor",
        "public_backlash_index",
    ]
    return {k: _safe_float(last.get(k, 0.0)) for k in keys}


def _baseline_delta(current: Dict[str, float], baseline: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for k, v in current.items():
        out[k] = v - _safe_float(baseline.get(k, 0.0))
    return out


# -------------------------
# STRICT schema (OpenAI-compatible)
# IMPORTANT: No dynamic dicts (additionalProperties) for required object fields.
# Use a list of knob changes instead.
# -------------------------
AERODYN_ANALYSIS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "executive_summary": {"type": "array", "items": {"type": "string"}},
        "key_drivers": {"type": "array", "items": {"type": "string"}},
        "risks_and_constraints": {"type": "array", "items": {"type": "string"}},
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
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "knob_id": {"type": "string"},
                                "value": {"type": "number"},
                            },
                            "required": ["knob_id", "value"],
                        },
                    },
                },
                "required": ["action", "rationale", "expected_effect", "knob_changes"],
            },
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "limitations": {"type": "array", "items": {"type": "string"}},
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


def analyze_run(
    df: pd.DataFrame,
    scenario_id: str,
    knobs_used: Dict[str, Any],
    recommendation: Dict[str, Any],
    baseline_df: Optional[pd.DataFrame] = None,
) -> LLMAnalysis:
    client = _ensure_client()
    model = _model_name()

    cur = _final_metrics(df)
    base = _final_metrics(baseline_df) if baseline_df is not None else None
    delta = _baseline_delta(cur, base) if base is not None else None

    payload = {
        "scenario_id": scenario_id,
        "knobs_used": knobs_used,
        "final_metrics": cur,
        "baseline_final_metrics": base,
        "delta_vs_baseline": delta,
        "rule_recommendation": recommendation,
        "time_horizon_years": float(df["year"].max()) if "year" in df.columns else None,
    }

    system = (
        "You are an external System Modeling & AI Task Force writing a CEO-grade analysis for AeroDyn.\n"
        "Be concise, decision-oriented, and avoid technical jargon.\n"
        "Use ONLY the provided simulation outputs.\n"
        "Return ONLY valid JSON that matches the provided schema."
    )

    user = (
        "Analyze this run and provide:\n"
        "- Executive summary bullets (3–5)\n"
        "- Key drivers (3–6)\n"
        "- Risks & constraints (3–6)\n"
        "- Recommended actions (2–5). Each action MUST include knob_changes as a LIST of {knob_id, value}.\n"
        "  Use knob_id from knobs_used keys when possible.\n"
        "- Confidence: low/medium/high\n"
        "- Limitations (3–6)\n\n"
        f"DATA:\n{json.dumps(payload, indent=2)}"
    )

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "aerodyn_llm_analysis",
                "schema": AERODYN_ANALYSIS_SCHEMA,
                "strict": True,
            }
        },
    )

    raw = (resp.output_text or "").strip()
    if not raw:
        raise RuntimeError("Empty LLM response. Try again.")

    try:
        data = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"LLM returned non-JSON output: {e}\n\nRAW:\n{raw}")

    return LLMAnalysis(
        executive_summary=data["executive_summary"],
        key_drivers=data["key_drivers"],
        risks_and_constraints=data["risks_and_constraints"],
        recommended_actions=data["recommended_actions"],
        confidence=data["confidence"],
        limitations=data["limitations"],
    )
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from factory.config.io import load_yaml
from factory.common.schemas import ClaimsConfig


def _strip_quotes(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1].strip()
    return s


def _ensure_client() -> tuple[OpenAI, str]:
    load_dotenv(override=True)
    api_key = _strip_quotes(os.getenv("OPENAI_API_KEY", "")) or ""
    model = _strip_quotes(os.getenv("OPENAI_MODEL", "gpt-4o")) or "gpt-4o"

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in .env (or environment).")

    return OpenAI(api_key=api_key), model


def _safe_json_extract(text: str) -> Dict[str, Any]:
    """
    Expect the model to return JSON only, but tolerate extra text by extracting the first {...}.
    """
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("LLM did not return JSON.")
    return json.loads(m.group(0))


def _next_claim_id(existing_ids: set[str]) -> str:
    # CLM_0001, CLM_0002, ...
    n = 1
    while True:
        cid = f"CLM_{n:04d}"
        if cid not in existing_ids:
            return cid
        n += 1


def extract_claims(
    text: str,
    max_claims: int = 12,
    focus: str = "AeroDyn lethal AI strategy: backlash, regulation, market access, pipeline, reputation, capability.",
) -> ClaimsConfig:
    """
    Takes unstructured text (notes, docs, bullet points) and returns ClaimsConfig (proposed claims).
    Uses existing variables + evidence IDs to constrain outputs.
    """
    client, model = _ensure_client()

    variables = load_yaml("configs/variables.yaml").get("variables", [])
    var_ids = [v.get("id") for v in variables if isinstance(v, dict) and v.get("id")]

    evidence = load_yaml("configs/evidence.yaml").get("evidence", [])
    evidence_ids = [e.get("id") for e in evidence if isinstance(e, dict) and e.get("id")]

    existing_claims = load_yaml("configs/claims.yaml").get("claims", [])
    existing_ids = {c.get("id") for c in existing_claims if isinstance(c, dict) and c.get("id")}

    system = f"""
You are a system dynamics analyst. Extract causal claims from text for a model.
Return ONLY valid JSON.
Constraints:
- Use only variables from this list: {var_ids}
- Use only evidence_id from this list: {evidence_ids}
- Max claims: {max_claims}
- Each claim must include:
  id (leave empty string if unknown),
  status="proposed",
  statement,
  from_var,
  to_var,
  polarity ("+" or "-"),
  delay_months (0..120),
  evidence_id,
  evidence_snippet,
  confidence (0..1),
  reviewer_note (empty)
Focus: {focus}

Output JSON schema:
{{
  "claims": [
    {{
      "id": "",
      "status": "proposed",
      "statement": "...",
      "from_var": "…",
      "to_var": "…",
      "polarity": "+",
      "delay_months": 0,
      "evidence_id": "…",
      "evidence_snippet": "...",
      "confidence": 0.5,
      "reviewer_note": ""
    }}
  ]
}}
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text.strip()},
        ],
        temperature=0.2,
    )

    raw = resp.choices[0].message.content or ""
    data = _safe_json_extract(raw)

    # Fill IDs if missing
    claims = data.get("claims", [])
    for c in claims:
        if not c.get("id"):
            c["id"] = _next_claim_id(existing_ids)
            existing_ids.add(c["id"])

    cfg = ClaimsConfig.model_validate({"claims": claims})
    return cfg
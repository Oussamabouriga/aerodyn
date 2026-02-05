from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

CONFIG_DIR = Path("configs")


@dataclass
class Proposal:
    intent_human: str
    intent_technical: str
    files_to_edit: List[str]
    expected_effects: List[str]
    questions: List[str]


@dataclass
class FilePatch:
    path: str          # e.g. "configs/model.yaml"
    new_content: str   # full YAML content for that file


@dataclass
class PatchBundle:
    summary: str
    patches: List[FilePatch]


def _available_yaml_files() -> List[str]:
    return sorted([p.name for p in CONFIG_DIR.glob("*.yaml")])


def _read_files(files: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for f in files:
        p = CONFIG_DIR / f
        out[f] = p.read_text(encoding="utf-8") if p.exists() else ""
    return out


def _ensure_openai_client():
    """
    Lazy import to avoid crashing Streamlit if openai isn't installed yet.
    """
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "OpenAI SDK not installed. Run: pip install openai>=1.0.0"
        ) from e

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in .env (or environment).")

    return OpenAI(api_key=api_key)


def _model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o")


def propose_change(user_request: str) -> Proposal:
    """
    Stage A: Interpret vague user request -> propose plan + files + effects + questions.
    """
    client = _ensure_openai_client()
    model = _model_name()
    available = _available_yaml_files()

    schema = {
        "name": "config_change_proposal",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "intent_human": {"type": "string"},
                "intent_technical": {"type": "string"},
                "files_to_edit": {"type": "array", "items": {"type": "string"}},
                "expected_effects": {"type": "array", "items": {"type": "string"}},
                "questions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["intent_human", "intent_technical", "files_to_edit", "expected_effects", "questions"],
        },
        "strict": True,
    }

    instructions = f"""
You are the AeroDyn Model Factory configuration assistant.

Your job:
- Understand the user's intent even if vague.
- Propose a technical plan and which YAML files to edit under configs/.
- Explain expected effects on the model and dashboard.
- Ask clarifying questions ONLY when needed to avoid wrong edits.

Constraints:
- You may only propose edits to these existing YAML files: {available}
- Output must be valid JSON matching the provided schema (no extra keys).
"""

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_request},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "config_change_proposal",
                "schema": schema["schema"],  # <-- IMPORTANT: pass the inner schema
                "strict": True,
            }
        },
        temperature=0.2,
    )

    import json
    obj = json.loads(resp.output_text)

    # keep only existing YAML names
    files = [f for f in obj["files_to_edit"] if f in available]

    return Proposal(
        intent_human=obj["intent_human"],
        intent_technical=obj["intent_technical"],
        files_to_edit=files,
        expected_effects=obj["expected_effects"],
        questions=obj["questions"],
    )


def generate_patch(user_request: str, proposal: Proposal, user_answers: Optional[str] = "") -> PatchBundle:
    """
    Stage B: Generate full updated YAML content for each file in proposal.files_to_edit.
    """
    client = _ensure_openai_client()
    model = _model_name()

    current_files = _read_files(proposal.files_to_edit)

    schema = {
        "name": "config_patch_bundle",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "patches": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "path": {"type": "string"},
                            "new_content": {"type": "string"},
                        },
                        "required": ["path", "new_content"],
                    },
                },
            },
            "required": ["summary", "patches"],
        },
        "strict": True,
    }

    instructions = """
You generate safe YAML patches for AeroDyn Model Factory.

Rules:
- Output must match JSON schema exactly.
- Only edit the provided files under configs/.
- For each file, return the FULL YAML content (not a diff).
- Keep changes minimal and consistent with the user's intent.
- Do NOT invent new files. Do NOT change unrelated fields.
"""

    context = {
        "user_request": user_request,
        "proposal": {
            "intent_human": proposal.intent_human,
            "intent_technical": proposal.intent_technical,
            "files_to_edit": proposal.files_to_edit,
            "expected_effects": proposal.expected_effects,
            "questions": proposal.questions,
        },
        "user_answers": user_answers or "",
        "current_files": current_files,
    }
    
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": yaml.safe_dump(context, sort_keys=False)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "config_patch_bundle",
                "schema": schema["schema"],
                "strict": True,
            }
        },
        temperature=0.2,
    )

    import json
    obj = json.loads(resp.output_text)

    patches: List[FilePatch] = []
    for p in obj["patches"]:
        patches.append(FilePatch(path=p["path"], new_content=p["new_content"]))

    return PatchBundle(summary=obj["summary"], patches=patches)
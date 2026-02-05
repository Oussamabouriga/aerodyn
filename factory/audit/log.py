from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def append_audit_event(event: Dict[str, Any], audit_dir: str | Path = "runs/audit") -> Path:
    """
    Appends one JSON line event to runs/audit/audit_log.jsonl
    """
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)

    path = audit_dir / "audit_log.jsonl"
    event = dict(event)
    event["ts_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return path
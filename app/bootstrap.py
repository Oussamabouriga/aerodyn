from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (works regardless of working directory)
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=False)
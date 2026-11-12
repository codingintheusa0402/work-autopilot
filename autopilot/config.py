"""Paths and settings. Everything personal lives under WORKSPACE (gitignored)."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
WORKSPACE = Path(os.environ.get("WA_WORKSPACE", ROOT / "workspace")).expanduser().resolve()

RAW_DIR = WORKSPACE / "raw"                 # screenpipe data dir (screens). Deleted after analysis.
OBS_DIR = WORKSPACE / "observations"        # minimal metadata export (no screen text, no images)
REPORT_DIR = WORKSPACE / "reports"
SPEC_DIR = WORKSPACE / "specs"              # interview answers, one file per automation
AUTO_DIR = WORKSPACE / "automations"        # the user's own automations (kept local)
LOG_DIR = WORKSPACE / "logs"
BACKUP_DIR = WORKSPACE / "backups"          # file snapshots that make runs reversible
DRYRUN_DIR = WORKSPACE / "dryrun"           # where dry-runs write their would-be output
STATE_DIR = WORKSPACE / "state"

ALL_DIRS = [RAW_DIR, OBS_DIR, REPORT_DIR, SPEC_DIR, AUTO_DIR, LOG_DIR, BACKUP_DIR, DRYRUN_DIR, STATE_DIR]


def ensure_workspace() -> None:
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load_config() -> dict:
    cfg = _read_json(CONFIG_DIR / "privacy.default.json")
    cfg.update(_read_json(WORKSPACE / "config.json"))
    # local_only can never be switched off from config: the code has no cloud path.
    cfg["local_only"] = True
    return cfg


def load_hints() -> list[dict]:
    custom = WORKSPACE / "task_hints.json"
    data = _read_json(custom) or _read_json(CONFIG_DIR / "task_hints.json")
    return data.get("categories", [])

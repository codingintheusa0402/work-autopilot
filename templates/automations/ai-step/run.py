"""Template: an AI step, only where judgment is needed (classify, summarize, draft).

Uses the agent CLI you already have: `claude -p` (Claude Code) or `codex exec` (Codex).
What leaves your computer: ONLY the text you pass in `prompt` below, to that agent's provider.
Never pass screenshots, recordings, passwords or ID numbers. Keep the input minimal.
Drafts are written locally; sending them is a separate risky action that needs approval.
"""
import json
import shutil
import subprocess
from pathlib import Path

from autopilot.sdk import Run

with Run() as run:
    m = json.loads(Path("automation.json").read_text(encoding="utf-8"))
    agent = m.get("params", {}).get("agent", "claude")
    cmd = {"claude": ["claude", "-p"], "codex": ["codex", "exec"]}[agent]
    if not shutil.which(cmd[0]):
        run.log(f"{cmd[0]} CLI not found")
        raise SystemExit(2)
    text = "..."            # TODO(build): the minimal input text
    prompt = "Classify this as A/B/C and answer with one letter:\n" + run.guard_value(text)
    out = subprocess.run(cmd + [prompt], capture_output=True, text=True, timeout=300).stdout.strip()
    run.write_text(Path("out") / "ai_result.txt", out)

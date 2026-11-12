"""Template: plain script (files, spreadsheets, CSV, local apps).
Every side effect goes through `run` → dry-run by default, logged, reversible."""
import json
import os
from pathlib import Path

from autopilot.sdk import Run

with Run() as run:
    m = json.loads(Path("automation.json").read_text(encoding="utf-8"))
    p = {k: v.replace("{workspace}", os.environ["WA_WORKSPACE"]) for k, v in m.get("params", {}).items()}
    # TODO(build): implement the steps from workspace/specs/<id>.md
    # run.move(src, dst) · run.copy(src, dst) · run.write_text(path, text) · run.delete(path)
    # run.risky("send_message", "what exactly", lambda: ...)   ← only after the user approves
    run.log("template: nothing to do yet")

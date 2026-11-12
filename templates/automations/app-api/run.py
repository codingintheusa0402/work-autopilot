"""Template: call an app's official API (Google Sheets, Microsoft Graph, Slack, Notion, ERP REST …).

Tokens: the USER creates the token and puts it in an environment variable or the OS keychain.
Never write tokens into this folder, automation.json, logs or git. Read them at run time only.
"""
import json
import os
import urllib.request
from pathlib import Path

from autopilot.sdk import Run

with Run() as run:
    m = json.loads(Path("automation.json").read_text(encoding="utf-8"))
    env_name = m.get("params", {}).get("token_env", "WA_APP_TOKEN")
    token = os.environ.get(env_name)
    if not token:
        run.log(f"{env_name} 가 설정되지 않았습니다. 사용자가 직접 설정해야 합니다.")
        raise SystemExit(2)

    def get(url):
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    # TODO(build): reads are safe in dry-run. Writes that leave this computer:
    # run.risky("submit_form", "시트에 N행 추가", lambda: post(...))
    run.log("template: nothing to do yet")

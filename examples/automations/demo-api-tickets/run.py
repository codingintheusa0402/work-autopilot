"""DEMO (synthetic): read orders from an app API, find late ones, write a local report,
and (only if approved) open one ticket per late order through the API.
The token comes from an environment variable the USER sets; it is never stored here."""
import json
import os
import urllib.request
from pathlib import Path

from autopilot.sdk import Run

with Run() as run:
    m = json.loads(Path("automation.json").read_text(encoding="utf-8"))
    prm = m["params"]
    token = os.environ.get(prm["token_env"])
    if not token:
        run.log(f"{prm['token_env']} 가 없습니다 — 사용자가 직접 설정해야 합니다.")
        raise SystemExit(2)

    def call(method, path, body=None):
        req = urllib.request.Request(prm["base_url"] + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())

    orders = call("GET", "/orders")["orders"]
    late = [o for o in orders if o["days_late"] > 2]
    run.log(f"주문 {len(orders)}건 중 지연 {len(late)}건")
    lines = ["order,customer,days_late"] + [f"{o['order']},{o['customer']},{o['days_late']}" for o in late]
    run.write_text(prm["report_csv"].replace("{workspace}", os.environ["WA_WORKSPACE"]), "\n".join(lines) + "\n")
    for o in late:
        run.risky("submit_form", f"티켓 생성: {o['order']} ({o['days_late']}일 지연)",
                  lambda o=o: call("POST", "/tickets", {"order": o["order"], "reason": "late"}))

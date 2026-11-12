#!/usr/bin/env python3
"""End-to-end check of the browser-cdp, app-api and ai-step templates on FAKE tasks.

For each demo automation: `wa new` from the template → overlay the demo code → spec →
`wa test` (lint + dry-run) → `wa run --live` on fake data → `wa undo` → verify the undo.
Everything runs against a local fake server (127.0.0.1:8765) and a throwaway headless Chrome
on its own port (9333) with its own temporary profile. Risky steps (submit/send) are NOT
approved here, so they must show up as BLOCKED and the fake server must receive nothing.

    python3 tools/e2e_templates.py            # uses a temp workspace, cleans up after itself
    WA_NO_AI=1 python3 tools/e2e_templates.py # skip the real `claude -p` call
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT_HTTP, PORT_CDP = 8765, 9333
FAKE_TOKEN = "mock-token-for-local-fake-api"      # not a secret: the fake server below accepts only this
RECEIVED: list = []

ERP = """<!doctype html><meta charset=utf-8><title>WA-FAKE ERP · 주문 등록</title>
<h1>WA-FAKE ERP (가짜)</h1>
<label>주문 <input id=order></label> <label>거래처 <input id=customer></label> <label>수량 <input id=qty></label>
<p id=preview></p><button id=submit>등록</button><p id=okbox></p>
<script>
const f=()=>document.getElementById('preview').textContent=['order','customer','qty'].map(i=>document.getElementById(i).value).join(' / ');
document.querySelectorAll('input').forEach(i=>i.addEventListener('input',f));
document.getElementById('submit').onclick=async()=>{const b={order:order.value,customer:customer.value,qty:qty.value};
 await fetch('/erp/submit',{method:'POST',body:JSON.stringify(b)});
 document.getElementById('okbox').innerHTML='<span id=ok>등록완료 '+b.order+'</span>';};
</script>"""

ORDERS = [{"order": "A-1001", "customer": "Demo Customer 1", "days_late": 0},
          {"order": "A-1002", "customer": "Demo Customer 2", "days_late": 4},
          {"order": "A-1003", "customer": "Demo Customer 3", "days_late": 3}]


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authed(self):
        return self.headers.get("Authorization") == "Bearer " + FAKE_TOKEN

    def do_GET(self):
        if self.path == "/erp":
            return self._send(200, ERP, "text/html")
        if self.path == "/api/orders":
            return self._send(200, {"orders": ORDERS}) if self._authed() else self._send(401, {"error": "token"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode() if n else ""
        if self.path in ("/erp/submit", "/api/tickets"):
            RECEIVED.append((self.path, body))
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})


def chrome_path() -> str | None:
    for c in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              shutil.which("google-chrome") or "", shutil.which("chromium") or ""]:
        if c and Path(c).exists():
            return c
    return None


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wa(ws: Path, *args, env_extra=None) -> tuple[int, str]:
    env = dict(os.environ, WA_WORKSPACE=str(ws), WA_APP_TOKEN=FAKE_TOKEN, **(env_extra or {}))
    p = subprocess.run([sys.executable, str(ROOT / "wa.py"), *args], capture_output=True, text=True, env=env, timeout=900)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    for port in (PORT_HTTP, PORT_CDP):
        if not port_free(port):
            print(f"port {port} is busy — stop whatever uses it and retry")
            return 2
    ws = Path(tempfile.mkdtemp(prefix="wa-e2e-"))
    srv = ThreadingHTTPServer(("127.0.0.1", PORT_HTTP), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    chrome = None
    results = []
    try:
        demo = ws / "demo_files"
        demo.mkdir(parents=True)
        (demo / "orders.csv").write_text("order,customer,qty\nA-1001,Demo Customer 1,3\nA-1002,Demo Customer 2,1\n", encoding="utf-8")
        (demo / "inbox.json").write_text(json.dumps([
            {"id": "M1", "text": "주문한 상품이 아직 배송되지 않았어요. 언제 받을 수 있나요? (가짜 문의)"},
            {"id": "M2", "text": "색상이 사진과 달라서 환불하고 싶습니다. (가짜 문의)"},
            {"id": "M3", "text": "이 케이스가 새 모델에도 맞나요? (가짜 문의)"}], ensure_ascii=False), encoding="utf-8")

        cp = chrome_path()
        try:
            import playwright  # noqa: F401
            have_pw = True
        except ImportError:
            have_pw = False
        if cp and have_pw:
            chrome = subprocess.Popen([cp, "--headless=new", f"--remote-debugging-port={PORT_CDP}",
                                       f"--user-data-dir={ws / 'chrome-e2e-profile'}", "--no-first-run",
                                       "--no-default-browser-check", "about:blank"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(50):
                if not port_free(PORT_CDP):
                    break
                time.sleep(0.2)

        plan = [("demo-browser-orders", "browser-cdp", "erp_entered.csv", bool(cp and have_pw)),
                ("demo-api-tickets", "app-api", "late_orders.csv", True),
                ("demo-ai-triage", "ai-step", "reply_drafts.md", True)]
        for auto_id, tool, out_name, possible in plan:
            r = {"automation": auto_id, "template": tool}
            if not possible:
                r.update(result="SKIPPED", why="Chrome or the playwright package is missing")
                results.append(r)
                continue
            rc, out = wa(ws, "new", auto_id, "--tool", tool)
            r["new"] = rc == 0
            src = ROOT / "examples" / "automations" / auto_id
            for f in src.iterdir():
                shutil.copy(f, ws / "automations" / auto_id / f.name)
            (ws / "specs").mkdir(exist_ok=True)
            shutil.copy(ROOT / "examples" / "specs" / f"{auto_id}.md", ws / "specs" / f"{auto_id}.md")
            before = len(RECEIVED)
            rc, out = wa(ws, "test", auto_id)
            r["test"] = rc == 0
            r["dry_wrote_real_file"] = (demo / out_name).exists()
            rc, out_live = wa(ws, "run", auto_id, "--live")
            r["live"] = rc == 0
            r["live_output_exists"] = (demo / out_name).exists()
            r["blocked"] = out_live.count("BLOCKED")
            r["server_received"] = len(RECEIVED) - before
            run_id = next((l.split("wa undo ")[1].strip() for l in out_live.splitlines() if "wa undo " in l), None)
            rc, out_undo = wa(ws, "undo", run_id) if run_id else (1, "no run id")
            r["undo"] = rc == 0 and not (demo / out_name).exists()
            if auto_id == "demo-ai-triage":
                r["ai_used"] = "사용 (" in out_live
                r["ai_failures"] = out_live.count("AI 실패")
            ok = all([r["new"], r["test"], not r["dry_wrote_real_file"], r["live"], r["live_output_exists"],
                      r["blocked"] > 0, r["server_received"] == 0, r["undo"]])
            r["result"] = "PASS" if ok else "FAIL"
            if not ok:
                r["log_tail"] = (out + out_live + out_undo)[-1500:]
            results.append(r)
    finally:
        if chrome:
            chrome.terminate()
            try:
                chrome.wait(10)
            except subprocess.TimeoutExpired:
                chrome.kill()
        srv.shutdown()
        shutil.rmtree(ws, ignore_errors=True)
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    return 0 if all(r["result"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

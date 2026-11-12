"""Template: drive a web system in a real Chrome over the DevTools port (CDP).

One-time setup by the USER (the agent never types passwords):
  macOS:   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
             --remote-debugging-port=9222 --user-data-dir="$HOME/.work-autopilot-chrome"
  Windows: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
             --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\\.work-autopilot-chrome"
  Then log in to the sites yourself in that window. Sessions stay in that separate profile.
  (Recent Chrome versions refuse remote debugging on your default profile — that is why it is separate.)

Needs: pip install playwright   (no browser download needed: we attach to your Chrome)
"""
import json
from pathlib import Path

from autopilot.sdk import Run

with Run() as run:
    from playwright.sync_api import sync_playwright

    m = json.loads(Path("automation.json").read_text(encoding="utf-8"))
    port = m.get("params", {}).get("cdp_port", "9222")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        page = ctx.new_page()                      # our own tab; closed at the end
        try:
            # TODO(build): page.goto(...), read values, fill fields with run.guard_value(v)
            # Reading and filling drafts is fine in dry-run. The final click that submits/sends/pays:
            # run.risky("submit_form", "ERP 주문 등록 버튼", lambda: page.click("text=등록"))
            run.log(f"attached to Chrome on :{port}, tabs={len(ctx.pages)}")
        finally:
            page.close()                           # never close the user's own tabs

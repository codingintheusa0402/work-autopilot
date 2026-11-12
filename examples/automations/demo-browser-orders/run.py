"""DEMO (synthetic): type each order from a CSV into a web ERP form in a real Chrome over CDP.

Fills the form (a draft — nothing is sent), reads the preview back, records what it entered.
The final '등록' click is a risky action (submit_form) that runs only after the user approves it.
"""
import csv
import io
import json
import os
from pathlib import Path

from autopilot.sdk import Run


def p(m, k):
    return m["params"][k].replace("{workspace}", os.environ["WA_WORKSPACE"])


with Run() as run:
    from playwright.sync_api import sync_playwright

    m = json.loads(Path("automation.json").read_text(encoding="utf-8"))
    orders = list(csv.DictReader(open(p(m, "orders_csv"), encoding="utf-8")))
    if not orders:
        run.log("주문 없음 — 할 일 없음")
        raise SystemExit(0)
    entered = []
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{m['params']['cdp_port']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()                                  # our own tab
        try:
            for o in orders:
                page.goto(p(m, "erp_url"))
                page.fill("#order", run.guard_value(o["order"]))
                page.fill("#customer", run.guard_value(o["customer"]))
                page.fill("#qty", run.guard_value(o["qty"]))
                preview = page.inner_text("#preview")
                run.log(f"입력 완료(초안): {preview}")
                done = run.risky("submit_form", f"ERP 등록 {o['order']}",
                                 lambda: (page.click("#submit"), page.wait_for_selector("#ok"), page.inner_text("#ok"))[2])
                entered.append([o["order"], o["customer"], o["qty"], "submitted" if done else "draft-only"])
        finally:
            page.close()                                       # never touch the user's other tabs
    buf = io.StringIO()
    csv.writer(buf).writerows([["order", "customer", "qty", "status"]] + entered)
    run.write_text(p(m, "result_csv"), buf.getvalue())

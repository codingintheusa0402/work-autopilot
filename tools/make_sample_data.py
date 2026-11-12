#!/usr/bin/env python3
"""Generate the bundled SYNTHETIC sample week. 100% fake: invented person, invented company,
example.com domains only. Deterministic (seeded) so the demo report is reproducible.

    python3 tools/make_sample_data.py  →  samples/synthetic_week/events.jsonl.gz
"""
import datetime as dt
import gzip
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "samples" / "synthetic_week" / "events.jsonl.gz"
TZ = dt.timezone(dt.timedelta(hours=9))
DAYS = [dt.date(2030, 3, 4) + dt.timedelta(days=i) for i in range(5)]   # a fake future week, Mon–Fri
rnd = random.Random(42)


CURSOR = [None]


def block(events, start, minutes, app, title, url=None, step=(20, 40)):
    # never overlap the previous block: one person, one focused window at a time
    if CURSOR[0] and start < CURSOR[0]:
        start = CURSOR[0] + dt.timedelta(seconds=30)
    t = start
    end = start + dt.timedelta(minutes=minutes)
    while t < end:
        events.append({"ts": t.isoformat(), "app": app, "title": title, "domain": url, "src": "synthetic"})
        t += dt.timedelta(seconds=rnd.randint(*step))
    CURSOR[0] = t
    return t


def at(day, hh, mm, jitter=6):
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ) + dt.timedelta(minutes=rnd.randint(-jitter, jitter))


def order_flow(ev, t, day, n):
    """Fixed 4-step routine: order mail → Excel → web ERP form → confirmation reply."""
    t = block(ev, t, rnd.randint(3, 5), "Outlook", f"[주문요청] 거래처 {rnd.randint(100,999)} - 받은편지함 - 데모 사용자 - Outlook")
    t = block(ev, t + dt.timedelta(seconds=30), rnd.randint(7, 10), "Excel", f"주문내역_{day:%Y%m%d}.xlsx - Excel")
    t = block(ev, t + dt.timedelta(seconds=40), rnd.randint(9, 13), "Google Chrome", "주문 등록 - Example ERP", "https://erp.example.com/orders/new")
    t = block(ev, t + dt.timedelta(seconds=30), rnd.randint(3, 4), "Outlook", f"RE: [주문요청] 거래처 {rnd.randint(100,999)} - 주문 접수 확인 - Outlook")
    return t


def main():
    ev = []
    for i, day in enumerate(DAYS):
        block(ev, at(day, 9, 0, 3), rnd.randint(20, 30), "Outlook", "받은편지함 - 데모 사용자 - Outlook")
        t = order_flow(ev, at(day, 9, 40), day, 1)
        block(ev, t + dt.timedelta(minutes=2), rnd.randint(10, 15), "Slack", "#sales-support - Example Trading (가상) - Slack")
        order_flow(ev, at(day, 10, 50), day, 2)
        if i % 2 == 0:
            order_flow(ev, at(day, 11, 30), day, 3)
        # private apps the privacy filter must drop
        block(ev, at(day, 12, 10), rnd.randint(3, 6), "KakaoTalk", "가족 단톡방")
        if i == 2:
            block(ev, at(day, 12, 30), 2, "1Password", "Unlock 1Password")
        # after lunch
        t = block(ev, at(day, 13, 20, 3), rnd.randint(4, 6), "Finder", "Downloads")
        t = block(ev, t, rnd.randint(8, 12), "Preview", f"Invoice_{rnd.randint(1000,9999)}.pdf")
        block(ev, t, rnd.randint(3, 5), "Finder", "거래명세서 > 2030 > 03월")
        if day.weekday() in (0, 2, 4):
            block(ev, at(day, 14, 0, 2), rnd.choice([30, 45, 60]), "zoom.us", "Zoom Meeting", step=(30, 60))
        if day.weekday() in (1, 3):
            block(ev, at(day, 14, 30), rnd.randint(18, 25), "Google Chrome", "경비 정산 - Example Expense", "https://expense.example.com/claims")
        block(ev, at(day, 15, 30), rnd.randint(15, 25), "Slack", "#sales-support - Example Trading (가상) - Slack")
        block(ev, at(day, 16, 10), rnd.randint(18, 25), "Excel", "일일매출_집계.xlsx - Excel")
        if day.weekday() == 4:
            t = block(ev, at(day, 16, 40), 30, "Excel", "일일매출_집계.xlsx - Excel")
            block(ev, t, rnd.randint(60, 80), "PowerPoint", "주간보고_영업지원.pptx - PowerPoint")
        else:
            block(ev, at(day, 16, 45), rnd.randint(10, 20), "Google Chrome", "거래처 검색 - Google 검색", "https://www.google.com/search")
        block(ev, at(day, 17, 30), rnd.randint(10, 15), "Outlook", "받은편지함 - 데모 사용자 - Outlook")
    ev.sort(key=lambda e: e["ts"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(OUT, "wb", mtime=0) as raw:
        for e in ev:
            raw.write((json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"{len(ev)} synthetic events → {OUT}")


if __name__ == "__main__":
    main()

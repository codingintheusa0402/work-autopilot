"""DEMO automation (synthetic data only).

Moves 'Invoice_<number>_<vendor>.pdf' files from the inbox folder into
archive/<vendor>/<YYYY-MM>/, writes a summary CSV, and (only if the user approved
it) posts a one-line summary. In this demo the "post" just prints — no network.
"""
import datetime as dt
import json
import os
import re
from pathlib import Path

from autopilot.sdk import Run

PATTERN = re.compile(r"^Invoice_(\d+)_([A-Za-z0-9-]+)\.pdf$")


def param(m, key):
    return Path(m["params"][key].replace("{workspace}", os.environ["WA_WORKSPACE"]))


with Run() as run:
    m = json.loads(Path("automation.json").read_text(encoding="utf-8"))
    inbox, archive = param(m, "inbox"), param(m, "archive")
    if not inbox.exists():
        run.log(f"inbox 없음: {inbox} — 할 일 없음")
        raise SystemExit(0)
    month = dt.date.today().strftime("%Y-%m")
    done, skipped = [], []
    for f in sorted(inbox.iterdir()):
        hit = PATTERN.match(f.name)
        if not hit:
            skipped.append(f.name)          # edge case from the spec: unknown names stay put
            continue
        number, vendor = hit.groups()
        dst = archive / vendor / month / f.name
        if dst.exists():
            run.log(f"이미 정리됨, 건너뜀: {f.name}")   # edge case: duplicates are never overwritten
            continue
        run.move(f, dst)
        done.append((number, vendor, f.name))
    lines = ["invoice,vendor,file"] + [",".join(x) for x in done]
    run.write_text(archive / f"summary-{month}.csv", "\n".join(lines) + "\n")
    run.log(f"정리 {len(done)}건, 이름 규칙 밖이라 둔 파일 {len(skipped)}건: {', '.join(skipped) or '-'}")
    text = f"[데모] 거래명세서 {len(done)}건 정리 완료 ({month})"
    run.risky("send_message", "팀 채널에 처리 요약 1줄", lambda: print("   (demo) would post:", text))

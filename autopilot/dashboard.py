"""One local page: what is automated, how it is running, how much time it saved."""
from __future__ import annotations

import collections
import html
import json
from pathlib import Path

from . import config as C
from .report import CSS
from .runner import all_automations, recent_runs

STATUS = {"draft": "초안", "tested": "테스트 통과", "scheduled": "예약 실행 중"}


def build() -> str:
    autos = all_automations()
    runs = recent_runs(5000)
    by = collections.defaultdict(list)
    for r in runs:
        by[r["automation"]].append(r)
    analysis = {}
    try:
        analysis = json.loads((C.REPORT_DIR / "analysis.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    task_week = {t["id"]: t["minutes_per_week"] for t in analysis.get("tasks", [])}
    total_week = sum(task_week.values()) or 0

    rows, saved_total, covered = [], 0.0, set()
    for a in autos:
        rs = by.get(a["id"], [])
        live = [r for r in rs if r["mode"] == "live"]
        ok_live = [r for r in live if r["ok"]]
        saved = sum(r["minutes_saved"] for r in ok_live)
        saved_total += saved
        covered |= set(a.get("task_ids", []))
        last = rs[-1] if rs else None
        rate = f"{100*len(ok_live)/len(live):.0f}%" if live else "–"
        per_week = a.get("minutes_saved_per_run", 0) * len((a.get("schedule") or {}).get("weekdays", []))
        last_txt = "–"
        if last:
            last_txt = f"{html.escape(last['start'][:16].replace('T', ' '))} · {last['mode']} · {'OK' if last['ok'] else 'FAIL'}"
            if last.get("undone"):
                last_txt += " · 되돌림"
            if last.get("blocked"):
                last_txt += f" · 승인대기 {len(last['blocked'])}"
        cls = {"scheduled": "auto", "tested": "ai"}.get(a.get("status"), "human")
        rows.append(f"""<tr><td><b>{html.escape(a.get('title', a['id']))}</b><div class=why>{html.escape(a['id'])} · {html.escape(a.get('tool',''))} · 작업 {html.escape(', '.join(a.get('task_ids', [])))}</div></td>
<td><span class="pill p-{cls}">{STATUS.get(a.get('status','draft'), a.get('status'))}</span></td>
<td>{html.escape(_sched(a))}</td><td class=num>{len(live)} / {len(rs)}</td><td class=num>{rate}</td>
<td class=why>{last_txt}</td><td class=num>{saved/60:.1f}h</td><td class=num>{per_week/60:.1f}h</td></tr>""")
    cov_min = sum(task_week.get(t, 0) for t in covered)
    cov = f"{100*cov_min/total_week:.0f}%" if total_week else "–"
    fails = [r for r in runs if not r["ok"]][-5:]
    fail_html = "".join(f"<li>{html.escape(r['start'][:16])} · {html.escape(r['automation'])} · exit {r['exit']} · <code>{html.escape(Path(r['log']).name)}</code></li>" for r in fails) or "<li>없음</li>"
    banner = ("<div class=banner>합성(가짜) 데모 데이터 기반 — SYNTHETIC DEMO DATA</div>" if analysis.get("synthetic") else "")
    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>자동화 대시보드</title><style>{CSS}</style></head><body><main>{banner}
<h1>자동화 대시보드</h1><p class=sub>무엇이 자동화됐고, 잘 돌고 있고, 시간을 얼마나 아꼈는지</p>
<div class=kpis>
<div class=kpi><b>{len(autos)}개</b><span>자동화 (예약 {sum(1 for a in autos if a.get('status')=='scheduled')} · 테스트 통과 {sum(1 for a in autos if a.get('status')=='tested')})</span></div>
<div class=kpi><b>{saved_total/60:.1f}h</b><span>지금까지 아낀 시간 (성공한 실제 실행 기준)</span></div>
<div class=kpi><b>{cov}</b><span>관찰된 업무 시간 중 자동화가 맡은 비율</span></div>
<div class=kpi><b>{len(runs)}회</b><span>전체 실행 (dry-run 포함)</span></div>
</div>
<h2>자동화 목록</h2><div class=card><table><thead><tr><th>자동화</th><th>상태</th><th>예약</th><th class=num>실제/전체 실행</th><th class=num>성공률</th><th>마지막 실행</th><th class=num>아낀 시간</th><th class=num>주당 예상</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan=8>아직 자동화가 없습니다.</td></tr>'}</tbody></table></div>
<h2>최근 실패</h2><div class=next><ul>{fail_html}</ul></div>
<footer>로컬 파일입니다. 실행 기록: workspace/logs/runs.jsonl · 되돌리기: wa undo &lt;run_id&gt;</footer>
</main></body></html>"""


def _sched(a: dict) -> str:
    s = a.get("schedule")
    if not s:
        return "수동"
    names = "월화수목금토일"
    days = "".join(names[d - 1] for d in s.get("weekdays", []))
    return f"{days} {s.get('time', '')}"


def write() -> str:
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    p = C.REPORT_DIR / "dashboard.html"
    p.write_text(build(), encoding="utf-8")
    return str(p)

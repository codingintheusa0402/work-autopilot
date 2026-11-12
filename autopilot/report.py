"""Render analysis.json as a self-contained HTML page and a Markdown file (both local only)."""
from __future__ import annotations

import html
from pathlib import Path

from . import config as C

VERDICT = {
    "automatable": ("자동화", "auto"),
    "ai_assistable": ("AI 보조", "ai"),
    "keep_human": ("사람 유지", "human"),
}

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--muted:#6e6e73;--line:#e5e5ea;
--auto:#1f8a5b;--ai:#3a6fd8;--human:#a3a3a8;--warn-bg:#fff4d6;--warn-ink:#7a5600}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111214;--card:#1b1c1f;--ink:#f2f2f4;
--muted:#a0a0a8;--line:#2c2d31;--auto:#3fbf86;--ai:#6d9bff;--human:#6b6b72;--warn-bg:#3a3010;--warn-ink:#ffd76a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic","Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;margin:0 0 4px;letter-spacing:-.02em}h2{font-size:18px;margin:36px 0 12px}
.sub{color:var(--muted);margin:0 0 20px}
.banner{background:var(--warn-bg);color:var(--warn-ink);border-radius:10px;padding:10px 14px;margin:0 0 20px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.kpi b{display:block;font-size:26px;letter-spacing:-.02em}.kpi span{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:4px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:760px}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em}
tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tid{color:var(--muted);font-variant-numeric:tabular-nums}.why{color:var(--muted);font-size:13px}
.bar{display:flex;height:8px;border-radius:4px;overflow:hidden;width:150px;background:var(--line)}
.bar i{display:block}.b-auto{background:var(--auto)}.b-ai{background:var(--ai)}.b-human{background:var(--human)}
.sc{font-size:12px;color:var(--muted);margin-top:4px;white-space:nowrap}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;color:#fff;white-space:nowrap}
.p-auto{background:var(--auto)}.p-ai{background:var(--ai)}.p-human{background:var(--human)}
.time{display:flex;align-items:center;gap:8px}.time .t{height:10px;border-radius:5px;background:var(--ink);opacity:.75}
.flow{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:10px}
.flow ol{margin:6px 0 0;padding-left:20px}.flow small{color:var(--muted)}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:13px;margin:8px 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.next{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px 20px}
footer{color:var(--muted);font-size:12px;margin-top:40px}
"""


def _e(x) -> str:
    return html.escape(str(x))


def render_html(r: dict) -> str:
    tasks = r["tasks"]
    max_w = max((t["minutes_per_week"] for t in tasks), default=1) or 1
    rows = []
    for t in tasks:
        s = t["scores"]
        tot = sum(s.values()) or 1
        lab, cls = VERDICT[t["verdict"]]
        rows.append(f"""<tr>
<td class=tid>{_e(t['id'])}</td>
<td><b>{_e(t['name'])}</b><div class=why>{_e(' · '.join(t['why']))}</div></td>
<td><div class=time><div class=t style="width:{90 * t['minutes_per_week'] / max_w:.0f}px"></div><span class=num>{t['minutes_per_week']/60:.1f}h</span></div></td>
<td class=num>{t['sessions_per_day']}</td>
<td class=num>{_e(t['typical_start'])}</td>
<td><div class=bar><i class=b-auto style="width:{100*s['automatable']/tot:.0f}%"></i><i class=b-ai style="width:{100*s['ai_assistable']/tot:.0f}%"></i><i class=b-human style="width:{100*s['keep_human']/tot:.0f}%"></i></div>
<div class=sc>{s['automatable']} / {s['ai_assistable']} / {s['keep_human']}</div></td>
<td><span class="pill p-{cls}">{lab}</span></td>
<td class=num>{t['est_minutes_saved_per_week']/60:.1f}h</td></tr>""")

    flows = []
    for w in r["workflows"]:
        items = "".join(f"<li><span class=tid>{_e(i)}</span> {_e(n)}</li>" for i, n in zip(w["steps"], w["names"]))
        flows.append(f"<div class=flow><b>{len(w['steps'])}단계 반복 루틴</b> <small>· {w['days_seen']}일 동안 관찰, 최소 {w['times_seen']}회</small><ol>{items}</ol></div>")
    flows_html = "".join(flows) or "<p class=sub>여러 날 반복된 앱 전환 순서가 아직 없습니다.</p>"

    banner = ("<div class=banner>합성(가짜) 데모 데이터입니다 — 실제 사람의 화면이 아닙니다. "
              "SYNTHETIC DEMO DATA, not a real person's screen.</div>") if r.get("synthetic") else ""
    by = {"automatable": 0, "ai_assistable": 0, "keep_human": 0}
    for t in tasks:
        by[t["verdict"]] += 1
    rank = {"automatable": 0, "ai_assistable": 1}
    top = sorted((t for t in tasks if t["verdict"] in rank),
                 key=lambda t: (rank[t["verdict"]], -t["est_minutes_saved_per_week"]))[:3]
    nexts = "".join(f"<li><b>{_e(t['id'])}</b> {_e(t['name'])} — 주 {t['minutes_per_week']/60:.1f}시간</li>" for t in top)

    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>업무 분석 리포트</title><style>{CSS}</style></head>
<body><main>
{banner}
<h1>업무 분석 리포트</h1>
<p class=sub>{_e(r['first_day'])} ~ {_e(r['last_day'])} · {r['days_observed']}일 관찰 · 이벤트 {r['events']:,}개 · 생성 {_e(r['generated'])}</p>
<div class=kpis>
<div class=kpi><b>{r['active_hours_per_day']}h</b><span>하루 평균 활동 시간</span></div>
<div class=kpi><b>{len(tasks)}개</b><span>찾은 작업 (자동화 {by['automatable']} · AI 보조 {by['ai_assistable']} · 사람 {by['keep_human']})</span></div>
<div class=kpi><b>{len(r['workflows'])}개</b><span>반복되는 여러 단계 루틴</span></div>
<div class=kpi><b>~{r['est_hours_saved_per_week']}h</b><span>주당 절약 가능 시간 (추정)</span></div>
</div>
<h2>작업 목록</h2>
<div class=legend><span><i class=b-auto></i>자동화 가능</span><span><i class=b-ai></i>AI 보조</span><span><i class=b-human></i>사람이 계속</span><span>점수 = 자동화 / AI 보조 / 사람 (0–100)</span></div>
<div class=card><table><thead><tr><th>ID</th><th>작업</th><th>주당 시간</th><th class=num>하루 횟수</th><th class=num>주로 하는 시간</th><th>점수</th><th>판정</th><th class=num>절약 추정</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<h2>반복 루틴 (여러 앱을 정해진 순서로 오가는 일)</h2>
{flows_html}
<h2>다음 단계: 인터뷰</h2>
<div class=next><p>에이전트가 아래 작업부터 하나씩 질문합니다. 각 단계의 의미, '끝'의 기준, 예외 상황, 승인이 필요한 동작이 모두 분명해질 때까지 묻고 나서 만듭니다.</p><ol>{nexts}</ol></div>
<footer>{' '.join(_e(n) for n in r['notes'])}<br>이 파일은 이 컴퓨터에만 저장됩니다. 원본 화면 기록은 분석 후 삭제됩니다.</footer>
</main></body></html>"""


def render_md(r: dict) -> str:
    out = []
    if r.get("synthetic"):
        out.append("> **합성(가짜) 데모 데이터 — SYNTHETIC DEMO DATA, not a real person's screen.**\n")
    out.append("# 업무 분석 리포트\n")
    out.append(f"{r['first_day']} ~ {r['last_day']} · {r['days_observed']}일 관찰 · 하루 평균 {r['active_hours_per_day']}시간 · "
               f"주당 절약 가능 ~{r['est_hours_saved_per_week']}시간 (추정)\n")
    out.append("| ID | 작업 | 주당 시간 | 하루 횟수 | 주로 하는 시간 | 자동화/AI/사람 | 판정 | 절약 추정 |")
    out.append("|---|---|---:|---:|---|---|---|---:|")
    for t in r["tasks"]:
        s = t["scores"]
        out.append(f"| {t['id']} | {t['name']} | {t['minutes_per_week']/60:.1f}h | {t['sessions_per_day']} | {t['typical_start']} | "
                   f"{s['automatable']}/{s['ai_assistable']}/{s['keep_human']} | {VERDICT[t['verdict']][0]} | {t['est_minutes_saved_per_week']/60:.1f}h |")
    out.append("\n## 반복 루틴\n")
    for w in r["workflows"]:
        out.append(f"- {' → '.join(w['steps'])} ({w['days_seen']}일, 최소 {w['times_seen']}회)")
    out.append("\n" + "\n".join(f"_{n}_" for n in r["notes"]))
    return "\n".join(out) + "\n"


def write(r: dict) -> tuple[Path, Path]:
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    h = C.REPORT_DIR / "report.html"
    m = C.REPORT_DIR / "report.md"
    h.write_text(render_html(r), encoding="utf-8")
    m.write_text(render_md(r), encoding="utf-8")
    return h, m

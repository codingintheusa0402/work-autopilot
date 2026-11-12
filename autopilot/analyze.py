"""Step 2 — Find. Turn metadata events into a task list with time, frequency and an automation score.

Heuristics only (no AI, no network). The agent reads analysis.json afterwards and refines the
names and verdicts with the user during the interview — the numbers here are a starting point.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import re
import statistics
from pathlib import Path

from . import config as C
from .redact import normalize_title

IDLE_CAP_S = 90          # one sample never counts for more than this
SESSION_GAP_S = 300      # same task again within 5 min = same session
CHAIN_GAP_S = 180        # different tasks within 3 min = same workflow chain
MIN_TASK_MIN = 10        # tasks smaller than this over the whole period fold into "기타"

_TOKEN = re.compile(r"[^\s\-–—|·:]+")


def _parse(ts: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _word_in(word: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?![a-z0-9])", text) is not None


def categorize(hints: list[dict], app: str, title: str, domain: str | None) -> dict:
    a, t, d = app.lower(), title.lower(), (domain or "").lower()
    for h in hints:
        if any(_word_in(x, a) for x in h.get("apps", [])) or (d and any(x in d for x in h.get("domains", []))):
            return h
    for h in hints:
        if any(x.lower() in t for x in h.get("title", [])):
            return h
    return hints[-1] if hints else {"id": "other", "label": "기타", "nature": "mixed"}


def _templates(events: list[dict]) -> list[str]:
    """Per app, keep only title tokens that recur (≥15% of that app's samples)."""
    by_app: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    norm = [normalize_title(e.get("title", "")) for e in events]
    for e, n in zip(events, norm):
        by_app[e["app"]].update(set(_TOKEN.findall(n)))
    totals = collections.Counter(e["app"] for e in events)
    out = []
    for e, n in zip(events, norm):
        c, tot = by_app[e["app"]], totals[e["app"]]
        keep = [tok for tok in _TOKEN.findall(n) if c[tok] >= max(3, 0.15 * tot)]
        out.append(" ".join(keep)[:60] or "(no title)")
    return out


def _regularity(ss: list[dict], active_days: int) -> tuple[float, str]:
    """Share of sessions that start in an hour slot used on most active days (±1h)."""
    slot_days: dict[int, set] = collections.defaultdict(set)
    for s in ss:
        slot_days[s["start"].hour].add(s["start"].date())
    need = max(2, 0.6 * active_days)
    slots = sorted(h for h, d in slot_days.items() if len(d) >= need)
    if active_days < 2 or not slots:
        hrs = sorted(s["start"].hour for s in ss)
        return 0.0, f"{statistics.median_low(hrs):02d}시경"
    hits = sum(1 for s in ss if any(abs(s["start"].hour - h) <= 1 for h in slots))
    merged = []
    for h in slots:
        if not merged or h - merged[-1] > 1:
            merged.append(h)
    return hits / len(ss), ", ".join(f"{h:02d}시" for h in merged)


def _clamp(x: float) -> int:
    return int(max(0, min(100, round(x))))


BASE = {
    "auto":  {"structured": 45, "text": 15, "mixed": 20, "human": 0},
    "ai":    {"structured": 20, "text": 55, "mixed": 35, "human": 15},
    "human": {"structured": 10, "text": 20, "mixed": 30, "human": 70},
}
SAVE_SHARE = {"automatable": 0.7, "ai_assistable": 0.3, "keep_human": 0.0}


def score(nature: str, per_day: float, regularity: float, day_ratio: float, avg_min: float, in_workflow: bool):
    f = min(per_day / 3, 1.0)
    auto = BASE["auto"][nature] + 20 * f + 15 * regularity + 10 * day_ratio + (10 if in_workflow else 0) \
        - (10 if avg_min > 45 else 0)
    ai = BASE["ai"][nature] + 15 * f + 10 * day_ratio + (10 if 3 <= avg_min <= 30 else 0)
    hum = BASE["human"][nature] + 20 * (1 - day_ratio) + 10 * (1 - regularity) + (10 if avg_min > 45 else 0)
    s = {"automatable": _clamp(auto), "ai_assistable": _clamp(ai), "keep_human": _clamp(hum)}
    verdict = max(s, key=s.get)
    why = []
    if nature == "structured":
        why.append("정형 입력/파일 작업")
    if nature == "text":
        why.append("글쓰기·읽기 비중이 큼")
    if nature == "human":
        why.append("사람 간 대화/판단")
    if per_day >= 2:
        why.append(f"하루 {per_day:.1f}회 반복")
    if regularity >= 0.6:
        why.append("매일 비슷한 시간에 함")
    if in_workflow:
        why.append("여러 앱을 오가는 고정 순서가 있음")
    if avg_min > 45:
        why.append("한 번에 오래 집중하는 일")
    if day_ratio < 0.4:
        why.append("가끔만 함")
    return s, verdict, why


def analyze(events: list[dict], workdays_per_week: int = 5) -> dict:
    hints = C.load_hints()
    events = sorted((e for e in events if e.get("ts")), key=lambda e: e["ts"])
    if not events:
        raise SystemExit("이벤트가 없습니다. observe export 또는 샘플 데이터를 확인하세요.")
    times = [_parse(e["ts"]) for e in events]
    tmpl = _templates(events)

    # 1) per-sample duration + task key
    keyed = []
    for i, e in enumerate(events):
        gap = (times[i + 1] - times[i]).total_seconds() if i + 1 < len(events) else 30
        dur = max(0.0, min(gap, IDLE_CAP_S))
        cat = categorize(hints, e["app"], e.get("title", ""), e.get("domain"))
        key = (cat["id"], e["app"], e.get("domain") or "", tmpl[i])
        keyed.append((times[i], dur, key, cat))

    days = sorted({t.date() for t, *_ in keyed})
    n_days = max(1, len(days))

    # 2) sessions
    sessions = []  # (key, start, end, seconds)
    cur = None
    for t, dur, key, cat in keyed:
        if cur and cur["key"] == key and (t - cur["end"]).total_seconds() <= SESSION_GAP_S:
            cur["end"] = t + dt.timedelta(seconds=dur)
            cur["sec"] += dur
        else:
            if cur:
                sessions.append(cur)
            cur = {"key": key, "cat": cat, "start": t, "end": t + dt.timedelta(seconds=dur), "sec": dur}
    if cur:
        sessions.append(cur)

    # 3) fold tiny tasks
    total_by_key = collections.Counter()
    for s in sessions:
        total_by_key[s["key"]] += s["sec"]
    # short observations (e.g. a 15-minute test) scale the cut-off down so real tasks still show up
    min_task_s = min(MIN_TASK_MIN * 60, 0.03 * sum(total_by_key.values()))
    for s in sessions:
        if total_by_key[s["key"]] < min_task_s:
            s["key"] = ("other", "(여러 앱)", "", "짧은 작업 모음")
            s["cat"] = {"id": "other", "label": "기타 (짧은 작업 모음)", "nature": "mixed"}

    # 4) workflows: chains of different tasks back-to-back, counted per distinct day
    chains, chain = [], []
    for s in sessions:
        if chain and (s["start"] - chain[-1]["end"]).total_seconds() > CHAIN_GAP_S:
            chains.append(chain)
            chain = []
        if not chain or chain[-1]["key"] != s["key"]:
            chain.append(s)
        else:
            chain[-1] = {**chain[-1], "end": s["end"]}
    if chain:
        chains.append(chain)
    tri_days: dict[tuple, set] = collections.defaultdict(set)
    tri_count = collections.Counter()
    for ch in chains:
        ks = [c["key"] for c in ch]
        for i in range(len(ks) - 2):
            tri = tuple(ks[i:i + 3])
            if len(set(tri)) == 3 and not any(k[0] in ("other", "meeting") for k in tri):
                tri_days[tri].add(ch[i]["start"].date())
                tri_count[tri] += 1

    # 5) aggregate tasks
    by_key: dict[tuple, list] = collections.defaultdict(list)
    for s in sessions:
        by_key[s["key"]].append(s)
    keys_sorted = sorted(by_key, key=lambda k: -sum(s["sec"] for s in by_key[k]))
    ids = {k: f"T{i+1:02d}" for i, k in enumerate(keys_sorted)}

    good_tris = [(tri, len(d), tri_count[tri]) for tri, d in tri_days.items() if len(d) >= 2]
    good_tris.sort(key=lambda x: (-x[1], -x[2]))
    good_tris = good_tris[:8]
    in_wf = {k for tri, *_ in good_tris for k in tri}

    tasks = []
    for k in keys_sorted:
        ss = by_key[k]
        cat = ss[0]["cat"]
        total_min = sum(s["sec"] for s in ss) / 60
        n_sess = len(ss)
        active_days = len({s["start"].date() for s in ss})
        per_day = n_sess / n_days
        regular, typical = _regularity(ss, active_days)
        avg_min = total_min / n_sess
        nature = cat.get("nature", "mixed")
        sc, verdict, why = score(nature, per_day, regular, active_days / n_days, avg_min, k in in_wf)
        weekly = total_min / n_days * workdays_per_week
        tasks.append({
            "id": ids[k],
            "name": _task_name(cat, k),
            "category": cat["id"], "category_label": cat.get("label", cat["id"]),
            "app": k[1], "domain": k[2] or None, "title_pattern": k[3],
            "minutes_total": round(total_min, 1),
            "minutes_per_week": round(weekly, 1),
            "sessions": n_sess, "sessions_per_day": round(per_day, 2),
            "active_days": active_days, "avg_session_min": round(avg_min, 1),
            "typical_start": typical,
            "regularity": round(regular, 2),
            "scores": sc, "verdict": verdict, "why": why,
            "est_minutes_saved_per_week": round(weekly * SAVE_SHARE[verdict], 1),
        })

    # merge overlapping 3-step chains (A,B,C)+(B,C,D) → A,B,C,D
    merged: list[list] = []
    for tri, nd, cnt in good_tris:
        steps = [ids[k] for k in tri]
        for m in merged:
            if m[0][-2:] == steps[:2] and steps[2] not in m[0]:
                m[0].append(steps[2])
                m[2] = min(m[2], cnt)
                break
        else:
            merged.append([steps, nd, cnt])
    name_of = {t["id"]: t["name"] for t in tasks}
    workflows = [{"steps": st, "names": [name_of[i] for i in st], "days_seen": nd, "times_seen": cnt}
                 for st, nd, cnt in merged]

    active_min = sum(t["minutes_total"] for t in tasks)
    srcs = sorted({e.get("src", "?") for e in events})
    return {
        "generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": srcs,
        "synthetic": "synthetic" in srcs,
        "days_observed": n_days,
        "first_day": str(days[0]), "last_day": str(days[-1]),
        "events": len(events),
        "active_hours_total": round(active_min / 60, 1),
        "active_hours_per_day": round(active_min / 60 / n_days, 1),
        "est_hours_saved_per_week": round(sum(t["est_minutes_saved_per_week"] for t in tasks) / 60, 1),
        "tasks": tasks,
        "workflows": workflows,
        "notes": [
            "점수는 관찰된 패턴으로 만든 추정치입니다. 인터뷰 단계에서 사용자와 함께 확정합니다.",
            "절약 시간 = 주당 소요 시간 × (자동화 70% / AI 보조 30% / 사람 유지 0%) 의 대략치입니다.",
        ],
    }


def _task_name(cat: dict, k: tuple) -> str:
    _, app, domain, pattern = k
    where = domain or app
    pat = pattern if pattern and pattern != "(no title)" else ""
    pat = " ".join(w for w in pat.split() if w.lower() not in app.lower().split())
    label = cat.get("label", cat["id"])
    return f"{label} · {where}" + (f" · {pat}" if pat and pat not in where.lower() else "")


def save(result: dict) -> Path:
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    p = C.REPORT_DIR / "analysis.json"
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

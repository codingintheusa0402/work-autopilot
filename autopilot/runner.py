"""Steps 4–5 — Build/Test. Find automations, lint, dry-run, run live, keep a run log."""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from . import config as C
from .redact import redact
from .safety import code_hash, lint

RUNS_LOG = C.LOG_DIR / "runs.jsonl"


def find(auto_id: str) -> Path:
    d = C.AUTO_DIR / auto_id
    if not (d / "automation.json").exists():
        raise SystemExit(f"자동화를 찾을 수 없습니다: {d}")
    return d


def all_automations() -> list[dict]:
    out = []
    for m in sorted(C.AUTO_DIR.glob("*/automation.json")):
        data = json.loads(m.read_text(encoding="utf-8"))
        data["_dir"] = str(m.parent)
        out.append(data)
    return out


def manifest(d: Path) -> dict:
    return json.loads((d / "automation.json").read_text(encoding="utf-8"))


def save_manifest(d: Path, m: dict) -> None:
    (d / "automation.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _spec_open_questions(m: dict) -> int:
    spec = C.SPEC_DIR / f"{m['id']}.md"
    if not spec.exists():
        return -1
    return spec.read_text(encoding="utf-8").count("TODO(ask)")


def run(auto_id: str, live: bool = False, scheduled: bool = False, quiet: bool = False) -> int:
    d = find(auto_id)
    m = manifest(d)
    h = code_hash(d)
    if live:
        if m.get("status") not in ("tested", "scheduled") or m.get("tested_hash") != h:
            print("실제 실행(--live)은 `wa test` 를 통과한 같은 코드만 가능합니다. 코드가 바뀌었다면 다시 test 하세요.")
            return 2
    run_id = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}-{auto_id}"   # unique even within a second
    env = dict(os.environ, WA_MODE="live" if live else "dry", WA_RUN_ID=run_id,
               WA_AUTOMATION_DIR=str(d), WA_WORKSPACE=str(C.WORKSPACE),
               PYTHONPATH=str(C.ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    entry = [sys.executable if x in ("python", "python3") else x for x in m.get("entry", ["python3", "run.py"])]
    log_dir = C.LOG_DIR / auto_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_id}.log"
    start = dt.datetime.now().astimezone()
    try:
        p = subprocess.run(entry, cwd=d, env=env, capture_output=True, text=True,
                           timeout=m.get("timeout_s", 600))
        code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        code, out = 124, f"TIMEOUT after {e.timeout}s\n" + str(e.stdout or "")
    out = redact(out, numbers=False)
    log_path.write_text(out, encoding="utf-8")
    ops = _ops_summary(run_id, live)
    ok = code == 0
    rec = {
        "run_id": run_id, "automation": auto_id, "mode": "live" if live else "dry", "scheduled": scheduled,
        "start": start.isoformat(timespec="seconds"),
        "seconds": round((dt.datetime.now().astimezone() - start).total_seconds(), 1),
        "ok": ok, "exit": code, "ops": ops["ops"], "blocked": ops["blocked"],
        "minutes_saved": m.get("minutes_saved_per_run", 0) if (live and ok) else 0,
        "log": str(log_path),
    }
    C.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if not quiet:
        print(out.rstrip())
        print(f"\n→ {'LIVE' if live else 'DRY-RUN'} {'OK' if ok else 'FAILED'} · run {run_id} · ops {ops['ops']} · blocked {len(ops['blocked'])}")
        if not ok:
            print(f"   로그: {log_path}\n   실패는 runs.jsonl 에 남았습니다. 고친 뒤 `wa test {auto_id}` 를 다시 하세요.")
        if live and ok:
            print(f"   되돌리기: wa undo {run_id}")
    return 0 if ok else 1


def _ops_summary(run_id: str, live: bool) -> dict:
    base = (C.BACKUP_DIR if live else C.DRYRUN_DIR) / run_id / "ops.json"
    try:
        data = json.loads(base.read_text(encoding="utf-8"))
        return {"ops": len(data.get("ops", [])), "blocked": data.get("blocked", [])}
    except FileNotFoundError:
        return {"ops": 0, "blocked": []}


def test(auto_id: str, require_spec: bool = True) -> int:
    """Lint + dry-run. Marks the exact code version as tested when it passes."""
    d = find(auto_id)
    m = manifest(d)
    open_q = _spec_open_questions(m)
    if require_spec and open_q != 0:
        print("인터뷰가 끝나지 않았습니다: " + ("spec 파일이 없습니다" if open_q < 0 else f"spec 에 TODO(ask) {open_q}개 남음")
              + f" → {C.SPEC_DIR / (m['id'] + '.md')}")
        return 2
    errors, warns = lint(d)
    for w in warns:
        print("  warn:", w)
    if errors:
        for e in errors:
            print("  ERROR:", e)
        print("lint 실패. 고친 뒤 다시 test 하세요.")
        return 1
    print(f"lint OK ({len(warns)} warnings). dry-run 실행…\n")
    rc = run(auto_id, live=False)
    if rc == 0:
        m["status"] = "tested" if m.get("status") != "scheduled" else "scheduled"
        m["tested_hash"] = code_hash(d)
        m["tested_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        save_manifest(d, m)
        print(f"\n✓ test 통과 — 이 버전은 `wa run {auto_id} --live` 가 가능합니다.")
    return rc


def recent_runs(limit: int = 200) -> list[dict]:
    """Run records, newest last. Live runs that were undone get undone=True and save no time."""
    if not RUNS_LOG.exists():
        return []
    lines = RUNS_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for x in lines:
        if not x.strip():
            continue
        r = json.loads(x)
        if r.get("mode") == "live":
            try:
                ops = json.loads((C.BACKUP_DIR / r["run_id"] / "ops.json").read_text(encoding="utf-8"))
                if ops.get("undone_at"):
                    r["undone"] = True
                    r["minutes_saved"] = 0
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        out.append(r)
    return out

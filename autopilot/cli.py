"""wa — work-autopilot command line. Run `wa help` for the flow."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import analyze as A
from . import config as C
from . import dashboard, observe, report, runner, safety, scheduler, sdk, spec

FLOW = """work-autopilot — 관찰 → 찾기 → 인터뷰 → 만들기 → 테스트 → 실행

  wa doctor                         환경 점검
  wa demo                           합성 데이터로 전체 흐름 체험 (화면 기록 없음)

1 관찰   wa observe start --days 5   3~7일 기록 (로컬 전용, 개인정보 필터 기본 ON)
         [--recorder screenpipe|builtin]  builtin = 라이선스 걱정 없는 내장 기록기 (앱/창 제목/시간)
         wa observe status | stop    stop = 메타데이터만 export 후 기록 중지
2 찾기   wa analyze                  작업 목록·시간·빈도·점수 → workspace/reports/report.html
                                     (분석이 끝나면 원본 화면 기록은 자동 삭제)
3 인터뷰 wa interview <id> T03 T05   질문지 생성 → 에이전트가 TODO(ask) 를 모두 물어봄
         wa spec check <id>
4 만들기 wa new <id> --tool script|browser-cdp|app-api|ai-step
5 테스트 wa test <id>                lint + dry-run (기본). 통과한 코드만 live 가능
         wa run <id> [--live]        wa undo <run_id> 로 되돌리기
         wa approve <id> <action>    보내기/결제/구매/삭제/제출/업로드는 사용자 본인이 직접 승인
6 실행   wa schedule <id> --live --apply     launchd / cron / 작업 스케줄러
         wa dashboard                무엇이 자동화됐고 시간을 얼마나 아꼈는지
"""


def _open_hint(path: str) -> None:
    print(f"  열기: {path}")


def cmd_doctor(_a) -> int:
    C.ensure_workspace()
    ok = True

    def line(name, good, note=""):
        nonlocal ok
        ok &= bool(good) or name.startswith("(opt)")
        print(f"  {'OK ' if good else '-- '} {name}{(' — ' + note) if note else ''}")

    print(f"work-autopilot doctor · {platform.system()} {platform.release()} · Python {platform.python_version()}")
    line("Python ≥ 3.9", sys.version_info >= (3, 9))
    line("workspace 쓰기 가능", (C.WORKSPACE / ".probe").write_text("x") or True, str(C.WORKSPACE))
    (C.WORKSPACE / ".probe").unlink(missing_ok=True)
    gi = (C.ROOT / ".gitignore").read_text() if (C.ROOT / ".gitignore").exists() else ""
    line("workspace/ 가 .gitignore 에 있음", "workspace/" in gi)
    line("(opt) Node.js / npx (screenpipe 관찰용)", shutil.which("npx"), "없으면 https://nodejs.org")
    line("(opt) Claude Code 또는 Codex CLI", shutil.which("claude") or shutil.which("codex"))
    line("(opt) Chrome (브라우저 자동화용)", _chrome())
    free = shutil.disk_usage(C.WORKSPACE).free / 1e9
    line("디스크 여유 ≥ 10 GB (관찰 기록용)", free >= 10, f"{free:.1f} GB")
    print("결과:", "준비 완료" if ok else "필수 항목을 확인하세요")
    return 0 if ok else 1


def _chrome() -> bool:
    cands = ["/Applications/Google Chrome.app", r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    return any(Path(c).exists() for c in cands) or bool(shutil.which("google-chrome") or shutil.which("chromium"))


def cmd_observe(a) -> int:
    C.ensure_workspace()
    cfg = C.load_config()
    if a.action == "start":
        return observe.start(cfg, a.days, recorder=a.recorder)
    if a.action == "status":
        return observe.status(cfg)
    if a.action == "stop":
        if observe._load_state().get("recorder") == "builtin":
            return observe.stop()          # the built-in logger already writes metadata only
        exported = None
        if observe.health(cfg):
            try:
                exported = observe.export(cfg)
            except Exception as e:  # never leave the recorder running because export failed
                print(f"export 실패: {e} — 기록은 멈추고, 원본은 지우지 않고 남겨 둡니다.")
        rc = observe.stop()
        if exported is None:
            print("주의: 이번 기록의 메타데이터가 export 되지 않았습니다. 원본은 workspace/raw 에 남아 있습니다.")
        return rc
    if a.action == "export":
        return 0 if observe.export(cfg) else 1
    if a.action == "purge":
        return observe.purge_raw(force=a.yes)
    if a.action == "command":
        print(" ".join(observe.record_command(cfg)))
        return 0
    return 2


def _load_for_analysis(sample: bool) -> list[dict]:
    cfg = C.load_config()
    paths = [C.ROOT / "samples" / "synthetic_week" / "events.jsonl.gz"] if sample else sorted(list(C.OBS_DIR.glob("events-*.jsonl*")) + list(C.OBS_DIR.glob("builtin-*.jsonl")))
    if not paths:
        raise SystemExit("관찰 데이터가 없습니다. `wa observe start` 로 기록하거나 `wa analyze --sample` 로 데모를 보세요.")
    raw = observe.load_events(paths)
    kept = [e for e in (observe.clean_event(cfg, x["ts"], x["app"], x.get("title", ""), x.get("domain"), x.get("src", "?"))
                        for x in raw) if e]
    print(f"이벤트 {len(raw):,}개 읽음 · 개인정보 필터로 {len(raw) - len(kept):,}개 제외 · {len(kept):,}개 분석")
    return kept


def cmd_analyze(a) -> int:
    C.ensure_workspace()
    r = A.analyze(_load_for_analysis(a.sample))
    A.save(r)
    h, m = report.write(r)
    print(f"작업 {len(r['tasks'])}개 · 반복 루틴 {len(r['workflows'])}개 · 하루 {r['active_hours_per_day']}h · "
          f"주당 절약 가능 ~{r['est_hours_saved_per_week']}h (추정)")
    for t in r["tasks"][:8]:
        print(f"  {t['id']} {t['minutes_per_week']/60:4.1f}h/주  {report.VERDICT[t['verdict']][0]:<5} {t['name'][:60]}")
    _open_hint(str(h))
    print(f"  markdown: {m}")
    cfg = C.load_config()
    if not a.sample and not a.keep_raw and cfg.get("auto_delete_raw_after_analysis", True):
        if observe._pid_alive(observe._load_state().get("pid", 0)):
            print("  (기록 중이라 원본은 아직 지우지 않았습니다. `wa observe stop` 후 다시 analyze 하면 삭제됩니다.)")
        else:
            observe.purge_raw(force=True)
    return 0


def cmd_interview(a) -> int:
    C.ensure_workspace()
    return spec.create(a.id, a.tasks)


def cmd_spec(a) -> int:
    return spec.check(a.id)


def cmd_new(a) -> int:
    C.ensure_workspace()
    src = C.ROOT / "templates" / "automations" / a.tool
    dst = C.AUTO_DIR / a.id
    if dst.exists():
        print(f"이미 있습니다: {dst}")
        return 1
    shutil.copytree(src, dst)
    m = runner.manifest(dst)
    m.update(id=a.id, title=a.title or a.id, task_ids=a.tasks or [])
    runner.save_manifest(dst, m)
    print(f"자동화 생성: {dst}\n다음: spec 대로 run.py 구현 → wa test {a.id}")
    return 0


def cmd_test(a) -> int:
    return runner.test(a.id, require_spec=not a.no_spec)


def cmd_run(a) -> int:
    return runner.run(a.id, live=a.live, scheduled=a.scheduled)


def cmd_undo(a) -> int:
    return sdk.undo(a.run_id)


def cmd_approve(a) -> int:
    d = runner.find(a.id)
    m = runner.manifest(d)
    if a.action not in m.get("risky_actions", {}):
        print(f"'{a.action}' 은(는) 이 자동화의 risky_actions 에 없습니다: {list(m.get('risky_actions', {}))}")
        return 2
    return safety.approve(a.id, a.action, d, m["risky_actions"][a.action])


def cmd_revoke(a) -> int:
    return safety.revoke(a.id, a.action)


def cmd_lint(a) -> int:
    errors, warns = safety.lint(runner.find(a.id))
    for w in warns:
        print("  warn:", w)
    for e in errors:
        print("  ERROR:", e)
    print("lint", "FAILED" if errors else "OK")
    return 1 if errors else 0


def cmd_schedule(a) -> int:
    return scheduler.schedule(a.id, live=a.live, apply=a.apply)


def cmd_unschedule(a) -> int:
    return scheduler.unschedule(a.id)


def cmd_dashboard(_a) -> int:
    C.ensure_workspace()
    _open_hint(dashboard.write())
    return 0


def cmd_logs(a) -> int:
    for r in runner.recent_runs(a.n * 10):
        if a.id and r["automation"] != a.id:
            continue
        print(f"{r['start'][:19]}  {r['automation']:<24} {r['mode']:<4} {'OK  ' if r['ok'] else 'FAIL'} "
              f"ops={r['ops']} blocked={len(r['blocked'])} saved={r['minutes_saved']}m{' UNDONE' if r.get('undone') else ''}  {r['run_id']}")
    return 0


def cmd_demo(_a) -> int:
    """Whole flow on synthetic data. No screen recording, no network, nothing outside workspace/."""
    C.ensure_workspace()
    bar = lambda s: print(f"\n━━ {s} " + "━" * max(0, 60 - len(s)))
    bar("1 관찰 (데모: 화면 기록 대신 합성 데이터 사용)")
    print("  실제 사용 시: wa observe start --days 5   →   기록 명령 미리보기: wa observe command")
    bar("2 찾기")
    cmd_analyze(argparse.Namespace(sample=True, keep_raw=True))
    bar("3 인터뷰 (데모: 미리 답한 질문지)")
    C.SPEC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(C.ROOT / "examples" / "specs" / "demo-invoice-sorter.md", C.SPEC_DIR / "demo-invoice-sorter.md")
    spec.check("demo-invoice-sorter")
    bar("4 만들기 (데모 자동화 설치 + 가짜 파일)")
    dst = C.AUTO_DIR / "demo-invoice-sorter"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(C.ROOT / "examples" / "automations" / "demo-invoice-sorter", dst)
    inbox = C.WORKSPACE / "demo_files" / "Downloads"
    if (C.WORKSPACE / "demo_files").exists():
        shutil.rmtree(C.WORKSPACE / "demo_files")
    inbox.mkdir(parents=True)
    for n, v in [(1041, "AlphaParts"), (1042, "BetaLogistics"), (1043, "AlphaParts"), (1044, "GammaOffice")]:
        (inbox / f"Invoice_{n}_{v}.pdf").write_text("SYNTHETIC DEMO FILE — not a real invoice\n")
    (inbox / "회의록_메모.txt").write_text("SYNTHETIC DEMO FILE\n")
    print(f"  가짜 다운로드 폴더: {inbox} (PDF 4개 + 규칙 밖 파일 1개)")
    bar("5 테스트 (lint + dry-run — 아무것도 바뀌지 않음)")
    if runner.test("demo-invoice-sorter") != 0:
        return 1
    bar("5 실제 실행 (--live) — send_message 는 승인 전이라 차단돼야 정상")
    runner.run("demo-invoice-sorter", live=True)
    last = runner.recent_runs(1)[-1]
    bar("5 되돌리기 확인 (undo) → 다시 실행")
    sdk.undo(last["run_id"])
    print(f"  다운로드 폴더 파일 수: {len(list(inbox.iterdir()))}")
    runner.run("demo-invoice-sorter", live=True, quiet=True)
    print(f"  재실행 후 다운로드 폴더 파일 수: {len(list(inbox.iterdir()))}")
    bar("6 실행 (예약 계획만 표시 — 데모는 설치하지 않음)")
    scheduler.schedule("demo-invoice-sorter", live=True, apply=False)
    bar("대시보드")
    cmd_dashboard(None)
    print("\n데모 끝. 실제로 쓰려면: Claude Code 나 Codex 를 이 폴더에서 열고 \"시작하자\" 라고 말하세요.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wa", description="work-autopilot", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=FLOW)
    sp = p.add_subparsers(dest="cmd")
    sp.add_parser("help")
    sp.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sp.add_parser("demo").set_defaults(fn=cmd_demo)

    o = sp.add_parser("observe")
    o.add_argument("action", choices=["start", "status", "stop", "export", "purge", "command"])
    o.add_argument("--days", type=float, default=5)
    o.add_argument("--recorder", choices=["screenpipe", "builtin"], help="default: workspace/config.json 'recorder'")
    o.add_argument("--yes", action="store_true")
    o.set_defaults(fn=cmd_observe)

    an = sp.add_parser("analyze")
    an.add_argument("--sample", action="store_true", help="bundled synthetic week (fake data)")
    an.add_argument("--keep-raw", action="store_true", help="do not delete raw recordings afterwards")
    an.set_defaults(fn=cmd_analyze)

    i = sp.add_parser("interview")
    i.add_argument("id")
    i.add_argument("tasks", nargs="*")
    i.set_defaults(fn=cmd_interview)

    s = sp.add_parser("spec")
    s.add_argument("check", choices=["check"])
    s.add_argument("id")
    s.set_defaults(fn=cmd_spec)

    n = sp.add_parser("new")
    n.add_argument("id")
    n.add_argument("--tool", choices=["script", "browser-cdp", "app-api", "ai-step"], default="script")
    n.add_argument("--title")
    n.add_argument("--tasks", nargs="*")
    n.set_defaults(fn=cmd_new)

    t = sp.add_parser("test")
    t.add_argument("id")
    t.add_argument("--no-spec", action="store_true", help=argparse.SUPPRESS)
    t.set_defaults(fn=cmd_test)

    r = sp.add_parser("run")
    r.add_argument("id")
    r.add_argument("--live", action="store_true")
    r.add_argument("--scheduled", action="store_true", help=argparse.SUPPRESS)
    r.set_defaults(fn=cmd_run)

    u = sp.add_parser("undo")
    u.add_argument("run_id")
    u.set_defaults(fn=cmd_undo)

    ap = sp.add_parser("approve")
    ap.add_argument("id")
    ap.add_argument("action", choices=list(safety.RISKY))
    ap.set_defaults(fn=cmd_approve)

    rv = sp.add_parser("revoke")
    rv.add_argument("id")
    rv.add_argument("action", nargs="?")
    rv.set_defaults(fn=cmd_revoke)

    li = sp.add_parser("lint")
    li.add_argument("id")
    li.set_defaults(fn=cmd_lint)

    sc = sp.add_parser("schedule")
    sc.add_argument("id")
    sc.add_argument("--live", action="store_true")
    sc.add_argument("--apply", action="store_true")
    sc.set_defaults(fn=cmd_schedule)

    us = sp.add_parser("unschedule")
    us.add_argument("id")
    us.set_defaults(fn=cmd_unschedule)

    sp.add_parser("dashboard").set_defaults(fn=cmd_dashboard)

    lg = sp.add_parser("logs")
    lg.add_argument("id", nargs="?")
    lg.add_argument("-n", type=int, default=20)
    lg.set_defaults(fn=cmd_logs)

    a = p.parse_args(argv)
    if not getattr(a, "fn", None):
        print(FLOW)
        return 0
    return a.fn(a)

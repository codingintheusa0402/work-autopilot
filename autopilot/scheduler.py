"""Step 6 — Run on a schedule: launchd (macOS), cron (Linux), Task Scheduler (Windows).

`wa schedule <id>` only prints the plan. `--apply` installs it. `wa unschedule <id>` removes it.
"""
from __future__ import annotations

import os
import platform
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

from . import config as C
from .runner import find, manifest, save_manifest
from .safety import code_hash

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
LABEL = "local.work-autopilot.{id}"


def _cmd(auto_id: str, live: bool) -> list[str]:
    c = [sys.executable, str(C.ROOT / "wa.py"), "run", auto_id, "--scheduled"]
    return c + (["--live"] if live else [])


def _when(m: dict) -> tuple[int, int, list[int]]:
    s = m.get("schedule") or {}
    hh, mm = (int(x) for x in s.get("time", "09:00").split(":"))
    wd = s.get("weekdays", [1, 2, 3, 4, 5])  # 1=Mon … 7=Sun
    return hh, mm, wd


def plan(auto_id: str, live: bool) -> dict:
    d = find(auto_id)
    m = manifest(d)
    hh, mm, wd = _when(m)
    cmd = _cmd(auto_id, live)
    system = platform.system()
    if system == "Darwin":
        agents = Path(os.environ.get("WA_LAUNCHAGENTS_DIR", Path.home() / "Library" / "LaunchAgents"))
        label = LABEL.format(id=auto_id)
        plist = {
            "Label": label, "ProgramArguments": cmd, "WorkingDirectory": str(C.ROOT),
            "EnvironmentVariables": {"WA_WORKSPACE": str(C.WORKSPACE)},
            # launchd weekday: 0 or 7 = Sunday, 1 = Monday
            "StartCalendarInterval": [{"Weekday": w % 7, "Hour": hh, "Minute": mm} for w in wd],
            "StandardOutPath": str(C.LOG_DIR / f"launchd-{auto_id}.log"),
            "StandardErrorPath": str(C.LOG_DIR / f"launchd-{auto_id}.log"),
        }
        return {"system": "launchd", "path": str(agents / f"{label}.plist"), "plist": plist, "label": label}
    if system == "Windows":
        tr = subprocess.list2cmdline(cmd)
        days = ",".join(DAYS[w - 1] for w in wd)
        return {"system": "schtasks", "create": ["schtasks", "/Create", "/TN", f"work-autopilot\\{auto_id}", "/TR", tr,
                                                   "/SC", "WEEKLY", "/D", days, "/ST", f"{hh:02d}:{mm:02d}", "/F"],
                "delete": ["schtasks", "/Delete", "/TN", f"work-autopilot\\{auto_id}", "/F"]}
    dow = ",".join(str(w % 7) for w in wd)
    line = (f"{mm} {hh} * * {dow} cd {shlex.quote(str(C.ROOT))} && WA_WORKSPACE={shlex.quote(str(C.WORKSPACE))} "
            f"{' '.join(shlex.quote(x) for x in cmd)} >> {shlex.quote(str(C.LOG_DIR / ('cron-' + auto_id + '.log')))} 2>&1"
            f" # work-autopilot:{auto_id}")
    return {"system": "cron", "line": line}


def schedule(auto_id: str, live: bool, apply: bool) -> int:
    d = find(auto_id)
    m = manifest(d)
    if m.get("status") not in ("tested", "scheduled") or m.get("tested_hash") != code_hash(d):
        print("예약하려면 먼저 `wa test` 를 통과해야 합니다 (코드가 바뀌면 다시).")
        return 2
    p = plan(auto_id, live)
    mode = "LIVE" if live else "DRY-RUN"
    print(f"[{p['system']}] {auto_id} · {mode} · {m.get('schedule')}")
    if p["system"] == "launchd":
        print(f"  plist → {p['path']}")
    elif p["system"] == "cron":
        print("  crontab +", p["line"])
    else:
        print("  ", subprocess.list2cmdline(p["create"]))
    if not apply:
        print("\n(계획만 보여줬습니다. 설치하려면 --apply)")
        return 0
    if p["system"] == "launchd":
        path = Path(p["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            plistlib.dump(p["plist"], f)
        if not os.environ.get("WA_SCHEDULER_NOLOAD"):
            uid = os.getuid()
            subprocess.call(["launchctl", "bootout", f"gui/{uid}", str(path)], stderr=subprocess.DEVNULL)
            subprocess.check_call(["launchctl", "bootstrap", f"gui/{uid}", str(path)])
    elif p["system"] == "cron":
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        keep = [x for x in cur.splitlines() if not x.endswith(f"# work-autopilot:{auto_id}")]
        subprocess.run(["crontab", "-"], input="\n".join(keep + [p["line"]]) + "\n", text=True, check=True)
    else:
        subprocess.check_call(p["create"])
    m["status"] = "scheduled"
    m["scheduled"] = {"mode": mode.lower(), "system": p["system"]}
    save_manifest(d, m)
    # keep the tested hash valid: status fields are excluded from the hash
    print("예약 완료. 해제: wa unschedule " + auto_id)
    return 0


def unschedule(auto_id: str) -> int:
    d = find(auto_id)
    m = manifest(d)
    p = plan(auto_id, False)
    if p["system"] == "launchd":
        path = Path(p["path"])
        if not os.environ.get("WA_SCHEDULER_NOLOAD"):
            subprocess.call(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)], stderr=subprocess.DEVNULL)
        path.unlink(missing_ok=True)
    elif p["system"] == "cron":
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        keep = [x for x in cur.splitlines() if not x.endswith(f"# work-autopilot:{auto_id}")]
        subprocess.run(["crontab", "-"], input="\n".join(keep) + ("\n" if keep else ""), text=True, check=True)
    else:
        subprocess.call(p["delete"])
    m.pop("scheduled", None)
    if m.get("status") == "scheduled":
        m["status"] = "tested"
    save_manifest(d, m)
    print("예약 해제 완료.")
    return 0

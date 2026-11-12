"""Built-in activity logger — the license-free alternative to screenpipe.

Every few seconds it notes the app in front, its window title and the time. Optionally it saves
a screenshot of ONLY that front window (never the whole screen). Everything stays on this
computer; no network code at all. Same privacy excludes as screenpipe, plus an optional
include-list so you can record only the windows you choose.

  macOS   : tested. Uses osascript (JavaScript for Automation) + `screencapture -l <window>`.
            Window titles need Screen Recording permission for your terminal app; without it
            only app names are logged (analysis still works, just coarser).
  Windows : UNTESTED. Uses ctypes (user32/kernel32) + PowerShell for window screenshots.
  Linux   : UNTESTED, best effort with `xdotool` if installed.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from . import config as C
from .observe import clean_event, is_excluded

SHOTS = C.RAW_DIR / "builtin_shots"

_JXA = r"""
ObjC.import('AppKit'); ObjC.import('CoreGraphics');
var app = $.NSWorkspace.sharedWorkspace.frontmostApplication;
var pid = app.processIdentifier, name = ObjC.unwrap(app.localizedName);
var list = ObjC.deepUnwrap($.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly | $.kCGWindowListExcludeDesktopElements, 0)) || [];
var title = '', wid = 0;
for (var i = 0; i < list.length; i++) { var w = list[i];
  if (w.kCGWindowOwnerPID === pid && w.kCGWindowLayer === 0) { title = w.kCGWindowName || ''; wid = w.kCGWindowNumber; break; } }
JSON.stringify({app: name, title: title, wid: wid});
"""


def front_window() -> dict | None:
    system = platform.system()
    try:
        if system == "Darwin":
            out = subprocess.run(["osascript", "-l", "JavaScript", "-e", _JXA], capture_output=True, text=True, timeout=5)
            return json.loads(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
        if system == "Windows":
            return _front_windows()
        out = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, timeout=5)
        pid = subprocess.run(["xdotool", "getactivewindow", "getwindowpid"], capture_output=True, text=True, timeout=5).stdout.strip()
        app = Path(os.readlink(f"/proc/{pid}/exe")).name if pid else "unknown"
        return {"app": app, "title": out.stdout.strip(), "wid": 0}
    except Exception:
        return None


def _front_windows() -> dict | None:  # pragma: no cover - Windows only, untested
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = u32.GetForegroundWindow()
    n = u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k32.OpenProcess(0x1000, False, pid.value)
    exe = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(1024)
    name = "unknown"
    if h and k32.QueryFullProcessImageNameW(h, 0, exe, ctypes.byref(size)):
        name = Path(exe.value).stem
    if h:
        k32.CloseHandle(h)
    return {"app": name, "title": buf.value, "wid": int(hwnd)}


def idle_seconds() -> float:
    system = platform.system()
    try:
        if system == "Darwin":
            out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                if "HIDIdleTime" in line:
                    return int(line.split("=")[-1].strip()) / 1e9
        if system == "Windows":  # pragma: no cover
            import ctypes

            class LII(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LII()
            lii.cbSize = ctypes.sizeof(LII)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000
    except Exception:
        pass
    return 0.0


def included(cfg: dict, app: str, title: str) -> bool:
    inc = [x.lower() for x in cfg.get("include_windows", []) if x]
    if not inc:
        return True
    hay = f"{app} {title}".lower()
    return any(x in hay for x in inc)


def screenshot(win: dict, path: Path) -> bool:
    """Capture only the front window (macOS: screencapture -l). Never the whole screen."""
    path.parent.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == "Darwin" and win.get("wid"):
        r = subprocess.run(["screencapture", "-x", "-o", "-t", "jpg", "-l", str(win["wid"]), str(path)],
                           capture_output=True, timeout=15)
        return r.returncode == 0 and path.exists()
    if system == "Windows" and win.get("wid"):  # pragma: no cover - untested
        ps = ("Add-Type -AssemblyName System.Drawing;Add-Type @'\nusing System;using System.Runtime.InteropServices;"
              "public class W{[DllImport(\"user32.dll\")]public static extern bool GetWindowRect(IntPtr h,out RECT r);"
              "public struct RECT{public int L,T,R,B;}}\n'@;$r=New-Object W+RECT;[W]::GetWindowRect([IntPtr]" + str(win["wid"]) +
              ",[ref]$r)|Out-Null;$b=New-Object System.Drawing.Bitmap(($r.R-$r.L),($r.B-$r.T));"
              "$g=[System.Drawing.Graphics]::FromImage($b);$g.CopyFromScreen($r.L,$r.T,0,0,$b.Size);"
              f"$b.Save('{path}',[System.Drawing.Imaging.ImageFormat]::Jpeg)")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=30)
        return r.returncode == 0 and path.exists()
    return False


def loop(cfg: dict, until: dt.datetime, max_ticks: int | None = None) -> int:
    """Main loop of the background logger process."""
    interval = float(cfg.get("logger_interval_s", 10))
    shot_every = float(cfg.get("logger_screenshot_every_s", 0))
    idle_cap = float(cfg.get("logger_idle_s", 300))
    C.OBS_DIR.mkdir(parents=True, exist_ok=True)
    last_shot, ticks, kept, skipped = 0.0, 0, 0, 0
    while dt.datetime.now().astimezone() < until and (max_ticks is None or ticks < max_ticks):
        ticks += 1
        t0 = time.time()
        win = front_window()
        if win and idle_seconds() < idle_cap:
            app, title = win.get("app") or "unknown", win.get("title") or ""
            if is_excluded(cfg, app, title, None) or not included(cfg, app, title):
                skipped += 1           # excluded or not on the include list: nothing logged, no screenshot
            else:
                now = dt.datetime.now().astimezone()
                ev = clean_event(cfg, now.isoformat(timespec="seconds"), app, title, None, "builtin")
                out = C.OBS_DIR / f"builtin-{now:%Y%m%d}.jsonl"
                with open(out, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                kept += 1
                if shot_every > 0 and t0 - last_shot >= shot_every:
                    if screenshot(win, SHOTS / f"{now:%Y%m%d-%H%M%S}.jpg"):
                        last_shot = t0
        time.sleep(max(0.0, interval - (time.time() - t0)))
    print(f"builtin logger done: {kept} events logged, {skipped} skipped by privacy/include filters", flush=True)
    return 0


def run_from_state() -> int:
    """Entry for the detached process (`wa observe _logger`)."""
    state = json.loads((C.STATE_DIR / "observe.json").read_text())
    until = dt.datetime.fromisoformat(state["until"])
    return loop(C.load_config(), until)


if __name__ == "__main__":
    sys.exit(run_from_state())

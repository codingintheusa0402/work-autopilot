"""Step 1 — Observe. Thin wrapper around screenpipe (installed and run by screenpipe's own npm package).

We never vendor screenpipe. We start it with privacy flags, export only minimal metadata
(time, app, redacted window title, domain) and delete the raw recordings afterwards.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import config as C
from .redact import normalize_title, redact

SP_DATA = C.RAW_DIR / "screenpipe"
STATE = C.STATE_DIR / "observe.json"


# ---------------------------------------------------------------- privacy filters

def _lower_list(xs):
    return [x.lower() for x in xs or []]


def is_excluded(cfg: dict, app: str, title: str, url: str | None) -> bool:
    app_l, title_l, url_l = (app or "").lower(), (title or "").lower(), (url or "").lower()
    for a in _lower_list(cfg.get("excluded_apps")):
        if a and (a == app_l or a in app_l):
            return True
    for k in _lower_list(cfg.get("excluded_title_keywords")):
        if k and k in title_l:
            return True
    host = urllib.parse.urlparse(url_l).hostname or "" if url_l else ""
    for d in _lower_list(cfg.get("excluded_domains")):
        if host and (host == d or host.endswith("." + d)):
            return True
    return False


def short_domain(url: str | None) -> str | None:
    """Keep host + first path segment only (enough to tell Sheets from Docs). No query strings."""
    if not url:
        return None
    p = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    if not p.hostname:
        return None
    seg = [s for s in p.path.split("/") if s][:1]
    return p.hostname + ("/" + seg[0] if seg else "")


def clean_event(cfg: dict, ts: str, app: str, title: str, url: str | None, src: str) -> dict | None:
    if is_excluded(cfg, app, title, url):
        return None
    return {
        "ts": ts,
        "app": app or "unknown",
        "title": redact(title or "") if cfg.get("keep_window_titles", True) else normalize_title(title or ""),
        "domain": short_domain(url),
        "src": src,
    }


# ---------------------------------------------------------------- screenpipe process

def record_command(cfg: dict) -> list[str]:
    npx = shutil.which("npx") or "npx"
    cmd = [
        npx, "--yes", "screenpipe@latest", "record",
        "--data-dir", str(SP_DATA),
        "--port", str(cfg.get("screenpipe_port", 3031)),
        "--disable-telemetry",
        "--video-quality", "low",
        "--use-pii-removal=true",
        "--ignore-incognito-windows=true",
        "--disable-keyboard-capture",
        "--disable-clipboard-capture",
        "--retention-days", str(cfg.get("screenpipe_retention_days", 8)),
        "--retention-mode", "all",
    ]
    if not cfg.get("record_audio", False):
        cmd.append("--disable-audio")
    else:
        # local Whisper only. We never pass a cloud engine or a Deepgram key.
        cmd += ["--audio-transcription-engine", "whisper-large-v3-turbo-quantized"]
    for a in cfg.get("excluded_apps", []):
        cmd += ["--ignored-windows", a]
    for k in cfg.get("excluded_title_keywords", []):
        cmd += ["--ignored-windows", "::" + k]
    for d in cfg.get("excluded_domains", []):
        cmd += ["--url-block", d + ":subdomains"]
    return cmd


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(s: dict) -> None:
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2))


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def health(cfg: dict) -> dict | None:
    port = cfg.get("screenpipe_port", 3031)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def start(cfg: dict, days: int, extra: list[str] | None = None) -> int:
    lo, hi = cfg.get("observe_days_min", 3), cfg.get("observe_days_max", 7)
    if not lo <= days <= hi:
        print(f"관찰 기간은 {lo}~{hi}일 사이로 정해 주세요. (got {days})")
        return 2
    s = _load_state()
    if _pid_alive(s.get("pid", 0)):
        print(f"이미 기록 중입니다 (pid {s['pid']}). `wa observe status` 로 확인하세요.")
        return 0
    if not shutil.which("npx"):
        print("Node.js (npx) 가 필요합니다. https://nodejs.org 에서 설치 후 다시 실행하세요.")
        return 2
    SP_DATA.mkdir(parents=True, exist_ok=True)
    cmd = record_command(cfg) + (extra or [])
    log = open(C.LOG_DIR / "screenpipe.log", "ab")
    kw = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen(cmd, **kw)
    now = dt.datetime.now().astimezone()
    _save_state({"pid": p.pid, "started": now.isoformat(), "days": days,
                 "until": (now + dt.timedelta(days=days)).isoformat(), "port": cfg.get("screenpipe_port", 3031)})
    print(f"screenpipe 기록 시작 (pid {p.pid}). {days}일 뒤 `wa observe stop` → `wa analyze` 하세요.")
    print("macOS: 시스템 설정 → 개인정보 보호 및 보안 → '화면 및 시스템 오디오 기록'에서 터미널/node 를 허용해야 합니다.")
    return 0


def stop() -> int:
    s = _load_state()
    pid = s.get("pid", 0)
    if not _pid_alive(pid):
        print("기록 중인 screenpipe 가 없습니다.")
        s.pop("pid", None)
        _save_state(s)
        return 0
    try:
        if os.name == "nt":
            subprocess.call(["taskkill", "/PID", str(pid), "/T", "/F"])
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            for _ in range(30):
                if not _pid_alive(pid):
                    break
                time.sleep(0.5)
            if _pid_alive(pid):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    s["stopped"] = dt.datetime.now().astimezone().isoformat()
    s.pop("pid", None)
    _save_state(s)
    print("screenpipe 기록을 멈췄습니다.")
    return 0


def status(cfg: dict) -> int:
    s = _load_state()
    alive = _pid_alive(s.get("pid", 0))
    h = health(cfg) if alive else None
    print(json.dumps({"recording_process": alive, "pid": s.get("pid"), "started": s.get("started"),
                      "planned_until": s.get("until"), "health": (h or {}).get("status"),
                      "raw_dir_mb": round(_dir_size(SP_DATA) / 1e6, 1)}, ensure_ascii=False, indent=2))
    return 0


def _dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


# ---------------------------------------------------------------- export (metadata only)

def _get(url: str) -> dict:
    req = urllib.request.Request(url)
    key = os.environ.get("SCREENPIPE_LOCAL_API_KEY")  # only needed for non-localhost setups
    if key:
        req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def export(cfg: dict, start_iso: str | None = None, end_iso: str | None = None) -> Path | None:
    """Pull frames from the local screenpipe API and keep only time/app/title/domain. No screen text."""
    port = cfg.get("screenpipe_port", 3031)
    if not health(cfg):
        print(f"screenpipe API (127.0.0.1:{port}) 가 응답하지 않습니다. 기록 중일 때 export 하세요.")
        return None
    s = _load_state()
    start_iso = start_iso or s.get("started") or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
    end_iso = end_iso or dt.datetime.now(dt.timezone.utc).isoformat()
    out = C.OBS_DIR / f"events-{dt.datetime.now():%Y%m%d-%H%M}.jsonl.gz"
    kept = dropped = 0
    offset, limit = 0, 500
    with gzip.open(out, "wt", encoding="utf-8") as f:
        while True:
            q = urllib.parse.urlencode({"content_type": "ocr", "limit": limit, "offset": offset,
                                        "start_time": start_iso, "end_time": end_iso, "max_content_length": 1})
            data = _get(f"http://127.0.0.1:{port}/search?{q}").get("data", [])
            if not data:
                break
            for item in data:
                c = item.get("content", {})
                ev = clean_event(cfg, c.get("timestamp"), c.get("app_name"), c.get("window_name"),
                                 c.get("browser_url"), "screenpipe")
                if ev is None:
                    dropped += 1
                    continue
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                kept += 1
            offset += limit
    print(f"export: {kept} events kept, {dropped} dropped by privacy filter → {out}")
    return out


def purge_raw(force: bool = False) -> int:
    """Delete raw screen recordings (our own data dir only — never ~/.screenpipe)."""
    if _pid_alive(_load_state().get("pid", 0)):
        print("기록 중에는 삭제하지 않습니다. 먼저 `wa observe stop`.")
        return 2
    if not SP_DATA.exists():
        print("삭제할 raw 기록이 없습니다.")
        return 0
    size = _dir_size(SP_DATA)
    if not force:
        print(f"raw 기록 {size/1e6:.1f} MB 를 삭제하려면 --yes 를 붙이세요: {SP_DATA}")
        return 1
    shutil.rmtree(SP_DATA)
    print(f"raw 기록 삭제 완료 ({size/1e6:.1f} MB).")
    return 0


def load_events(paths: list[Path]) -> list[dict]:
    evs: list[dict] = []
    for p in paths:
        opener = gzip.open if str(p).endswith(".gz") else open
        with opener(p, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    evs.append(json.loads(line))
    return evs


if __name__ == "__main__":
    print(" ".join(record_command(C.load_config())))
    sys.exit(0)

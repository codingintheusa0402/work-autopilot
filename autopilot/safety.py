"""Safety rails: risky-action catalogue, per-automation approvals (human only), code hashing, lint."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

from . import config as C
from .redact import looks_sensitive

# Actions that always need the user's explicit OK, per automation, before a live run may do them.
RISKY = {
    "send_message": "메시지/메일/채팅 보내기 (send a message, email or chat)",
    "payment": "결제·송금 (payment or money transfer)",
    "purchase": "구매·주문 확정 (purchase / place an order)",
    "delete": "데이터 삭제 (delete data — we soft-delete into backups, still needs OK)",
    "submit_form": "외부 시스템에 제출·확정 (submit/confirm a form in another system)",
    "external_upload": "파일을 외부로 업로드·공유 (upload or share files outside this computer)",
}

APPROVALS = C.STATE_DIR / "approvals.json"


def code_hash(auto_dir: Path) -> str:
    """Hash of everything that defines the automation, minus its mutable status fields."""
    h = hashlib.sha256()
    for p in sorted(auto_dir.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts or p.suffix in (".pyc", ".log"):
            continue
        data = p.read_bytes()
        if p.name == "automation.json":
            m = json.loads(data)
            for k in ("status", "tested_hash", "tested_at", "scheduled"):
                m.pop(k, None)
            data = json.dumps(m, sort_keys=True).encode()
        h.update(p.relative_to(auto_dir).as_posix().encode())
        h.update(data)
    return h.hexdigest()[:16]


def _load() -> dict:
    try:
        return json.loads(APPROVALS.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def is_approved(auto_id: str, action: str, current_hash: str) -> bool:
    a = _load().get(auto_id, {}).get(action)
    return bool(a) and a.get("code_hash") == current_hash


def approve(auto_id: str, action: str, auto_dir: Path, describe: str) -> int:
    """Record the user's OK. Refuses without a real keyboard on the other end: an agent cannot approve."""
    if action not in RISKY:
        print(f"알 수 없는 동작: {action}. 가능한 값: {', '.join(RISKY)}")
        return 2
    if not sys.stdin.isatty():
        print("승인은 사용자 본인만 할 수 있습니다. 터미널에서 직접 실행하세요 (에이전트/스크립트에서는 거부됨).\n"
              "Approval needs a human at an interactive terminal; agents and scripts are refused.")
        return 3
    print(f"\n자동화 '{auto_id}' 가 다음 동작을 실제로 하도록 허용합니다:\n  · {RISKY[action]}\n  · 이 자동화에서: {describe}\n"
          "코드가 바뀌면 이 승인은 자동으로 무효가 됩니다.")
    typed = input(f"허용하려면 자동화 ID '{auto_id}' 를 그대로 입력하세요: ").strip()
    if typed != auto_id:
        print("취소했습니다.")
        return 1
    data = _load()
    data.setdefault(auto_id, {})[action] = {
        "approved_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "code_hash": code_hash(auto_dir),
    }
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    APPROVALS.write_text(json.dumps(data, indent=2))
    print("승인 기록 완료.")
    return 0


def revoke(auto_id: str, action: str | None = None) -> int:
    data = _load()
    if auto_id in data:
        if action:
            data[auto_id].pop(action, None)
        else:
            data.pop(auto_id)
        APPROVALS.write_text(json.dumps(data, indent=2))
    print("승인 취소 완료.")
    return 0


# ---------------------------------------------------------------- lint

DANGEROUS = [
    (re.compile(r"\b(os\.remove|os\.unlink|shutil\.rmtree|\.unlink\(|Remove-Item|\brm\s+-)"), "delete",
     "직접 삭제 대신 run.delete() 를 쓰세요 (백업 후 소프트 삭제)"),
    (re.compile(r"(smtplib|sendmail|chat\.postMessage|hooks\.slack\.com|webhook|send_message|Send-MailMessage)", re.I),
     "send_message", "메시지 전송은 run.risky('send_message', ...) 안에서만"),
    (re.compile(r"(checkout|place.?order|buy.?now|결제|구매하기|purchase)", re.I), "purchase",
     "구매/결제 흐름은 run.risky('purchase'|'payment', ...) 안에서만"),
    (re.compile(r"\b(type|fill|send_keys|press_sequentially)\(.*(pass|pwd|비밀번호|card|카드)", re.I), "secret",
     "비밀번호·카드번호를 입력하는 코드는 허용되지 않습니다"),
]


def lint(auto_dir: Path) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    manifest = json.loads((auto_dir / "automation.json").read_text(encoding="utf-8"))
    declared = set(manifest.get("risky_actions", {}))
    for a in declared:
        if a not in RISKY:
            errors.append(f"automation.json: 알 수 없는 risky action '{a}'")
    for p in sorted(auto_dir.rglob("*")):
        if not p.is_file() or p.suffix not in (".py", ".js", ".ts", ".ps1", ".sh", ".json", ".md", ".txt"):
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            where = f"{p.relative_to(auto_dir)}:{n}"
            reason = looks_sensitive(line)
            if reason:
                errors.append(f"{where}: 민감한 값처럼 보입니다 ({reason}) — 코드/설정에 저장 금지")
            if p.suffix not in (".py", ".js", ".ts", ".ps1", ".sh"):
                continue
            for rx, kind, msg in DANGEROUS:
                if rx.search(line) and "run.risky" not in line and "run.delete" not in line and not line.lstrip().startswith("#"):
                    if kind == "secret":
                        errors.append(f"{where}: {msg}")
                    elif kind not in declared:
                        errors.append(f"{where}: '{kind}' 동작이 보이는데 automation.json risky_actions 에 선언되지 않았습니다 — {msg}")
                    else:
                        warns.append(f"{where}: {msg}")
    return errors, warns

"""What an automation script imports. Every side effect goes through a Run so it is
dry-run by default, logged, reversible, and gated when risky.

    from autopilot.sdk import Run
    with Run() as run:
        run.move(src, dst)                         # reversible
        run.write_text(path, text)                 # previous content backed up
        run.delete(path)                           # soft delete into backups; needs approval
        run.risky("send_message", "팀 채널에 요약 전송", lambda: post(...))   # needs approval
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

from . import config as C
from .redact import looks_sensitive, redact
from .safety import RISKY, code_hash, is_approved


class SensitiveValueError(RuntimeError):
    pass


class Run:
    def __init__(self) -> None:
        self.auto_dir = Path(os.environ.get("WA_AUTOMATION_DIR", Path.cwd())).resolve()
        manifest = json.loads((self.auto_dir / "automation.json").read_text(encoding="utf-8"))
        self.id = manifest["id"]
        self.declared = manifest.get("risky_actions", {})
        self.mode = os.environ.get("WA_MODE", "dry")          # dry unless the runner says live
        self.live = self.mode == "live"
        self.run_id = os.environ.get("WA_RUN_ID") or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.backup = C.BACKUP_DIR / self.run_id
        self.preview = C.DRYRUN_DIR / self.run_id
        self.ops: list[dict] = []
        self.blocked: list[str] = []
        self._hash = code_hash(self.auto_dir)

    # -------------------------------------------------- context
    def __enter__(self) -> "Run":
        self.log(f"start {self.id} mode={self.mode} run={self.run_id}")
        return self

    def __exit__(self, et, ev, tb) -> bool:
        self._flush()
        if et:
            self.log(f"FAILED: {et.__name__}: {redact(str(ev), numbers=False)}")
        else:
            self.log(f"done: {len(self.ops)} ops, {len(self.blocked)} blocked")
        return False

    # -------------------------------------------------- logging
    def log(self, msg: str) -> None:
        print(f"[{dt.datetime.now():%H:%M:%S}] {'DRY ' if not self.live else ''}{redact(msg, numbers=False)}", flush=True)

    def _record(self, op: dict) -> None:
        self.ops.append(op)
        self._flush()

    def _flush(self) -> None:
        if not self.ops and not self.blocked:
            return
        target = self.backup if self.live else self.preview
        target.mkdir(parents=True, exist_ok=True)
        (target / "ops.json").write_text(json.dumps(
            {"automation": self.id, "run_id": self.run_id, "mode": self.mode, "ops": self.ops, "blocked": self.blocked},
            ensure_ascii=False, indent=2), encoding="utf-8")

    # -------------------------------------------------- guards
    def guard_value(self, value: str) -> str:
        """Call before typing/storing any user-provided value. Passwords, card numbers, IDs are refused."""
        reason = looks_sensitive(value)
        if reason:
            raise SensitiveValueError(f"refusing to type/store a {reason}")
        return value

    # -------------------------------------------------- file ops (reversible)
    def move(self, src: str | Path, dst: str | Path) -> None:
        src, dst = Path(src).resolve(), Path(dst).resolve()
        if dst.exists():
            raise FileExistsError(f"{dst} already exists; refusing to overwrite")
        if not self.live:
            self.log(f"would move {src.name} → {dst.parent.name}/{dst.name}")
            self._record({"op": "move", "src": str(src), "dst": str(dst), "dry": True})
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        self.log(f"moved {src.name} → {dst.parent.name}/{dst.name}")
        self._record({"op": "move", "src": str(src), "dst": str(dst)})

    def copy(self, src: str | Path, dst: str | Path) -> None:
        src, dst = Path(src).resolve(), Path(dst).resolve()
        if not self.live:
            self.log(f"would copy {src.name} → {dst}")
            self._record({"op": "copy", "src": str(src), "dst": str(dst), "dry": True})
            return
        prev = self._backup_file(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        self.log(f"copied {src.name} → {dst.name}")
        self._record({"op": "write", "path": str(dst), "backup": prev})

    def write_text(self, path: str | Path, text: str) -> Path:
        path = Path(path).resolve()
        if not self.live:
            out = self.preview / "files" / path.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            self.log(f"would write {path.name} (preview: {out})")
            self._record({"op": "write", "path": str(path), "preview": str(out), "dry": True})
            return out
        prev = self._backup_file(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.log(f"wrote {path.name}")
        self._record({"op": "write", "path": str(path), "backup": prev})
        return path

    def delete(self, path: str | Path) -> None:
        path = Path(path).resolve()
        if not self._allowed("delete", f"delete {path.name}"):
            return
        if not self.live:
            self.log(f"would delete {path.name} (soft, into backups)")
            self._record({"op": "delete", "path": str(path), "dry": True})
            return
        prev = self._backup_file(path, move=True)
        self.log(f"deleted {path.name} (kept in backups)")
        self._record({"op": "delete", "path": str(path), "backup": prev})

    def _backup_file(self, path: Path, move: bool = False) -> str | None:
        if not path.exists():
            return None
        dest = self.backup / "files" / f"{len(self.ops):04d}_{path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        (shutil.move if move else shutil.copy2)(str(path), str(dest))
        return str(dest)

    # -------------------------------------------------- risky actions
    def _allowed(self, action: str, what: str) -> bool:
        if action not in RISKY:
            raise ValueError(f"unknown risky action {action}")
        if action not in self.declared:
            raise PermissionError(f"'{action}' is not declared in automation.json risky_actions")
        if self.live and not is_approved(self.id, action, self._hash):
            self.log(f"BLOCKED (not approved by the user): {action} — {what}. "
                     f"User runs: wa approve {self.id} {action}")
            self.blocked.append(f"{action}: {what}")
            self._flush()
            return False
        return True

    def risky(self, action: str, what: str, fn: Callable[[], Any]) -> Any:
        """Do something irreversible (send, pay, buy, submit, upload) only when live AND approved."""
        if not self._allowed(action, what):
            return None
        if not self.live:
            self.log(f"would {action}: {what}")
            self._record({"op": "risky", "action": action, "what": what, "dry": True})
            return None
        result = fn()
        self.log(f"did {action}: {what}")
        self._record({"op": "risky", "action": action, "what": what, "irreversible": True})
        return result


def undo(run_id: str) -> int:
    ops_file = C.BACKUP_DIR / run_id / "ops.json"
    if not ops_file.exists():
        print(f"되돌릴 기록이 없습니다: {run_id} (dry-run 은 바꾼 것이 없어 되돌릴 필요가 없습니다)")
        return 1
    data = json.loads(ops_file.read_text(encoding="utf-8"))
    undone = 0
    for op in reversed(data["ops"]):
        if op.get("dry"):
            continue
        if op["op"] == "move":
            src, dst = Path(op["src"]), Path(op["dst"])
            if dst.exists() and not src.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                undone += 1
        elif op["op"] in ("write", "delete"):
            p = Path(op["path"])
            if op.get("backup"):
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(op["backup"], p)
            elif p.exists() and op["op"] == "write":
                p.unlink()
            undone += 1
        elif op["op"] == "risky":
            print(f"  ! 되돌릴 수 없는 동작 (직접 확인 필요): {op['action']} — {op['what']}")
    data["undone_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    ops_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"되돌리기 완료: {undone}개 작업 원상복구 ({run_id})")
    return 0


if __name__ == "__main__":
    sys.exit(undo(sys.argv[1]) if len(sys.argv) > 1 else 0)

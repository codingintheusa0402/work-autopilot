"""DEMO (synthetic): AI only for the judgment step.

For each fake customer message: ask the agent CLI (claude -p / codex exec) for a category and a short
reply draft. Only the message text is sent to the AI provider — no screens, no recordings, no IDs.
Drafts are written locally; sending is a separate risky action that needs approval.
Without an agent CLI the step falls back to a simple keyword rule and says so."""
import json
import os
import shutil
import subprocess
from pathlib import Path

from autopilot.sdk import Run

PROMPT = ("You triage customer messages for a small office. Reply with ONLY a JSON object "
          '{"category": "shipping|refund|product|other", "draft": "<2-sentence polite reply in Korean>"} '
          "for this message:\n\n")


def ask(cmd, text):
    out = subprocess.run(cmd + [PROMPT + text], capture_output=True, text=True, timeout=240).stdout.strip()
    start, end = out.find("{"), out.rfind("}")
    return json.loads(out[start:end + 1])


def rule(text):
    t = text.lower()
    cat = "shipping" if ("배송" in t or "ship" in t) else "refund" if ("환불" in t or "refund" in t) else "other"
    return {"category": cat, "draft": "(규칙 기반 분류 — AI 없이 생성된 자리표시 초안)"}


with Run() as run:
    m = json.loads(Path("automation.json").read_text(encoding="utf-8"))
    ws = os.environ["WA_WORKSPACE"]
    msgs = json.loads(Path(m["params"]["inbox_json"].replace("{workspace}", ws)).read_text(encoding="utf-8"))
    cmd = {"claude": ["claude", "-p"], "codex": ["codex", "exec"]}[m["params"].get("agent", "claude")]
    use_ai = bool(shutil.which(cmd[0])) and not os.environ.get("WA_NO_AI")
    run.log(f"AI 단계: {'사용 (' + cmd[0] + ')' if use_ai else '없음 → 키워드 규칙'} · 메시지 {len(msgs)}건")
    out = ["# 답장 초안 (보내지 않음)\n"]
    for msg in msgs:
        text = run.guard_value(msg["text"])
        try:
            res = ask(cmd, text) if use_ai else rule(text)
        except Exception as e:                       # AI failed → keep going with the rule, log it
            run.log(f"AI 실패 ({type(e).__name__}) → 규칙으로 대체: {msg['id']}")
            res = rule(text)
        run.log(f"{msg['id']}: {res['category']}")
        out.append(f"## {msg['id']} · {res['category']}\n> {text}\n\n{res['draft']}\n")
        run.risky("send_message", f"{msg['id']} 답장 보내기", lambda: None)
    run.write_text(m["params"]["drafts_md"].replace("{workspace}", ws), "\n".join(out))

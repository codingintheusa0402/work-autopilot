# CLAUDE.md — work-autopilot

This repo is driven by an agent. The full playbook is in AGENTS.md (shared with Codex) and is imported here:

@AGENTS.md

## Claude Code specifics
- When the user says "시작하자" / "let's start": run `./wa doctor`, offer `./wa demo`, then begin step 1 (Observe).
- Approvals: ask the user to type `! ./wa approve <id> <action>` themselves. Never run it for them and never work
  around its interactive check.
- Never use screenshot/recording upload tools on the user's screen data. Work from `workspace/reports/analysis.json`.
- Browser work: prefer attaching to the user's separate automation Chrome (CDP, see `templates/automations/browser-cdp`)
  over opening new browser profiles. Close only the tabs you opened.
- If something truly needs the user (OS permission dialog, login, 2FA), say exactly what to click and keep working on
  everything that isn't blocked.

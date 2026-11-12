# work-autopilot

**내 업무를 며칠 지켜보고, 자동화할 만한 일을 찾아서, 하나씩 물어본 다음 만들어 주는 도구.**
Claude Code 나 Codex 가 처음부터 끝까지 안내합니다. 설치는 명령어 한 줄.

[English below](#english)

![데모: 합성 데이터로 관찰 → 분석 → 자동화 → 되돌리기 → 대시보드](docs/images/demo.gif)

---

## 이런 분께

매일 하는 일 중에 "이거 누가 대신 해줬으면…" 싶은 게 있는데, 뭘 어떻게 자동화해야 할지 모르겠는 분.
엑셀에서 복사해서 사내 시스템에 붙여넣기, 다운로드 폴더 정리, 같은 양식의 메일 답장, 매주 같은 보고서 만들기 같은 일들이요.

work-autopilot 은 이렇게 움직입니다.

| 단계 | 하는 일 | 사용자가 하는 일 |
|---|---|---|
| 1. 관찰 | 3~7일 동안 내 컴퓨터 작업을 **내 컴퓨터 안에서만** 기록 — [screenpipe](https://github.com/screenpipe/screenpipe) 또는 라이선스 걱정 없는 **내장 기록기** 중 선택 | 기록기·기간 고르기, 권한 허용 |
| 2. 찾기 | 어떤 일에 시간을 얼마나, 몇 번 쓰는지 분석해서 작업마다 **자동화 / AI 보조 / 사람이 계속** 점수를 매긴 리포트 | 리포트 보기 |
| 3. 인터뷰 | 에이전트가 애매한 것을 계속 물어봄 — 이 단계는 무슨 뜻인지, 언제 '끝'인지, 예외는 뭔지, 승인이 필요한 건 뭔지 | 대답하기 |
| 4. 만들기 | 일에 맞는 도구로 구현: 스크립트, 앱 API, 브라우저 자동화(CDP/MCP), 꼭 필요한 곳만 AI | — |
| 5. 테스트 | 무조건 dry-run(미리보기) 먼저 → 결과 확인 → 고치고 반복. 실패는 기록 | 결과 확인 |
| 6. 실행 | 예약 실행(Mac launchd / Windows 작업 스케줄러 / Linux cron) + 대시보드에서 아낀 시간 확인 | 승인하기 |

모든 일을 자동화해 준다고 약속하지 않습니다. **자동화할 수 있는 것은 최대한, 사람이 해야 하는 것은 사람에게.**
회의나 판단이 필요한 일은 리포트에서 솔직하게 "사람 유지"라고 나옵니다.

## 분석 리포트 (합성 데이터 예시)

![업무 분석 리포트](docs/images/report.png)

작업별로 주당 시간, 하루 횟수, 주로 하는 시간, 세 가지 점수(자동화 / AI 보조 / 사람), 절약 추정치를 보여 주고,
"메일 확인 → 엑셀 → ERP 입력 → 회신"처럼 **매일 같은 순서로 여러 앱을 오가는 루틴**도 찾아냅니다.

## 설치 (명령어 한 줄)

필요한 것: Python 3.9 이상. 관찰 단계에는 Node.js 가 추가로 필요합니다. Claude Code 또는 Codex 를 권장합니다.

**Mac / Linux**
```bash
git clone https://github.com/codingintheusa0402/work-autopilot.git && cd work-autopilot && ./setup.sh --demo
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/codingintheusa0402/work-autopilot.git; cd work-autopilot; powershell -ExecutionPolicy Bypass -File setup.ps1 -Demo
```

`setup` 은 시스템에 아무것도 설치하지 않습니다. 개인 폴더 `workspace/` 를 만들고, **어떤 기록기를 쓸지 묻고**
(screenpipe / 내장 기록기), 환경을 점검하고, 자체 테스트를 돌린 뒤 `--demo` 면 **가짜 데이터로 전체 흐름**을 보여 줍니다.
화면은 기록하지 않습니다. 질문 없이 정하려면 `./setup.sh --recorder=builtin` (Windows: `-Recorder builtin`).

## 시작하기

```bash
cd work-autopilot
claude        # 또는 codex
> 시작하자
```

에이전트가 `CLAUDE.md` / `AGENTS.md` 에 적힌 순서대로 안내합니다. 직접 하고 싶다면 `./wa help` (Windows: `wa.cmd help`).

```text
./wa observe start --days 5     # 1 관찰 시작 (3~7일)
./wa observe stop               #   기록 종료 (메타데이터만 남기고 멈춤)
./wa analyze                    # 2 리포트 → workspace/reports/report.html (원본 기록은 자동 삭제)
./wa interview order-entry T03 T05   # 3 질문지 → 에이전트가 하나씩 물어봄
./wa new order-entry --tool browser-cdp   # 4 템플릿으로 만들기
./wa test order-entry           # 5 lint + dry-run
./wa run order-entry --live     #   실제 실행 (테스트 통과한 코드만)
./wa undo <run_id>              #   되돌리기
./wa schedule order-entry --live --apply  # 6 예약
./wa dashboard                  #   대시보드
```

## 안전장치 (코드로 강제됩니다)

- **비밀번호·카드번호·주민번호는 저장도 입력도 하지 않습니다.** 로그인은 사용자가 직접. 자동화 코드에 그런 값이 보이면 `wa test` 가 실패합니다.
- **결제·구매·메시지 발송·삭제·외부 제출·업로드**는 자동화마다 사용자가 터미널에서 직접 `wa approve` 해야만 실행됩니다.
  에이전트나 스크립트는 승인할 수 없게 막혀 있고, 코드가 바뀌면 승인은 자동으로 무효가 됩니다.
- **dry-run 이 기본**입니다. 실제 실행(`--live`)은 dry-run 을 통과한 바로 그 코드만 가능합니다.
- **모든 실행은 기록되고 되돌릴 수 있습니다.** 파일 변경은 백업 후 진행되고 `wa undo` 로 원상복구. 보내기처럼 되돌릴 수 없는 동작은 그렇다고 표시됩니다.
- **데이터는 내 컴퓨터에만.** 기록·리포트·로그·내 자동화는 전부 `workspace/` 에 있고 `.gitignore` 로 막혀 있습니다.

![자동화 대시보드](docs/images/dashboard.png)

## 개인정보 기본값 (모두 ON)

- 로컬 전용. 원본 화면이나 음성을 어떤 클라우드에도 보내지 않습니다. screenpipe 텔레메트리도 끕니다.
- 비밀번호 관리자(1Password, Bitwarden …), 은행·결제(토스, 카카오뱅크, PayPal …), 개인 메신저(카카오톡, WhatsApp, Telegram …),
  시크릿 창은 **기록에서 제외**됩니다. 목록: [`config/privacy.default.json`](config/privacy.default.json)
- 음성, 키보드 입력, 클립보드는 기록하지 않습니다 (음성은 원하면 켤 수 있고, 켜도 로컬 Whisper 만 사용).
- 분석에는 **시간, 앱 이름, 가린 창 제목, 사이트 도메인**만 씁니다. 이메일·전화번호·긴 숫자는 제목에서 가립니다.
- **분석이 끝나면 원본 기록은 자동 삭제**됩니다.

## 기록기 고르기: screenpipe 또는 내장 기록기

> **screenpipe 라이선스 요약** — 개인적·비상업적 사용은 무료, **회사에서는 7일 평가까지 무료**,
> 그보다 오래 회사 업무에 쓰려면 **screenpipe 유료 플랜**이 필요합니다. 회사 컴퓨터라면 아래 내장 기록기를 권합니다.

| | screenpipe | 내장 기록기 (`builtin`) |
|---|---|---|
| 기록하는 것 | 화면 텍스트(접근성/OCR) + 앱·창 제목 | 앞에 있는 앱 이름 · 창 제목 · 시간 (10초마다) |
| 스크린샷 | 앞 창 밖은 검게 가림, 분석 후 삭제 | 기본 끔. 켜면 **앞 창만** 캡처 (`logger_screenshot_every_s`), 분석 후 삭제 |
| 라이선스 | 소스 공개, 회사 7일 평가 후 유료 | 이 저장소와 같은 MIT. 추가 설치 없음 |
| 텔레메트리 | `--disable-telemetry` 로 끔 | 네트워크 코드 자체가 없음 |
| 개인정보 제외 목록 | 적용 | 같은 목록 적용 (제외 앱이 앞에 있으면 기록·스크린샷 안 함) |
| 분석 정확도 | 더 높음 | 앱/창 단위 — 대부분의 반복 업무를 찾기엔 충분 |
| 지원 | macOS 테스트 완료 | macOS 테스트 완료 · Windows/Linux **미검증(untested)** |

```bash
./wa observe start --days 5 --recorder builtin    # 또는 --recorder screenpipe
```

특정 앱·창만 기록하고 싶으면 `workspace/config.json` 에 `"include_windows": ["Excel", "ERP"]` 처럼 적으세요. 두 기록기 모두 적용됩니다.
macOS 에서 내장 기록기의 창 제목 수집은 **실험적**입니다. 터미널 앱에 **화면 및 시스템 오디오 기록** 권한이 있어도 최신 macOS 에서는
제목이 비어 올 수 있고, 그때는 앱 이름 단위로 기록·분석합니다 (`include_windows` 도 앱 이름으로 적으세요).

**macOS 에서 screenpipe 화면이 비어 있거나(단색) "no displays enumerated" 가 보이면:** 시스템 설정 → 개인정보 보호 및 보안 →
화면 및 시스템 오디오 기록 → **+** 로 screenpipe 실행 파일 자체를 추가하세요. 경로는 `./wa observe binary` 로 확인합니다.
터미널 권한만으로는 부족할 수 있습니다 (실제 테스트에서 확인).

## screenpipe 에 대해 꼭 알아 두세요

screenpipe 는 다른 회사의 소프트웨어이고, 이 저장소에 포함돼 있지 않습니다. 관찰을 시작하면 screenpipe 의 공식 npm 패키지
(`npx screenpipe record`)가 받아집니다. 데스크톱 앱은 [screenpipe.com/how-to-install](https://screenpipe.com/how-to-install) 에서.

**오픈소스가 아닙니다.** "Screenpipe Commercial License" 라는 소스 공개(source-available) 라이선스이고,
개인적·비상업적 사용, 비영리·교육·연구, 그리고 **조직 규모와 상관없이 최대 7일 평가**가 무료로 허용됩니다.
상업적 사용은 별도 라이선스가 필요하고, 공식 빌드는 screenpipe 약관과 요금제를 따릅니다.
회사에서 쓰기 전에 [LICENSE.md](https://github.com/screenpipe/screenpipe/blob/main/LICENSE.md), [요금제](https://screenpipe.com/pricing),
그리고 **회사의 승인**을 꼭 확인하세요. 자세히: [`docs/screenpipe.md`](docs/screenpipe.md)

## 폴더 구조

```text
work-autopilot/
├── setup.sh / setup.ps1        한 줄 설치 (Mac·Linux / Windows)
├── wa · wa.cmd · wa.py         CLI
├── CLAUDE.md · AGENTS.md       에이전트가 따르는 진행 순서와 안전 규칙
├── autopilot/                  관찰·분석·리포트·인터뷰·실행·예약·대시보드 (Python 표준 라이브러리만 사용)
├── config/                     개인정보 기본값, 작업 분류 규칙
├── templates/automations/      script · browser-cdp · app-api · ai-step 템플릿
├── examples/                   데모 자동화 4개 (파일 정리 · 웹 ERP 입력 · API 티켓 · AI 분류) + 미리 답한 질문지
├── tools/                      합성 데이터 생성기, 템플릿 끝-to-끝 점검 (e2e_templates.py)
├── samples/synthetic_week/     합성(가짜) 1주일 데이터
├── tests/                      자체 테스트
└── workspace/                  ← 내 데이터 (git 제외)
```

## 무엇이 검증됐나

| 항목 | 상태 |
|---|---|
| 설치 · 데모 · 분석 리포트 · 대시보드 (macOS) | 새로 clone 한 폴더에서 끝까지 통과 |
| 실제 화면 기록 → 분석 (macOS, screenpipe) | 가짜 작업 창만 허용 목록(`include_windows`)으로 15분 기록 → 실제 프레임 확인 → 분석까지 통과 |
| 내장 기록기 (macOS) | 앱 이름 + 시간 기록·분석 통과. **창 제목 수집은 실험적(experimental)** — 최신 macOS 에서는 권한이 있어도 비어 올 수 있음 |
| 템플릿 `script` · `browser-cdp` · `app-api` · `ai-step` (macOS) | 가짜 작업으로 test → 실제 실행 → 되돌리기 통과 (`python3 tools/e2e_templates.py`) |
| Windows 10/11 | 설치 스크립트·CLI·내장 기록기·작업 스케줄러 코드 포함, **미검증(untested)** |
| Linux | cron 예약, 내장 기록기(xdotool) 코드 포함, **미검증(untested)** |

`browser-cdp` 템플릿은 `pip install playwright` 가 필요합니다 (브라우저 다운로드 없이 내 Chrome 에 붙습니다).
`ai-step` 템플릿은 Claude Code(`claude -p`) 또는 Codex(`codex exec`)가 있으면 사용하고, 없으면 키워드 규칙으로 대신합니다.

[면책 조항](DISCLAIMER.md) · [MIT License](LICENSE)

---

## English

**work-autopilot watches how you work for a few days, finds what is worth automating, asks you until every step is clear,
then builds the automations — led by Claude Code or Codex.** One-command setup.

1. **Observe** — record 3–7 days, locally only, with [screenpipe](https://github.com/screenpipe/screenpipe) or the
   license-free **built-in recorder** (front app, window title, timestamp; optional front-window screenshots). Password managers,
   banking and private messaging apps are excluded by default; no audio, keystrokes or clipboard; no telemetry; raw
   recordings are deleted after analysis.
2. **Find** — a report of your tasks with time spent, frequency, and an *automatable / AI-assistable / keep human* score,
   plus the multi-app routines you repeat every day.
3. **Interview** — the agent keeps asking (what a step means, what "done" looks like, edge cases, approvals) until
   each automation is unambiguous.
4. **Build** — the right tool per task: scripts, app APIs, browser automation over the Chrome DevTools port or MCP,
   AI only where judgment is needed.
5. **Test** — dry-run first, always. Fix and repeat. Failures are logged; live runs can be undone.
6. **Run** — scheduled with launchd (macOS), Task Scheduler (Windows) or cron (Linux). A dashboard shows what is
   automated and the time saved (estimates, never "100%").

```bash
git clone https://github.com/codingintheusa0402/work-autopilot.git && cd work-autopilot && ./setup.sh --demo   # macOS/Linux
```
```powershell
git clone https://github.com/codingintheusa0402/work-autopilot.git; cd work-autopilot; powershell -ExecutionPolicy Bypass -File setup.ps1 -Demo
```

**Safety, enforced in code:** no passwords, card or ID numbers are stored or typed; sending, paying, buying, deleting,
submitting and uploading need your explicit per-automation approval at a real terminal (agents can't approve, and
changing the code voids the approval); dry-run by default; every run is logged and file changes are reversible;
all your data stays in the gitignored `workspace/` folder.

**screenpipe license in one line:** free for personal use and for a 7-day evaluation at a company; company use beyond
that needs screenpipe's paid plan. It is source-available (not open source) and not bundled here — see
[`docs/screenpipe.md`](docs/screenpipe.md). For work computers, pick the built-in recorder at setup
(`./setup.sh --recorder=builtin`): MIT like this repo, no network code, same privacy excludes.

The demo runs on a clearly **synthetic** sample week (`samples/synthetic_week/`) — no real person's screen.
Tested on macOS: setup, demo, a 15-minute real screen capture (fake task windows only) → analysis, the built-in
recorder, and all four automation templates (test → live → undo, `python3 tools/e2e_templates.py`).
Windows and Linux code paths are included but **untested**.

[Disclaimer](DISCLAIMER.md) · [MIT License](LICENSE)

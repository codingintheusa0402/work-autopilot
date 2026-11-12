#!/usr/bin/env bash
# work-autopilot — one-command setup for macOS / Linux.
#   ./setup.sh            check tools, create workspace/, run the self-test
#   ./setup.sh --demo     … then run the demo on synthetic data
#   ./setup.sh --recorder=builtin|screenpipe   pick the recorder without the prompt
# Installs nothing system-wide. screenpipe is fetched later by its own npm package, only
# when you run `./wa observe start`.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "1/4  Python"
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "python3 가 없습니다. macOS: 'xcode-select --install' 또는 https://www.python.org 에서 설치 후 다시 실행하세요."
  exit 1
fi
"$PY" -c 'import sys; assert sys.version_info >= (3, 9), "Python 3.9+ needed"' && "$PY" --version

say "2/4  workspace/ (개인 데이터 폴더 — git 에 절대 올라가지 않음)"
mkdir -p workspace
[ -f workspace/config.json ] || echo '{}' > workspace/config.json
chmod 700 workspace
echo "ok: $(pwd)/workspace"

say "기록기 선택 (관찰 단계에서 사용)"
REC=""
for a in "$@"; do case "$a" in --recorder=*) REC="${a#--recorder=}";; esac; done
if [ -z "$REC" ] && [ -t 0 ]; then
  cat <<'TXT'
  1) screenpipe — 화면 텍스트까지 기록, 분석이 더 정확. 소스 공개(오픈소스 아님) 라이선스:
     개인 비상업적 사용과 회사에서 7일 평가는 무료, 그 이상 회사 사용은 유료 플랜 필요.
  2) builtin   — 이 저장소의 내장 기록기. 앞 창의 앱 이름·창 제목·시간만 로컬 기록 (MIT, 추가 설치 없음).
     회사 컴퓨터에서 라이선스가 걱정되면 이쪽을 고르세요.
TXT
  read -r -p "  번호를 고르세요 [2]: " n
  case "$n" in 1) REC=screenpipe;; *) REC=builtin;; esac
fi
REC="${REC:-builtin}"
"$PY" - "$REC" <<'PY'
import json, sys, pathlib
p = pathlib.Path("workspace/config.json")
c = json.loads(p.read_text() or "{}")
c["recorder"] = sys.argv[1]
p.write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n")
print("  recorder =", sys.argv[1], "(바꾸려면 workspace/config.json)")
PY

say "3/4  환경 점검"
"$PY" wa.py doctor || true

say "4/4  자체 테스트"
"$PY" -m unittest discover -s tests -q

if [[ " $* " == *" --demo "* ]]; then
  say "데모 (합성 데이터)"
  "$PY" wa.py demo
fi

cat <<'MSG'

준비 완료.
  체험:   ./wa demo
  시작:   이 폴더에서 Claude Code(claude) 또는 Codex(codex)를 열고 "시작하자" 라고 말하세요.
          에이전트가 CLAUDE.md / AGENTS.md 의 순서대로 안내합니다.
MSG

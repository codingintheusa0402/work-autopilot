#!/usr/bin/env bash
# work-autopilot — one-command setup for macOS / Linux.
#   ./setup.sh            check tools, create workspace/, run the self-test
#   ./setup.sh --demo     … then run the demo on synthetic data
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

say "3/4  환경 점검"
"$PY" wa.py doctor || true

say "4/4  자체 테스트"
"$PY" -m unittest discover -s tests -q

if [ "${1:-}" = "--demo" ]; then
  say "데모 (합성 데이터)"
  "$PY" wa.py demo
fi

cat <<'MSG'

준비 완료.
  체험:   ./wa demo
  시작:   이 폴더에서 Claude Code(claude) 또는 Codex(codex)를 열고 "시작하자" 라고 말하세요.
          에이전트가 CLAUDE.md / AGENTS.md 의 순서대로 안내합니다.
MSG

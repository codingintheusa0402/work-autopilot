# work-autopilot — one-command setup for Windows 10/11 (PowerShell).
#   powershell -ExecutionPolicy Bypass -File setup.ps1          check tools, create workspace\, self-test
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -Demo    ... then run the demo on synthetic data
# Installs nothing system-wide. screenpipe is fetched later by its own npm package, only when you
# run `wa observe start`.
param([switch]$Demo, [ValidateSet("", "builtin", "screenpipe")][string]$Recorder = "")
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Say($m) { Write-Host "`n$m" -ForegroundColor Cyan }

Say "1/4  Python"
$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $py = @("py", "-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = @("python") }
if (-not $py) {
  Write-Host "Python 3.9+ 가 없습니다. 'winget install Python.Python.3.12' 또는 https://www.python.org 에서 설치 후 다시 실행하세요."
  exit 1
}
$pyExe = $py[0]; $pyArgs = @($py | Select-Object -Skip 1)
& $pyExe @pyArgs -c "import sys; assert sys.version_info >= (3, 9), 'Python 3.9+ needed'; print(sys.version.split()[0])"
if ($LASTEXITCODE -ne 0) { exit 1 }

Say "2/4  workspace\ (개인 데이터 폴더 — git 에 절대 올라가지 않음)"
New-Item -ItemType Directory -Force -Path "workspace" | Out-Null
if (-not (Test-Path "workspace\config.json")) { Set-Content -Path "workspace\config.json" -Value "{}" -Encoding UTF8 }
Write-Host "ok: $PSScriptRoot\workspace"

Say "기록기 선택 (관찰 단계에서 사용)"
if (-not $Recorder) {
  Write-Host "  1) screenpipe - 화면 텍스트까지 기록. 소스 공개 라이선스: 개인 비상업적 사용과 회사 7일 평가는 무료, 그 이상 회사 사용은 유료 플랜."
  Write-Host "  2) builtin    - 내장 기록기. 앞 창의 앱 이름/창 제목/시간만 로컬 기록 (MIT). Windows 에서는 아직 미검증(untested)."
  $n = Read-Host "  번호를 고르세요 [2]"
  $Recorder = if ($n -eq "1") { "screenpipe" } else { "builtin" }
}
& $pyExe @pyArgs -c "import json,pathlib,sys; p=pathlib.Path('workspace/config.json'); c=json.loads(p.read_text(encoding='utf-8-sig') or '{}'); c['recorder']=sys.argv[1]; p.write_text(json.dumps(c,indent=2),encoding='utf-8'); print('  recorder =', sys.argv[1])" $Recorder

Say "3/4  환경 점검"
$env:PYTHONIOENCODING = "utf-8"
& $pyExe @pyArgs wa.py doctor

Say "4/4  자체 테스트"
& $pyExe @pyArgs -m unittest discover -s tests -q
if ($LASTEXITCODE -ne 0) { exit 1 }

if ($Demo) {
  Say "데모 (합성 데이터)"
  & $pyExe @pyArgs wa.py demo
}

Write-Host @"

준비 완료.
  체험:   .\wa.cmd demo
  시작:   이 폴더에서 Claude Code(claude) 또는 Codex(codex)를 열고 "시작하자" 라고 말하세요.
"@

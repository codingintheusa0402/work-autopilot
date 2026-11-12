# work-autopilot — one-command setup for Windows 10/11 (PowerShell).
#   powershell -ExecutionPolicy Bypass -File setup.ps1          check tools, create workspace\, self-test
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -Demo    ... then run the demo on synthetic data
# Installs nothing system-wide. screenpipe is fetched later by its own npm package, only when you
# run `wa observe start`.
param([switch]$Demo)
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

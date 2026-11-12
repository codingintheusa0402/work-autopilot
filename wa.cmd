@echo off
rem work-autopilot CLI (Windows)
set PYTHONIOENCODING=utf-8
where py >nul 2>nul
if %errorlevel%==0 (py -3 "%~dp0wa.py" %*) else (python "%~dp0wa.py" %*)
exit /b %errorlevel%

@echo off
REM ── 수집 앱 실행 (HTML GUI) ──
cd /d "%~dp0"
echo 브라우저에서 http://localhost:5000 접속하세요.
start "" http://localhost:5000
.venv\Scripts\python.exe collect_app.py
pause

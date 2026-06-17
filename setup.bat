@echo off
REM ── 새 PC 최초 1회 설치 ──
REM Python 3.11 이 설치돼 있어야 함 (py -3.11)
cd /d "%~dp0"

echo [1/2] 가상환경 생성...
py -3.11 -m venv .venv 2>nul || python -m venv .venv

echo [2/2] 패키지 설치...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo 설치 완료. 실행하려면 run.bat 더블클릭.
pause

#!/bin/bash
# ── 수집 앱 실행 (HTML GUI, macOS) ──
# macOS는 RealSense 장치 claim에 root 권한이 필요(sudo)하고,
# 포트 5000은 AirPlay가 점유하므로 5050 사용.
cd "$(dirname "$0")"
export PORT="${PORT:-5050}"
echo "카메라 접근을 위해 관리자(sudo) 권한이 필요합니다 — 비밀번호를 입력하세요."
echo "브라우저에서 http://localhost:${PORT} 접속하세요. (준비까지 잠시 대기)"
( sleep 6; open "http://localhost:${PORT}" ) &
sudo PORT="${PORT}" .venv/bin/python -u collect_app.py

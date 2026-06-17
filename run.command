#!/bin/bash
# ── 수집 앱 실행 (HTML GUI, macOS) ──
# macOS는 RealSense 장치 claim에 root 권한이 필요(sudo)하고,
# 포트 5000은 AirPlay가 점유하므로 5050 사용.
cd "$(dirname "$0")"
export PORT="${PORT:-5050}"

# 기본은 고화질(FHD+720p). 맥에서 프레임이 멈추면:  LOWRES=1 ./run.command
if [ "${LOWRES:-0}" = "1" ]; then
  COLOR_W=640; COLOR_H=480; DEPTH_W=640; DEPTH_H=480
fi
COLOR_W="${COLOR_W:-1920}"; COLOR_H="${COLOR_H:-1080}"
DEPTH_W="${DEPTH_W:-1280}"; DEPTH_H="${DEPTH_H:-720}"

echo "카메라 접근을 위해 관리자(sudo) 권한이 필요합니다 — 비밀번호를 입력하세요."
echo "해상도: 컬러 ${COLOR_W}x${COLOR_H} / 깊이 ${DEPTH_W}x${DEPTH_H}  (낮추려면 LOWRES=1 ./run.command)"
echo "브라우저에서 http://localhost:${PORT} 접속하세요. (준비까지 잠시 대기)"
( sleep 6; open "http://localhost:${PORT}" ) &
sudo PORT="${PORT}" \
     COLOR_W="${COLOR_W}" COLOR_H="${COLOR_H}" DEPTH_W="${DEPTH_W}" DEPTH_H="${DEPTH_H}" \
     .venv/bin/python -u collect_app.py

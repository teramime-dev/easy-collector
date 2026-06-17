#!/bin/bash
# ── 새 Mac 자동 설치 (더블클릭하고 기다리면 끝) ──
# 유일한 사전 준비물: Homebrew (https://brew.sh) — 관리자 암호 필요해서 자동화 불가
set -u
cd "$(dirname "$0")"
ARCH="$(uname -m)"
echo "================================================"
echo "  립리딩 수집 앱 자동 설치 (macOS, $ARCH)"
echo "================================================"

# 0) Homebrew 확인 (유일한 수동 준비물)
if ! command -v brew >/dev/null 2>&1; then
  echo "[!] Homebrew가 필요합니다. 아래를 터미널에 붙여넣어 설치한 뒤 이 파일을 다시 실행하세요:"
  echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  exit 1
fi

# 1) Python 3.11
if ! command -v python3.11 >/dev/null 2>&1; then
  echo "[1/5] python@3.11 설치..."
  brew install python@3.11
fi
PY="$(command -v python3.11)"

# 2) 가상환경 + 기본 패키지 (카메라 외 — Mac에서 pip로 잘 설치됨)
echo "[2/5] 가상환경 + 기본 패키지 설치..."
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install mediapipe opencv-python numpy Flask pillow

# 3) pyrealsense2 — pip 우선 시도 (인텔 Mac 등에서 성공할 수 있음)
echo "[3/5] pyrealsense2 pip 설치 시도..."
if pip install pyrealsense2 2>/dev/null && .venv/bin/python -c "import pyrealsense2" 2>/dev/null; then
  echo "    ✅ pip 설치 성공 — 소스 빌드 불필요"
  echo ""
  echo "설치 완료! run.command 더블클릭으로 실행하세요."
  exit 0
fi
echo "    pip 휠 없음 → 소스 빌드로 자동 진행 (10~20분 소요)"

# 4) librealsense 소스 빌드 (Python 바인딩 포함)
echo "[4/5] 빌드 도구 설치..."
brew install cmake libusb pkg-config >/dev/null

REPO_TAG="${REALSENSE_TAG:-master}"
BUILD_ROOT=".build_librealsense"
rm -rf "$BUILD_ROOT"
echo "    librealsense 내려받기 ($REPO_TAG)..."
git clone --depth 1 --branch "$REPO_TAG" \
  https://github.com/IntelRealSense/librealsense.git "$BUILD_ROOT" 2>/dev/null \
  || git clone --depth 1 https://github.com/IntelRealSense/librealsense.git "$BUILD_ROOT"

PYBIN="$(pwd)/.venv/bin/python"
mkdir -p "$BUILD_ROOT/build"
( cd "$BUILD_ROOT/build" && \
  echo "    cmake 구성..." && \
  cmake .. \
    -DBUILD_PYTHON_BINDINGS=ON \
    -DPYTHON_EXECUTABLE="$PYBIN" \
    -DFORCE_RSUSB_BACKEND=ON \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_GRAPHICAL_EXAMPLES=OFF \
    -DBUILD_TOOLS=OFF \
    -DCMAKE_BUILD_TYPE=Release && \
  echo "    컴파일 (코어 $(sysctl -n hw.ncpu)개)..." && \
  make -j"$(sysctl -n hw.ncpu)" )

# 5) 빌드 산출물(pyrealsense2*.so / .py)을 venv 로 복사
echo "[5/5] pyrealsense2 모듈을 가상환경에 설치..."
SITE="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
find "$BUILD_ROOT/build" -name 'pyrealsense2*.so'  -exec cp {} "$SITE"/ \; 2>/dev/null
find "$BUILD_ROOT/build" -path '*pyrealsense2*' -name '*.py' -exec cp {} "$SITE"/ \; 2>/dev/null

echo ""
if .venv/bin/python -c "import pyrealsense2 as rs; print('pyrealsense2', rs.__version__)" 2>/dev/null; then
  echo "✅ 설치 완료! run.command 더블클릭으로 실행하세요."
  rm -rf "$BUILD_ROOT"
else
  echo "⚠️  빌드는 끝났지만 import 검증 실패."
  echo "    빌드 폴더($BUILD_ROOT)는 남겨뒀습니다. MIGRATION.md 의 macOS 수동 절차를 참고하세요."
fi

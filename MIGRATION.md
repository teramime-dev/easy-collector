# 다른 PC로 이식하기

> **OS별 실행 파일**
> - Windows: `setup.bat` → `run.bat`
> - macOS: `setup.command` → `run.command`
>
> 공통 규칙: **`.venv` 폴더는 복사하지 말고** 새 PC에서 다시 생성한다.
> macOS 카메라(`pyrealsense2`)는 주의가 필요하다 — 아래 **A. macOS** 참고.

---

## A. macOS (특히 애플 실리콘)

### ⚠️ 카메라 라이브러리 주의 (먼저 읽기)
`pyrealsense2`는 Windows/Linux는 `pip` 한 줄로 설치되지만, **macOS는 공식 pip 휠이 없을 때가 많다**(특히 M1~M4 arm64).
- 앱의 **나머지 기능(영상 UI, MediaPipe, 저장)** 은 Mac에서 정상 동작.
- **카메라 캡처만** 추가 작업이 필요할 수 있다.
- 캡처가 핵심이면 **실제 촬영은 Windows PC**에서 하고, Mac은 분석/확인용으로 쓰는 것도 방법.

### 설치 절차 (거의 전자동 — 더블클릭하고 기다리면 끝)
1. **Homebrew** 설치 (유일한 수동 준비물, 없으면): https://brew.sh
   - 관리자 암호가 필요해 스크립트가 대신 못 함. 이것만 미리 해두면 나머지는 자동.
2. `.venv` 뺀 폴더를 Mac으로 복사
3. 터미널에서:
   ```bash
   cd 옮긴_폴더
   chmod +x setup.command run.command   # 더블클릭 가능하게 (최초 1회)
   ./setup.command
   ```

`setup.command`가 자동으로 하는 일:
- python@3.11 설치 → 가상환경 생성 → 기본 패키지(mediapipe·opencv·flask 등) 설치
- `pyrealsense2`를 **pip로 먼저 시도**, 실패하면 **librealsense를 소스 자동 빌드**
  (cmake/libusb 설치 → 클론 → 컴파일 → 빌드된 모듈을 venv로 복사 → import 검증)
- 컴파일 때문에 처음 한 번은 **10~20분** 걸린다. 그 뒤엔 `run.command`로 바로 실행.

> 특정 librealsense 버전으로 빌드하려면: `REALSENSE_TAG=v2.55.1 ./setup.command`

### 자동 빌드가 실패하면
- 빌드 폴더 `.build_librealsense/`가 남는다. macOS 버전에 따라 cmake 옵션 조정이 필요할 수 있다.
- 카메라 권한: 시스템 설정 → 개인정보 보호 및 보안 → 카메라 에서 터미널 허용이 필요할 수 있다.
- 그래도 안 되면: **실제 촬영은 Windows PC**에서 하고 Mac은 분석용으로 쓰는 것을 권장.

### 실행
```bash
./run.command          # 또는 Finder에서 더블클릭
```
→ 브라우저에서 http://localhost:5000

---

## B. Windows

## 1. 새 PC 준비물
- **Python 3.11** (https://www.python.org/downloads/ — 설치 시 "Add to PATH" 체크)
- **Intel RealSense D435i** 카메라 + USB 3.0 케이블
- (대개 불필요) 카메라가 인식 안 되면 Intel RealSense SDK 2.0 설치

## 2. 복사할 것 / 복사하지 말 것

### ✅ 복사 (폴더 통째로, 단 `.venv` 제외)
```
collect_app.py
collect_realsense.py
face_landmarker_v2_with_blendshapes.task   ← 필수! (3.6MB 모델)
requirements.txt
setup.bat   run.bat
templates/   static/
data_d435i/   data_v2/   ← 기존 수집 데이터도 옮기려면 함께
```

### ❌ 복사 금지
```
.venv/   ← 경로가 박혀 있어 다른 PC에서 깨짐. 새로 만든다.
```
> USB/압축으로 옮길 때 `.venv`만 빼면 됩니다. (있어도 setup.bat이 무시하고 새로 만드므로 큰 문제는 아니지만, 용량만 차지)

## 3. 새 PC에서 설치 (최초 1회)
폴더를 옮긴 뒤 **`setup.bat` 더블클릭**.
- 가상환경 생성 + 패키지 자동 설치 (인터넷 필요, 5~10분)

수동으로 하려면:
```
cd 옮긴_폴더
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## 4. 카메라 인식 확인
```
.venv\Scripts\python -c "import pyrealsense2 as rs; print(len(rs.context().query_devices()), 'device(s)')"
```
→ `1 device(s)` 나오면 정상. `0`이면 USB 3.0 포트/케이블 교체.

## 5. 실행
- **`run.bat` 더블클릭** → 브라우저에서 http://localhost:5000 자동 열림
- 화자 ID 입력 → 화자 설정 → 녹화

## 요약
1. `.venv` 빼고 폴더 통째로 복사
2. `setup.bat` (최초 1회)
3. `run.bat` (실행)

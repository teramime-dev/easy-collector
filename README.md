# easy-collector — RealSense 립리딩 데이터 수집기

Intel RealSense **D435i** 카메라로 발화 시 입술 랜드마크(76점)를 **3D로 수집**하는 도구입니다.
브라우저에서 라이브 영상을 보며 버튼/단축키로 녹화합니다. (Flask 웹앱 + MediaPipe + RealSense)

---

## 무엇이 저장되나

한 발화 = **2초 / 60프레임 고정 길이**. 단어를 말할 때마다 take 하나가 저장됩니다.

```
data_v2/{화자ID}/{단어}/take_NN_mp.npy      (60, 76, 3)  MediaPipe 추정 좌표 (화면 픽셀 + z)
                       take_NN_depth.npy   (60, 76, 3)  RealSense 실측 3D (mm)
```

수집 단어: 입체조(기준동작) + 명령어 8개(선택·확인·뒤로·취소·다음·확대·축소·처음으로)

---

## 준비물

- Intel **RealSense D435i** + **USB 3.0** 케이블 (⚠️ 아래 "함정" 참고)
- macOS(Apple Silicon/Intel) 또는 Windows
- macOS는 **Homebrew** 필요: https://brew.sh

---

## 설치 & 실행

### macOS
```bash
git clone https://github.com/teramime-dev/easy-collector.git
cd easy-collector
chmod +x setup.command run.command
./setup.command     # 가상환경 + pyrealsense2 빌드 (Apple Silicon은 처음 10~20분)
./run.command       # 실행 → 관리자(sudo) 비밀번호 입력
```
브라우저에서 자동으로 **http://localhost:5050** 이 열립니다.
콘솔에 `같은 네트워크: http://192.168.x.x:5050` 도 표시되며, **같은 와이파이의 다른 기기**에서 이 주소로 접속하면 그 화면에서도 녹화할 수 있습니다. (카메라는 서버 PC 한 대만 있으면 됨)

### Windows
```
setup.bat   더블클릭   (pyrealsense2 자동 설치, 5~10분)
run.bat     더블클릭   → http://localhost:5000
```

---

## 사용 순서

1. 브라우저 접속 후 **화자 ID 입력 → "화자 설정"**
   - 같은 PC에서 사람이 바뀌면 화자 ID만 바꾸면 됩니다. (`data_v2/{이름}/` 로 자동 분리)
2. 단어 선택 (버튼 또는 단축키)
3. **녹화** 누르면 2초(60프레임) 자동 캡처 후 저장
4. 단어/화자 바꿔가며 반복

**촬영 팁:** 얼굴을 카메라에서 **40~50cm** 정도 띄우면 입술 외곽 점의 깊이(depth) 누락이 줄어 품질이 좋아집니다.

---

## ⚠️ 함정 3가지 (macOS, 꼭 읽기)

이걸 모르면 "카메라가 안 잡힌다"로 한참 헤맵니다. 전부 해결되도록 스크립트에 반영돼 있지만, 증상을 알아두세요.

| 증상 | 원인 | 해결 |
|---|---|---|
| `failed to set power state` / 카메라 안 잡힘 | macOS는 RealSense 장치 점유에 **root 권한** 필요 | **반드시 `sudo`로 실행** — `run.command`가 이미 sudo로 돎 |
| 브라우저가 `localhost:5000` 안 열림 | macOS **AirPlay 수신**이 5000 포트 점유 | **5050 포트 사용** (이미 반영). 바꾸려면 `PORT=5060 ./run.command` |
| 감지(1대)는 되는데 스트림이 `No device connected` | **USB 2.0** 케이블/허브로 연결됨 (대역폭·전원 부족) | **USB 3.0** 케이블 + **맥북 본체 포트 직결** (USB 2.0 허브·도크 ❌) |

> USB 연결 속도 확인: 아래 값이 **3** 이어야 USB 3.0 입니다.
> ```bash
> ioreg -p IOUSB -w0 -l | grep -i "RealSense" -A4 | grep "Device Speed"
> ```

---

## 다른 PC로 옮길 때

- **`.venv`, `.build_librealsense`, `data_*` 폴더는 복사하지 마세요.**
  - `.venv`는 파이썬 경로가 박혀 있어 다른 PC에서 깨집니다 → `setup` 으로 새로 생성.
  - 데이터는 수집 결과물이라 실행에 불필요합니다.
- `git clone` 후 `setup` 한 번 돌리는 것이 가장 깔끔합니다.

자세한 이식 절차는 [MIGRATION.md](MIGRATION.md) 참고.

---

## 구조

| 파일 | 역할 |
|---|---|
| `collect_app.py` | **메인 앱** — Flask 서버 + RealSense 캡처 + MediaPipe |
| `collect_realsense.py` | 옛 CLI 버전 (현재 미사용) |
| `face_landmarker_v2_with_blendshapes.task` | MediaPipe 얼굴 모델 (필수) |
| `templates/`, `static/` | 웹 UI |
| `setup.command` / `setup.bat` | 환경 자동 설치 (mac / Windows) |
| `run.command` / `run.bat` | 실행 |

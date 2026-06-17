#!/usr/bin/env python3
"""RealSense D435i 립리딩 수집 — HTML GUI 버전.

브라우저에서 라이브 영상을 보며 버튼/단축키로 녹화한다.
한글 라벨이 브라우저에서 렌더링되므로 OpenCV 한글 깨짐 문제가 없다.

실행:
  .venv\\Scripts\\python.exe collect_app.py
  → 브라우저에서 http://localhost:5000 접속

저장 구조 (기존 data_d435i 와 분리된 새 데이터셋):
  data_v2/{화자ID}/{단어}/take_NN_mp.npy     (T,76,3) MediaPipe 추정 좌표
                          take_NN_depth.npy  (T,76,3) RealSense 실측 3D(mm)
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request

try:
    import pyrealsense2 as rs
except ImportError:
    raise SystemExit("pip install pyrealsense2 필요 (로컬 PC)")

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# ── 설정 ──
BASE_DIR = Path(__file__).resolve().parent
FACE_MODEL = str(BASE_DIR / "face_landmarker_v2_with_blendshapes.task")
# 해상도는 환경변수로 조절 (기본 = 고화질: 컬러 FHD + 깊이 720p).
# macOS는 USB 대역폭이 빠듯해 프레임이 멈추면 LOWRES=1 로 640x480 사용:
#   LOWRES=1 ./run.command   (또는 COLOR_W/COLOR_H/DEPTH_W/DEPTH_H 개별 지정)
COLOR_W = int(os.environ.get("COLOR_W", "1920"))
COLOR_H = int(os.environ.get("COLOR_H", "1080"))
DEPTH_W = int(os.environ.get("DEPTH_W", "1280"))
DEPTH_H = int(os.environ.get("DEPTH_H", "720"))
FPS = int(os.environ.get("FPS", "30"))
# 랜드마크 정규화 좌표 → 픽셀 변환 및 화면 크기 기준 (= 컬러 해상도)
W, H = COLOR_W, COLOR_H
REC_SECONDS = 2.0
REC_FRAMES = int(FPS * REC_SECONDS)  # 한 발화 고정 길이 (= 60프레임)
DEFAULT_DATASET = "data_v2"          # 기존 data_d435i 와 분리

# ── 76점 인덱스 (collect_realsense.py 와 동일) ──
ALL_LANDMARK_INDICES = [
    0, 1, 2, 4, 5, 6, 13, 14, 17, 19, 37, 39, 40, 48, 58, 61,
    78, 80, 81, 82, 84, 87, 88, 91, 93, 94, 95, 98, 115, 132,
    136, 146, 148, 149, 150, 152, 168, 172, 176, 178, 181, 185,
    191, 195, 197, 234, 267, 269, 270, 275, 288, 291, 308, 310,
    311, 312, 314, 317, 318, 321, 323, 324, 327, 344, 361, 365,
    375, 377, 378, 379, 397, 400, 402, 405, 409, 415,
]
OUTER_LIP_LOCAL = [15, 41, 12, 11, 10, 0, 46, 47, 48, 74, 51, 66, 59, 73, 56, 8, 20, 40, 23, 31]

# ── 수집 단어: 기준동작(입체조) + 명령어 11개 ──
WORDS = [
    {"name": "입체조", "target": 5, "kind": "calib"},
    {"name": "선택", "target": 8, "kind": "cmd"},
    {"name": "확인", "target": 8, "kind": "cmd"},
    {"name": "뒤로", "target": 8, "kind": "cmd"},
    {"name": "취소", "target": 8, "kind": "cmd"},
    {"name": "다음", "target": 8, "kind": "cmd"},
    {"name": "확대", "target": 8, "kind": "cmd"},
    {"name": "축소", "target": 8, "kind": "cmd"},
    {"name": "처음으로", "target": 8, "kind": "cmd"},
]


def make_landmarker():
    return mp_vision.FaceLandmarker.create_from_options(
        mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=FACE_MODEL),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    )


class Collector:
    """RealSense 캡처 스레드 + 녹화 상태를 관리한다."""

    def __init__(self):
        self.lock = threading.Lock()
        self.speaker = ""
        self.dataset = DEFAULT_DATASET
        self.words = [dict(w) for w in WORDS]
        self.wi = 0
        self.recording = False
        self.buf_mp: list[np.ndarray] = []
        self.buf_depth: list[np.ndarray] = []
        self.buf_frames: list[np.ndarray] = []   # 원본 컬러 프레임 (mp4 저장용)
        self.save_video = os.environ.get("SAVE_VIDEO", "1") == "1"
        self.takes = {w["name"]: 0 for w in WORDS}
        self.latest_jpeg: bytes | None = None
        self.status = "카메라 시작 중..."
        self.has_face = False
        self.depth_scale = 1.0
        self.distance_mm = 0.0          # 코끝~카메라 거리(실시간 표시용)
        self.intrinsics = None          # 카메라 내부파라미터(메타데이터 저장용)
        self.frame_idx = 0
        self.running = True
        self.camera_ok = False
        self._landmarker = None
        # 깊이 후처리 필터 (노이즈·구멍 감소) — temporal은 상태를 유지하므로 1회 생성
        self._spatial = rs.spatial_filter()
        self._temporal = rs.temporal_filter()
        self._hole = rs.hole_filling_filter()

    # ── 단어 폴더 정보 ──
    def _cur_word(self) -> str:
        return self.words[self.wi]["name"]

    # ── 단어별 수행 안내문 (UI 표시용) ──
    @staticmethod
    def _guide(w: dict) -> str:
        if w["kind"] == "calib":
            return ("입 운동(소리 없이 입모양만): 크게 '아' 벌리기 → 양옆으로 활짝 '이' "
                    "→ 앞으로 모아 '우' → 다물기. 2초간 과장되게 천천히 한 번.")
        return f"입모양으로 또박또박 «{w['name']}» 라고 말하세요. (2초)"

    def _refresh_takes_locked(self):
        for w in self.words:
            d = Path(self.dataset) / self.speaker / w["name"]
            self.takes[w["name"]] = (
                len(list(d.glob("take_*_mp.npy"))) if d.exists() else 0
            )

    # ── 외부(API)에서 호출 ──
    def set_speaker(self, speaker: str, dataset: str):
        with self.lock:
            self.speaker = (speaker or "").strip()
            self.dataset = (dataset or "").strip() or DEFAULT_DATASET
            self.recording = False
            self.buf_mp, self.buf_depth, self.buf_frames = [], [], []
            if self.speaker:
                self._refresh_takes_locked()
                self.status = f"{self.speaker} 준비 완료 — 녹화 가능"
            else:
                self.status = "화자 ID를 입력하세요"

    def start_record(self) -> bool:
        with self.lock:
            if not self.speaker:
                self.status = "먼저 화자 ID를 입력하세요"
                return False
            if not self.recording:
                self.recording = True
                self.buf_mp, self.buf_depth, self.buf_frames = [], [], []
                self.status = "녹화 중..."
            return True

    def cancel_record(self):
        with self.lock:
            self.recording = False
            self.buf_mp, self.buf_depth, self.buf_frames = [], [], []
            self.status = "녹화 취소"

    def next_word(self):
        with self.lock:
            self.recording = False
            self.buf_mp, self.buf_depth, self.buf_frames = [], [], []
            self.wi = (self.wi + 1) % len(self.words)

    def prev_word(self):
        with self.lock:
            self.recording = False
            self.buf_mp, self.buf_depth, self.buf_frames = [], [], []
            self.wi = (self.wi - 1) % len(self.words)

    def select_word(self, index: int):
        with self.lock:
            if 0 <= index < len(self.words):
                self.recording = False
                self.buf_mp, self.buf_depth, self.buf_frames = [], [], []
                self.wi = index

    def reset_take(self):
        with self.lock:
            self.takes[self._cur_word()] = 0
            self.status = f"{self._cur_word()} take 리셋 (파일은 보존됨)"

    # ── 저장 (lock 보유 상태에서 호출) ──
    def _save_take_locked(self):
        word = self._cur_word()
        n = self.takes[word]
        wdir = Path(self.dataset) / self.speaker / word
        wdir.mkdir(parents=True, exist_ok=True)
        np.save(wdir / f"take_{n:02d}_mp.npy", np.array(self.buf_mp, np.float32))
        np.save(wdir / f"take_{n:02d}_depth.npy", np.array(self.buf_depth, np.float32))
        # 원본 컬러 영상(mp4) 저장
        video_name = None
        if self.save_video and self.buf_frames:
            h, w = self.buf_frames[0].shape[:2]
            video_name = f"take_{n:02d}_color.mp4"
            vw = cv2.VideoWriter(str(wdir / video_name),
                                 cv2.VideoWriter_fourcc(*"mp4v"), FPS, (w, h))
            for fr in self.buf_frames:
                vw.write(fr)
            vw.release()
        # 재처리·검증용 메타데이터
        meta = {
            "speaker": self.speaker, "word": word, "take": n,
            "frames": len(self.buf_mp),
            "color_res": [COLOR_W, COLOR_H], "depth_res": [DEPTH_W, DEPTH_H],
            "fps": FPS, "rec_seconds": REC_SECONDS,
            "depth_scale": self.depth_scale,
            "video": video_name,
            "landmark_indices": ALL_LANDMARK_INDICES,
            "intrinsics": self.intrinsics,
            "saved_at": time.time(),
        }
        (wdir / f"take_{n:02d}_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2))
        self.takes[word] = n + 1
        self.recording = False
        self.buf_mp, self.buf_depth, self.buf_frames = [], [], []
        self.status = f"저장 완료: {word} take {n}"

    # ── 상태 스냅샷 (프론트로 전송) ──
    def state(self) -> dict:
        with self.lock:
            return {
                "speaker": self.speaker,
                "dataset": self.dataset,
                "wi": self.wi,
                "word": self._cur_word(),
                "kind": self.words[self.wi]["kind"],
                "target": self.words[self.wi]["target"],
                "guide": self._guide(self.words[self.wi]),
                "recording": self.recording,
                "progress": len(self.buf_mp),
                "rec_frames": REC_FRAMES,
                "has_face": self.has_face,
                "distance_mm": round(self.distance_mm),
                "camera_ok": self.camera_ok,
                "status": self.status,
                "total": sum(self.takes.values()),
                "words": [
                    {
                        "name": w["name"],
                        "target": w["target"],
                        "kind": w["kind"],
                        "count": self.takes[w["name"]],
                    }
                    for w in self.words
                ],
            }

    # ── 카메라 파이프라인 시작 (재시작에도 사용) ──
    def _start_pipe(self):
        pipe = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.color, COLOR_W, COLOR_H, rs.format.bgr8, FPS)
        cfg.enable_stream(rs.stream.depth, DEPTH_W, DEPTH_H, rs.format.z16, FPS)
        profile = pipe.start(cfg)
        dev = profile.get_device()
        depth_sensor = dev.first_depth_sensor()
        self.depth_scale = depth_sensor.get_depth_scale()

        # 센서 옵션 설정은 macOS RSUSB 백엔드에서 스트림을 멈추게 할 수 있어 기본 OFF.
        # 안정적인 환경(주로 Windows)에서 화질을 높이려면 SENSOR_TUNE=1 로 켠다.
        if os.environ.get("SENSOR_TUNE", "0") == "1":
            try:  # 깊이 프리셋 → High Accuracy (측정 노이즈↓)
                if depth_sensor.supports(rs.option.visual_preset):
                    depth_sensor.set_option(
                        rs.option.visual_preset,
                        float(rs.rs400_visual_preset.high_accuracy))
            except Exception:
                pass
            try:  # 노출 '프레임레이트 우선' → 어두워도 30fps 유지
                color_sensor = dev.first_color_sensor()
                if color_sensor.supports(rs.option.auto_exposure_priority):
                    color_sensor.set_option(rs.option.auto_exposure_priority, 0)
            except Exception:
                pass

        # 카메라 내부파라미터 저장 (정렬 후 깊이는 컬러 intrinsics를 따름)
        try:
            cp = profile.get_stream(rs.stream.color).as_video_stream_profile()
            it = cp.get_intrinsics()
            self.intrinsics = {
                "width": it.width, "height": it.height,
                "fx": it.fx, "fy": it.fy, "ppx": it.ppx, "ppy": it.ppy,
                "model": str(it.model), "coeffs": list(it.coeffs),
            }
        except Exception:
            pass
        return pipe

    # ── 캡처 스레드 본체 ──
    def run(self):
        # 모델을 먼저 로드해 start~첫 프레임 사이 공백을 없앤다.
        self._landmarker = make_landmarker()
        align = rs.align(rs.stream.color)
        # 카메라가 안정적으로 잡힐 때까지 재시도 (USB 일시 끊김에도 스레드가 죽지 않음)
        pipe = None
        while self.running and pipe is None:
            try:
                pipe = self._start_pipe()
            except Exception as e:
                with self.lock:
                    self.camera_ok = False
                    self.status = f"카메라 연결 대기 중... ({str(e)[:45]})"
                time.sleep(2.0)
        if pipe is None:
            return
        with self.lock:
            self.camera_ok = True
            self.status = "준비 완료 — 화자 ID 입력 후 녹화하세요"

        fails = 0
        try:
            while self.running:
                # 프레임 대기 — 타임아웃/끊김에도 스레드를 죽이지 않고 재시도·재연결
                try:
                    frames = align.process(pipe.wait_for_frames(10000))
                except RuntimeError:
                    fails += 1
                    with self.lock:
                        self.has_face = False
                        self.status = f"프레임 대기 중... (재시도 {fails})"
                    if fails >= 3:
                        try:
                            pipe.stop()
                        except Exception:
                            pass
                        time.sleep(1.0)
                        try:
                            pipe = self._start_pipe()
                            fails = 0
                            with self.lock:
                                self.status = "카메라 재연결됨"
                        except Exception:
                            with self.lock:
                                self.status = "카메라 연결 끊김 — USB 3.0 연결 확인"
                            time.sleep(1.0)
                    continue
                fails = 0
                cframe = frames.get_color_frame()
                dframe = frames.get_depth_frame()
                if not cframe or not dframe:
                    continue
                # 깊이 후처리 (노이즈·구멍 감소)
                dframe = self._spatial.process(dframe)
                dframe = self._temporal.process(dframe)
                dframe = self._hole.process(dframe).as_depth_frame()
                color = np.asanyarray(cframe.get_data())
                depth = np.asanyarray(dframe.get_data())

                rgb = cv2.cvtColor(color, cv2.COLOR_BGR2RGB)
                ts = int(self.frame_idx * 1000 / FPS) + 1
                res = self._landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                self.frame_idx += 1

                disp = color.copy()   # 그림은 복사본에 → color는 깨끗하게 보존(영상 저장용)
                has_face = bool(res.face_landmarks)
                pts_mp = pts_depth = None

                if has_face:
                    face = res.face_landmarks[0]
                    depth_intrin = dframe.profile.as_video_stream_profile().intrinsics
                    mp_list, dp_list = [], []
                    for i in ALL_LANDMARK_INDICES:
                        x = face[i].x * W
                        y = face[i].y * H
                        z_mp = face[i].z * W
                        mp_list.append([x, y, z_mp])
                        xi = int(np.clip(x, 0, W - 1))
                        yi = int(np.clip(y, 0, H - 1))
                        depth_m = float(depth[yi, xi]) * self.depth_scale
                        X, Y, Z = rs.rs2_deproject_pixel_to_point(
                            depth_intrin, [xi, yi], depth_m)
                        dp_list.append([X * 1000.0, Y * 1000.0, Z * 1000.0])
                    pts_mp = np.array(mp_list, np.float32)
                    pts_depth = np.array(dp_list, np.float32)
                    for li in OUTER_LIP_LOCAL:
                        cv2.circle(disp, (int(pts_mp[li, 0]), int(pts_mp[li, 1])),
                                   2, (0, 255, 0), -1)

                # 카메라~얼굴 거리 (유효 깊이 점들의 중앙값, mm)
                dist_mm = 0.0
                if pts_depth is not None:
                    zz = pts_depth[:, 2]
                    valid = zz[zz > 0]
                    if valid.size:
                        dist_mm = float(np.median(valid))

                with self.lock:
                    self.has_face = has_face
                    self.distance_mm = dist_mm
                    if self.recording and pts_mp is not None:
                        self.buf_mp.append(pts_mp)
                        self.buf_depth.append(pts_depth)
                        if self.save_video:
                            self.buf_frames.append(color.copy())
                        if len(self.buf_mp) >= REC_FRAMES:
                            self._save_take_locked()
                    rec = self.recording

                if rec:
                    cv2.rectangle(disp, (0, 0), (W - 1, H - 1), (0, 0, 255), 10)

                ok, jpg = cv2.imencode(".jpg", disp,
                                       [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    with self.lock:
                        self.latest_jpeg = jpg.tobytes()
        finally:
            if pipe is not None:
                try:
                    pipe.stop()
                except Exception:
                    pass
            if self._landmarker:
                self._landmarker.close()


app = Flask(__name__)
collector = Collector()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    def gen():
        while True:
            with collector.lock:
                frame = collector.latest_jpeg
            if frame is None:
                time.sleep(0.03)
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                   + frame + b"\r\n")
            time.sleep(1.0 / FPS)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/snapshot")
def snapshot():
    # 최신 프레임 1장 (브라우저가 폴링) — MJPEG보다 안정적
    with collector.lock:
        frame = collector.latest_jpeg
    if frame is None:
        return ("", 503)
    resp = Response(frame, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/state")
def api_state():
    return jsonify(collector.state())


@app.route("/api/speaker", methods=["POST"])
def api_speaker():
    d = request.get_json(force=True)
    collector.set_speaker(d.get("speaker", ""), d.get("dataset", DEFAULT_DATASET))
    return jsonify(collector.state())


@app.route("/api/record", methods=["POST"])
def api_record():
    collector.start_record()
    return jsonify(collector.state())


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    collector.cancel_record()
    return jsonify(collector.state())


@app.route("/api/next", methods=["POST"])
def api_next():
    collector.next_word()
    return jsonify(collector.state())


@app.route("/api/prev", methods=["POST"])
def api_prev():
    collector.prev_word()
    return jsonify(collector.state())


@app.route("/api/select", methods=["POST"])
def api_select():
    d = request.get_json(force=True)
    collector.select_word(int(d.get("index", 0)))
    return jsonify(collector.state())


@app.route("/api/reset_take", methods=["POST"])
def api_reset_take():
    collector.reset_take()
    return jsonify(collector.state())


def _lan_ip() -> str:
    """이 PC의 LAN IP를 추정 (다른 기기가 접속할 주소)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # 실제로 패킷을 보내진 않음
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    t = threading.Thread(target=collector.run, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", "5000"))
    ip = _lan_ip()
    print("=" * 52)
    print("  립리딩 수집 서버 시작")
    print(f"  이 PC:        http://localhost:{port}")
    print(f"  같은 네트워크: http://{ip}:{port}")
    print("  (다른 기기는 위 '같은 네트워크' 주소로 접속)")
    print("=" * 52)
    # host=0.0.0.0 → 같은 LAN의 다른 기기에서도 접속 가능
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()

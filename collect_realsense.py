#!/usr/bin/env python3
"""RealSense D435i 단어 발화 수집 — 추정z(MediaPipe) vs 실측z(Depth) 동시 저장.

로컬 PC(카메라 연결된 곳)에서 실행. 서버 아님.

설치:
  pip install pyrealsense2 mediapipe opencv-python numpy

동작:
  1. RGB+Depth 동시 캡처 (D435i, depth는 color에 정렬 align)
  2. MediaPipe로 RGB에서 76점 (x,y) 검출
  3. 각 점을 두 좌표계로 저장 (x,y,z 전부 다른 값):
       mp    = MediaPipe 자체 추정값 (x,y = 픽셀, z = 추정 깊이)
       depth = RealSense 실제 3D 좌표 (실측 depth를 intrinsics로 역투영, mm)
               * 점의 픽셀 위치는 MediaPipe가 제공 → 그 픽셀을 카메라 광학
                 기하로 역투영해 RealSense 고유의 (X,Y,Z) mm 로 변환
  4. 한 발화 = (T,76,3) 두 버전 저장
     → MediaPipe 추정 좌표 vs RealSense 실측 3D 좌표 비교 데이터

조작 (OpenCV 창):
  스페이스 = 녹화 시작 (2초 후 자동 정지·저장. 채우기 전 다시 누르면 취소)
  n        = 다음 단어
  p        = 이전 단어
  r        = 현재 단어 take 카운트 리셋
  q        = 종료

저장 구조:
  data_d435i/{화자ID}/{단어}/take_{NN}_mp.npy     (T,76,3)  추정z
                            take_{NN}_depth.npy  (T,76,3)  실측z
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import pyrealsense2 as rs
except ImportError:
    raise SystemExit("pip install pyrealsense2 필요 (로컬 PC)")

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# ── 우리 모델이 쓰는 76점 인덱스 (demo_lipreading.py 와 동일) ──
ALL_LANDMARK_INDICES = [
    0, 1, 2, 4, 5, 6, 13, 14, 17, 19, 37, 39, 40, 48, 58, 61,
    78, 80, 81, 82, 84, 87, 88, 91, 93, 94, 95, 98, 115, 132,
    136, 146, 148, 149, 150, 152, 168, 172, 176, 178, 181, 185,
    191, 195, 197, 234, 267, 269, 270, 275, 288, 291, 308, 310,
    311, 312, 314, 317, 318, 321, 323, 324, 327, 344, 361, 365,
    375, 377, 378, 379, 397, 400, 402, 405, 409, 415,
]
OUTER_LIP_LOCAL = [15, 41, 12, 11, 10, 0, 46, 47, 48, 74, 51, 66, 59, 73, 56, 8, 20, 40, 23, 31]

DEFAULT_WORDS = ["결제", "취소", "확인", "주문", "카드결제", "현금결제", "앞으로", "뒤로"]
FACE_MODEL = "face_landmarker_v2_with_blendshapes.task"  # 로컬에 같이 두기
W, H, FPS = 640, 480, 30
REC_SECONDS = 2.0
REC_FRAMES = int(FPS * REC_SECONDS)  # 한 발화 고정 길이 (= 60프레임 = 2초)

# ── 한글 표시용 폰트 (OpenCV putText는 한글 못 그려서 PIL로 그림) ──
KR_FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
_FONT_BIG = ImageFont.truetype(KR_FONT_PATH, 56)    # 말할 단어
_FONT_MID = ImageFont.truetype(KR_FONT_PATH, 26)    # 보조 정보


def draw_overlay(img, cur_word, wi, n_words, take_n, status, recording):
    """OpenCV(BGR) 이미지에 한글 안내 텍스트를 PIL로 그려서 반환."""
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    red, white, yellow = (255, 60, 60), (255, 255, 255), (255, 220, 0)
    main = red if recording else yellow
    # 말할 단어 (크게)
    d.text((20, 15), f"▶ {cur_word}", font=_FONT_BIG, fill=main)
    # 보조: 진행/테이크/상태
    d.text((22, 85), f"[{wi+1}/{n_words}]  take {take_n}", font=_FONT_MID, fill=white)
    d.text((22, 120), status, font=_FONT_MID, fill=(red if recording else white))
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker", required=True, help="화자 ID (예: spk01)")
    ap.add_argument("--words", nargs="+", default=DEFAULT_WORDS)
    ap.add_argument("--out", default="data_d435i")
    args = ap.parse_args()

    out_root = Path(args.out) / args.speaker
    out_root.mkdir(parents=True, exist_ok=True)

    # RealSense 파이프라인 (RGB + Depth, depth를 color에 정렬)
    pipe = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.color, W, H, rs.format.bgr8, FPS)
    cfg.enable_stream(rs.stream.depth, W, H, rs.format.z16, FPS)
    profile = pipe.start(cfg)
    align = rs.align(rs.stream.color)
    depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()  # → meters
    print(f"depth_scale={depth_scale} (z16 → meter), mm = value*{depth_scale*1000:.4f}")

    landmarker = make_landmarker()
    words = args.words
    wi = 0
    take = {w: len(list(out_root.joinpath(w).glob("take_*_mp.npy"))) if out_root.joinpath(w).exists() else 0
            for w in words}

    recording = False
    buf_mp, buf_depth = [], []
    frame_idx = 0
    t0 = time.time()

    print(f"스페이스=녹화시작({REC_SECONDS}초자동)  n=다음단어  p=이전단어  r=리셋  q=종료")
    while True:
        frames = align.process(pipe.wait_for_frames())
        cframe = frames.get_color_frame()
        dframe = frames.get_depth_frame()
        if not cframe or not dframe:
            continue
        color = np.asanyarray(cframe.get_data())
        depth = np.asanyarray(dframe.get_data())  # (H,W) uint16, z16

        rgb = cv2.cvtColor(color, cv2.COLOR_BGR2RGB)
        ts = int(frame_idx * 1000 / FPS) + 1
        res = landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

        disp = color.copy()
        cur_word = words[wi]
        has_face = bool(res.face_landmarks)

        if has_face:
            face = res.face_landmarks[0]
            # 정렬된 depth 프레임의 intrinsics (= color 카메라 기준)
            # → 픽셀을 RealSense 고유의 실제 3D 좌표로 역투영하는 데 사용
            depth_intrin = dframe.profile.as_video_stream_profile().intrinsics
            pts_mp, pts_depth = [], []
            for i in ALL_LANDMARK_INDICES:
                # ── MediaPipe: 자체 추정값 (x,y = 픽셀, z = 추정 깊이) ──
                x = face[i].x * W
                y = face[i].y * H
                z_mp = face[i].z * W
                pts_mp.append([x, y, z_mp])

                # ── RealSense: 그 픽셀의 실측 depth를 intrinsics로 역투영한
                #    실제 3D 좌표 (X,Y,Z) mm — x,y,z 모두 MediaPipe와 다른 값 ──
                xi = int(np.clip(x, 0, W - 1))
                yi = int(np.clip(y, 0, H - 1))
                depth_m = float(depth[yi, xi]) * depth_scale          # 미터
                X, Y, Z = rs.rs2_deproject_pixel_to_point(
                    depth_intrin, [xi, yi], depth_m)
                pts_depth.append([X * 1000.0, Y * 1000.0, Z * 1000.0])  # mm

            pts_mp = np.array(pts_mp, np.float32)
            pts_depth = np.array(pts_depth, np.float32)

            # 입술 외곽 오버레이
            for li in OUTER_LIP_LOCAL:
                cv2.circle(disp, (int(pts_mp[li, 0]), int(pts_mp[li, 1])), 2, (0, 255, 0), -1)

            if recording:
                buf_mp.append(pts_mp)
                buf_depth.append(pts_depth)
                # 2초(REC_FRAMES) 채우면 자동 정지 + 저장 → 모든 take 길이 동일
                if len(buf_mp) >= REC_FRAMES:
                    n = take[cur_word]
                    wdir = out_root / cur_word
                    wdir.mkdir(exist_ok=True)
                    np.save(wdir / f"take_{n:02d}_mp.npy", np.array(buf_mp, np.float32))
                    np.save(wdir / f"take_{n:02d}_depth.npy", np.array(buf_depth, np.float32))
                    take[cur_word] += 1
                    print(f"저장: {cur_word} take {n} ({len(buf_mp)}프레임 = {REC_SECONDS}초)")
                    recording = False

        # UI 텍스트 (한글 렌더링: PIL)
        status = f"REC {len(buf_mp)}/{REC_FRAMES}" if recording else ("FACE" if has_face else "NO FACE")
        disp = draw_overlay(disp, cur_word, wi, len(words), take[cur_word], status, recording)
        cv2.imshow("D435i 수집", disp)
        frame_idx += 1

        k = cv2.waitKey(1) & 0xFF
        if k == ord(" "):
            if not recording:
                recording = True
                buf_mp, buf_depth = [], []
                print(f"녹화 시작: {cur_word} ({REC_SECONDS}초 자동)")
            else:
                recording = False  # 2초 채우기 전 스페이스 = 취소
                print("녹화 취소")
        elif k == ord("n"):
            wi = (wi + 1) % len(words); recording = False
        elif k == ord("p"):
            wi = (wi - 1) % len(words); recording = False
        elif k == ord("r"):
            take[cur_word] = 0; print(f"{cur_word} take 리셋")
        elif k == ord("q"):
            break

    pipe.stop()
    landmarker.close()
    cv2.destroyAllWindows()
    print(f"\n완료. 저장 위치: {out_root}")
    for w in words:
        print(f"  {w}: {take[w]} takes")


if __name__ == "__main__":
    main()

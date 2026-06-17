"use strict";

const $ = (id) => document.getElementById(id);

async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
  });
  return res.json();
}

function render(s) {
  // 현재 단어
  $("curWord").textContent = s.word || "—";
  const kind = $("wordKind");
  kind.textContent = s.kind === "calib" ? "기준동작" : "명령어";
  kind.classList.toggle("calib", s.kind === "calib");

  // 현재 단어 카운트 / 목표
  const cur = s.words[s.wi] || { count: 0, target: 0 };
  $("wordCount").textContent = `${cur.count} / ${cur.target}`;

  // 현재 단어 수행 안내
  const guide = $("wordGuide");
  guide.textContent = s.guide || "";
  guide.classList.toggle("calib", s.kind === "calib");

  // 총계, 상태
  $("total").textContent = s.total;
  $("statusLine").textContent = s.status;

  // 얼굴 인식 + 거리 (권장 40~50cm)
  const fb = $("faceBadge");
  if (s.has_face) {
    const cm = (s.distance_mm || 0) / 10;
    let tag = "";
    if (cm > 0) tag = cm < 35 ? " · 너무 가까움" : cm > 55 ? " · 너무 멈" : " · 적정";
    fb.textContent = `얼굴 인식됨 · ${cm.toFixed(0)}cm${tag}`;
    fb.classList.toggle("warn", cm > 0 && (cm < 35 || cm > 55));
  } else {
    fb.textContent = "얼굴 없음";
    fb.classList.remove("warn");
  }
  fb.classList.toggle("ok", s.has_face);

  // 녹화 상태
  const recBadge = $("recBadge");
  recBadge.classList.toggle("hidden", !s.recording);
  const pct = s.rec_frames ? (s.progress / s.rec_frames) * 100 : 0;
  $("progBar").style.width = s.recording ? `${pct}%` : "0%";

  const recBtn = $("recordBtn");
  recBtn.disabled = !s.speaker || !s.camera_ok;
  recBtn.classList.toggle("armed", s.recording);
  recBtn.textContent = s.recording
    ? `녹화중 ${s.progress}/${s.rec_frames}`
    : "녹화 (Space)";

  // 단어 목록
  const ul = $("wordList");
  ul.innerHTML = "";
  s.words.forEach((w, i) => {
    const li = document.createElement("li");
    li.className =
      (i === s.wi ? "active " : "") +
      (w.kind === "calib" ? "calib " : "") +
      (w.count >= w.target ? "done" : "");
    li.innerHTML =
      `<span class="dot"></span>` +
      `<span class="name">${w.name}</span>` +
      `<span class="cnt">${w.count}/${w.target}</span>`;
    li.onclick = () => post("/api/select", { index: i }).then(render);
    ul.appendChild(li);
  });
}

// ── 버튼 ──
$("setSpeaker").onclick = () =>
  post("/api/speaker", {
    speaker: $("speaker").value,
    dataset: $("dataset").value,
  }).then(render);

$("recordBtn").onclick = () => post("/api/record").then(render);
$("nextBtn").onclick = () => post("/api/next").then(render);
$("prevBtn").onclick = () => post("/api/prev").then(render);
$("resetBtn").onclick = () => post("/api/reset_take").then(render);

// ── 단축키 (IME 영향 없음: e.code 사용) ──
document.addEventListener("keydown", (e) => {
  const t = e.target.tagName;
  if (t === "INPUT" || t === "TEXTAREA") return; // 입력창에선 무시
  if (e.code === "Space") {
    e.preventDefault();
    post("/api/record").then(render);
  } else if (e.code === "KeyN") {
    post("/api/next").then(render);
  } else if (e.code === "KeyP") {
    post("/api/prev").then(render);
  }
});

// ── 상태 폴링 ──
async function poll() {
  try {
    const s = await (await fetch("/api/state")).json();
    render(s);
  } catch (err) {
    $("statusLine").textContent = "서버 연결 끊김 — 재시도 중...";
  }
}
setInterval(poll, 150);
poll();

// ── 영상: 스냅샷 폴링 (MJPEG 멈춤 회피, 다음 프레임은 직전 로드 후 요청) ──
const videoImg = $("video");
function nextFrame() {
  videoImg.src = "/snapshot?t=" + Date.now();
}
videoImg.onload = () => setTimeout(nextFrame, 33);   // ~30fps
videoImg.onerror = () => setTimeout(nextFrame, 200); // 준비 전이면 잠시 후 재시도
nextFrame();

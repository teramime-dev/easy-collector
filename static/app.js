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

  // 총계, 상태
  $("total").textContent = s.total;
  $("statusLine").textContent = s.status;

  // 얼굴 인식
  const fb = $("faceBadge");
  fb.textContent = s.has_face ? "얼굴 인식됨" : "얼굴 없음";
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

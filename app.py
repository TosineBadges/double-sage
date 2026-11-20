import os, random, string, time
from flask import Flask, request, jsonify, send_from_directory, abort

app = Flask(__name__)

ROOMS = {}

STARTER_PROMPTS = [
    ("Geography", "What is the largest hot desert in the world?", "Sahara"),
    ("Geography", "Which river flows through Cairo?", "Nile"),
    ("Geography", "What is the capital city of Japan?", "Tokyo"),
    ("Geography", "Which country has the most natural lakes?", "Canada"),
    ("Geography", "What is the smallest country in the world?", "Vatican City"),
    ("Science", "What planet is closest to the Sun?", "Mercury"),
    ("Science", "What gas do plants absorb from the atmosphere?", "Carbon dioxide"),
    ("Science", "How many bones are in an adult human body?", "206"),
    ("Science", "What is the chemical symbol for gold?", "Au"),
    ("Science", "What organ pumps blood throughout the human body?", "Heart"),
    ("Pop Culture", "Who painted the Mona Lisa?", "Leonardo da Vinci"),
    ("Pop Culture", "What fictional city does Batman protect?", "Gotham City"),
    ("Pop Culture", "How many strings does a standard guitar have?", "6"),
    ("Pop Culture", "Who wrote the Harry Potter book series?", "J.K. Rowling"),
    ("Pop Culture", "What color is the Hogwarts Express?", "Red"),
    ("Sports", "How many players are on a standard soccer team on the field?", "11"),
    ("Sports", "In which sport would you perform a slam dunk?", "Basketball"),
    ("Sports", "How often are the Summer Olympic Games held (in years)?", "4"),
    ("Sports", "What country won the first FIFA World Cup in 1930?", "Uruguay"),
    ("Sports", "How many rings are on the Olympic flag?", "5"),
    ("History & General", "In what year did World War II end?", "1945"),
    ("History & General", "How many days are in a leap year?", "366"),
    ("History & General", "What is the hardest natural substance on Earth?", "Diamond"),
    ("History & General", "How many continents are there on Earth?", "7"),
    ("History & General", "What currency is used in the United Kingdom?", "Pound sterling")
]

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Double Sage - Online Multiplayer</title>
<style>
  :root {
    --bg: #070b14;
    --card: #111827;
    --border: #1f2937;
    --accent: #f59e0b;
    --accent2: #3b82f6;
    --success: #10b981;
    --danger: #ef4444;
    --text: #f9fafb;
    --muted: #9ca3af;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }
  body { background: var(--bg); color: var(--text); min-height: 100vh; padding-bottom: 40px; }

  #introOverlay {
    position: fixed !important;
    inset: 0 !important;
    z-index: 99990 !important;
    background: #070b14 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 20px;
    text-align: center;
  }
  #introOverlay img {
    max-width: 92vw;
    max-height: 55vh;
    border-radius: 16px;
    border: 2px solid var(--accent);
    box-shadow: 0 10px 35px rgba(245, 158, 11, 0.35);
    object-fit: contain;
    background: #0f172a;
  }
  .intro-caption { margin-top: 14px; font-size: 1.15rem; font-weight: 700; color: var(--accent); }
  .intro-bar-wrap { width: 260px; height: 6px; background: #1f2937; border-radius: 999px; overflow: hidden; margin: 12px auto; }
  .intro-bar { height: 100%; width: 0%; background: var(--accent); transition: width 0.1s linear; }
  .intro-btns { display: flex; gap: 12px; margin-top: 14px; flex-wrap: wrap; justify-content: center; }
  #introOverlay button {
    position: relative !important;
    z-index: 99999 !important;
    pointer-events: auto !important;
    cursor: pointer !important;
    padding: 12px 20px;
    border-radius: 10px;
    border: none;
    font-weight: 800;
    font-size: 0.95rem;
  }

  .topbar {
    position: sticky; top: 0; z-index: 100;
    background: rgba(17, 24, 39, 0.96);
    border-bottom: 1px solid var(--border);
    padding: 10px 14px;
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px;
  }
  .brand { display: flex; align-items: center; gap: 8px; font-weight: 900; font-size: 1.1rem; color: var(--accent); }
  .brand img { width: 32px; height: 32px; border-radius: 8px; object-fit: cover; }
  .audio-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .pill-btn {
    background: #1f2937; color: var(--text); border: 1px solid #374151;
    padding: 6px 10px; border-radius: 8px; font-size: 0.8rem; font-weight: 700; cursor: pointer;
  }
  .pill-btn.active { background: var(--accent); color: #000; border-color: var(--accent); }
  input[type="range"] { width: 72px; accent-color: var(--accent); cursor: pointer; }

  .container { max-width: 680px; margin: 18px auto; padding: 0 14px; }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; padding: 18px; margin-bottom: 16px;
  }
  h2, h3 { margin-bottom: 10px; }
  label { display: block; font-size: 0.85rem; color: var(--muted); margin: 10px 0 4px; font-weight: 600; }
  input[type="text"], input[type="number"], select, textarea {
    width: 100%; padding: 11px; border-radius: 10px;
    background: #0b1120; border: 1px solid #374151; color: var(--text); font-size: 1rem;
  }
  .btn {
    width: 100%; padding: 13px; border: none; border-radius: 10px;
    font-size: 1rem; font-weight: 800; cursor: pointer; margin-top: 12px;
  }
  .btn-primary { background: var(--accent); color: #000; }
  .btn-blue { background: var(--accent2); color: #fff; }
  .btn-success { background: var(--success); color: #000; }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-ghost { background: #1f2937; color: var(--text); border: 1px solid #374151; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; }
  .row > * { flex: 1; min-width: 130px; }
  .badge {
    display: inline-block; padding: 4px 10px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 800; background: #1f2937; color: var(--accent);
  }
  .room-code-box {
    font-size: 2rem; font-weight: 900; letter-spacing: 6px; text-align: center;
    background: #0b1120; border: 2px dashed var(--accent); padding: 12px; border-radius: 12px; margin: 10px 0;
  }
  .timer-box {
    font-size: 2.2rem; font-weight: 900; text-align: center; color: var(--accent);
    padding: 10px; background: #0b1120; border-radius: 12px; margin: 10px 0;
  }
  .timer-box.urgent { color: var(--danger); animation: pulse 0.6s infinite alternate; }
  @keyframes pulse { from { transform: scale(1); } to { transform: scale(1.05); } }
  .hint-box {
    background: rgba(59, 130, 246, 0.14); border: 1px solid var(--accent2);
    padding: 12px; border-radius: 10px; margin: 10px 0; font-weight: 700; color: #93c5fd;
  }
  .player-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px; background: #0b1120; border-radius: 10px; margin-bottom: 8px;
  }
  .hidden { display: none !important; }
  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 500;
    display: flex; align-items: center; justify-content: center; padding: 16px;
  }
  .modal {
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    max-width: 520px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 18px;
  }
</style>
</head>
<body>

<div id="introOverlay">
  <img id="introImg" src="/media/double_sage_icon" alt="Double Sage">
  <div id="introCaption" class="intro-caption">DOUBLE SAGE - MIND DUEL</div>
  <div class="intro-bar-wrap"><div id="introBar" class="intro-bar"></div></div>
  <div class="intro-btns">
    <button style="background:#10b981;color:#000;" onclick="enableSoundFromIntro()">🔊 Enable Loud Sound & Music</button>
    <button style="background:#f59e0b;color:#000;" onclick="skipIntro()">Skip Intro ⏭</button>
  </div>
</div>

<div class="topbar">
  <div class="brand">
    <img src="/media/double_sage_icon" onerror="this.style.display='none'" alt="">
    <span>DOUBLE SAGE</span>
  </div>
  <div class="audio-bar">
    <button class="pill-btn" onclick="replayIntro()">🎬 Intro</button>
    <button class="pill-btn" onclick="openQbModal()">📚 My QB's</button>
    <button id="musicBtn" class="pill-btn active" onclick="toggleMusic()">🎵 Music: ON</button>
    <button id="sfxBtn" class="pill-btn active" onclick="toggleSfx()">🔊 SFX: ON</button>
    <input id="volSlider" type="range" min="0" max="1" step="0.05" value="0.9" oninput="setVolume(this.value)" title="Master Volume">
    <button class="pill-btn" onclick="document.getElementById('songPicker').click()">📂 Load Song</button>
    <input id="songPicker" type="file" accept="audio/*" class="hidden" onchange="loadCustomSongFile(event)">
  </div>
</div>

<div class="container">
  <div id="homeView" class="card">
    <h2>Online Multi-Phone Arena</h2>
    <p style="color:var(--muted);font-size:0.9rem;margin-bottom:12px;">Create a room to get a 4-letter code, or join a friend's room from your phone.</p>

    <label>Your Display Name</label>
    <input id="playerName" type="text" placeholder="Enter your name (e.g. Tunde)" maxlength="20">

    <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border);">
      <h3>Create a New Room</h3>
      <div class="row">
        <div>
          <label>Max Players (2-10)</label>
          <input id="maxPlayers" type="number" min="2" max="10" value="2">
        </div>
        <div>
          <label>Questions / Player</label>
          <input id="qPerPlayer" type="number" min="1" max="15" value="3">
        </div>
        <div>
          <label>Timer (10s - 60s)</label>
          <input id="timeLimit" type="number" min="10" max="60" value="30">
        </div>
      </div>
      <label style="display:flex;align-items:center;gap:8px;margin-top:12px;color:var(--text);cursor:pointer;">
        <input id="umpireCheck" type="checkbox" style="width:18px;height:18px;">
        <span>Play as Umpire (Organizer sets all questions; ruling is final)</span>
      </label>
      <button class="btn btn-primary" onclick="createRoom()">Create Room & Generate Code</button>
    </div>

    <div style="margin-top:18px;padding-top:14px;border-top:1px solid var(--border);">
      <h3>Join Existing Room</h3>
      <label>4-Letter Room Code</label>
      <input id="joinCode" type="text" placeholder="e.g. SAGE" maxlength="4" style="text-transform:uppercase;">
      <button class="btn btn-blue" onclick="joinRoom()">Join Room</button>
    </div>
  </div>

  <div id="roomView" class="hidden"></div>
</div>

<div id="qbModal" class="modal-backdrop hidden">
  <div class="modal">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <h3>📚 My QB's (Saved Question Banks)</h3>
      <button class="pill-btn" onclick="closeQbModal()">✖ Close</button>
    </div>
    <p style="color:var(--muted);font-size:0.85rem;margin-bottom:10px;">Save questions and secret answers on your phone so you can load them in one tap during any round.</p>
    <label>Question</label>
    <input id="qbNewQ" type="text" placeholder="Type a question to save...">
    <label>Secret Answer</label>
    <input id="qbNewA" type="text" placeholder="Type the exact answer...">
    <button class="btn btn-success" onclick="addQbItem()">💾 Add to My QB's</button>
    <div id="qbList" style="margin-top:14px;"></div>
  </div>
</div>

<script>
const SLIDES = [
  { src: "/media/double_sage_icon", label: "DOUBLE SAGE - MIND DUEL" },
  { src: "/media/double_sage_battle", label: "HEAD-TO-HEAD INTELLECTUAL CLASH" },
  { src: "/media/double_sage_banner", label: "OUTSMART. OUTPACE. OUTSCORE." },
  { src: "/media/double_sage_tournament", label: "TOURNAMENTS & MULTIPLAYER ARENA" }
];
let slideIdx = 0;
let slideProg = 0;
window.introTimer = null;

function startIntroSequence() {
  const ov = document.getElementById("introOverlay");
  const img = document.getElementById("introImg");
  const cap = document.getElementById("introCaption");
  const bar = document.getElementById("introBar");
  if (!ov) return;
  ov.style.display = "flex";
  slideIdx = 0;
  slideProg = 0;
  img.src = SLIDES[0].src;
  cap.textContent = SLIDES[0].label;
  bar.style.width = "0%";
  if (window.introTimer) clearInterval(window.introTimer);
  window.introTimer = setInterval(() => {
    slideProg += 100;
    bar.style.width = Math.min(100, (slideProg / 3000) * 100) + "%";
    if (slideProg >= 3000) {
      slideProg = 0;
      slideIdx++;
      if (slideIdx >= SLIDES.length) {
        skipIntro();
        return;
      }
      img.src = SLIDES[slideIdx].src;
      cap.textContent = SLIDES[slideIdx].label;
      bar.style.width = "0%";
    }
  }, 100);
}

window.skipIntro = function() {
  if (window.introTimer) clearInterval(window.introTimer);
  const ov = document.getElementById("introOverlay");
  if (ov) ov.style.display = "none";
  unlockAudio();
};

function replayIntro() {
  startIntroSequence();
}

function enableSoundFromIntro() {
  unlockAudio();
  playSfx("lock");
}

let audioCtx = null, masterGain = null, bgmInterval = null;
let musicOn = true, sfxOn = true, masterVol = 0.9;
let customSongAudio = null, usingCustomTrack = false;

function initThemeSong() {
  customSongAudio = new Audio("/media/theme_song");
  customSongAudio.loop = true;
  customSongAudio.volume = masterVol;
  customSongAudio.addEventListener("canplaythrough", () => {
    usingCustomTrack = true;
    if (bgmInterval) { clearInterval(bgmInterval); bgmInterval = null; }
    if (musicOn && audioCtx && audioCtx.state === "running") {
      customSongAudio.play().catch(() => {});
    }
  });
  customSongAudio.addEventListener("error", () => {
    usingCustomTrack = false;
  });
}

function unlockAudio() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    audioCtx = new AC();
    const comp = audioCtx.createDynamicsCompressor();
    comp.threshold.value = -12;
    comp.ratio.value = 8;
    masterGain = audioCtx.createGain();
    masterGain.gain.value = masterVol;
    comp.connect(masterGain);
    masterGain.connect(audioCtx.destination);
    window._audioOut = comp;
  }
  if (audioCtx.state === "suspended") audioCtx.resume();
  if (musicOn) {
    if (usingCustomTrack && customSongAudio) {
      customSongAudio.volume = masterVol;
      customSongAudio.play().catch(() => {});
    } else if (!bgmInterval) {
      startSynthBgm();
    }
  }
}

function startSynthBgm() {
  if (bgmInterval) return;
  const notes = [130.81, 164.81, 196.00, 261.63, 196.00, 164.81, 146.83, 220.00];
  let step = 0;
  bgmInterval = setInterval(() => {
    if (!musicOn || usingCustomTrack || !audioCtx || audioCtx.state !== "running") return;
    const osc = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    osc.type = "sawtooth";
    osc.frequency.value = notes[step % notes.length];
    g.gain.setValueAtTime(0.28, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.22);
    osc.connect(g);
    g.connect(window._audioOut);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.24);
    step++;
  }, 260);
}

function toggleMusic() {
  unlockAudio();
  musicOn = !musicOn;
  const btn = document.getElementById("musicBtn");
  btn.textContent = musicOn ? "🎵 Music: ON" : "🎵 Music: OFF";
  btn.classList.toggle("active", musicOn);
  if (usingCustomTrack && customSongAudio) {
    if (musicOn) customSongAudio.play().catch(() => {});
    else customSongAudio.pause();
  }
}

function toggleSfx() {
  unlockAudio();
  sfxOn = !sfxOn;
  const btn = document.getElementById("sfxBtn");
  btn.textContent = sfxOn ? "🔊 SFX: ON" : "🔇 SFX: OFF";
  btn.classList.toggle("active", sfxOn);
}

function setVolume(val) {
  masterVol = parseFloat(val);
  if (masterGain) masterGain.gain.value = masterVol;
  if (customSongAudio) customSongAudio.volume = masterVol;
}

function loadCustomSongFile(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  unlockAudio();
  if (customSongAudio) customSongAudio.pause();
  if (bgmInterval) { clearInterval(bgmInterval); bgmInterval = null; }
  customSongAudio = new Audio(URL.createObjectURL(file));
  customSongAudio.loop = true;
  customSongAudio.volume = masterVol;
  usingCustomTrack = true;
  musicOn = true;
  document.getElementById("musicBtn").textContent = "🎵 Music: ON";
  document.getElementById("musicBtn").classList.add("active");
  customSongAudio.play().catch(() => {});
}

function playSfx(type) {
  if (!sfxOn) return;
  unlockAudio();
  if (!audioCtx) return;
  const osc = audioCtx.createOscillator();
  const g = audioCtx.createGain();
  const now = audioCtx.currentTime;
  if (type === "win") {
    osc.type = "triangle";
    osc.frequency.setValueAtTime(523.25, now);
    osc.frequency.setValueAtTime(659.25, now + 0.1);
    osc.frequency.setValueAtTime(783.99, now + 0.2);
    g.gain.setValueAtTime(0.45, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
    osc.connect(g); g.connect(window._audioOut);
    osc.start(now); osc.stop(now + 0.46);
  } else if (type === "wrong") {
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(160, now);
    osc.frequency.linearRampToValueAtTime(110, now + 0.3);
    g.gain.setValueAtTime(0.4, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.32);
    osc.connect(g); g.connect(window._audioOut);
    osc.start(now); osc.stop(now + 0.34);
  } else {
    osc.type = "sine";
    osc.frequency.setValueAtTime(660, now);
    g.gain.setValueAtTime(0.3, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.14);
    osc.connect(g); g.connect(window._audioOut);
    osc.start(now); osc.stop(now + 0.15);
  }
}

document.addEventListener("pointerdown", unlockAudio, { once: true });

const QB_KEY = "double_sage_qbs_v1";
let usedQbIndices = new Set();

function getQbs() {
  try { return JSON.parse(localStorage.getItem(QB_KEY) || "[]"); }
  catch (e) { return []; }
}
function saveQbs(list) {
  localStorage.setItem(QB_KEY, JSON.stringify(list));
}
function openQbModal() {
  renderQbList();
  document.getElementById("qbModal").classList.remove("hidden");
}
function closeQbModal() {
  document.getElementById("qbModal").classList.add("hidden");
}
function addQbItem() {
  const q = document.getElementById("qbNewQ").value.trim();
  const a = document.getElementById("qbNewA").value.trim();
  if (!q || !a) return alert("Enter both a question and answer.");
  const list = getQbs();
  list.push({ q, a });
  saveQbs(list);
  document.getElementById("qbNewQ").value = "";
  document.getElementById("qbNewA").value = "";
  renderQbList();
  playSfx("lock");
}
function deleteQbItem(idx) {
  const list = getQbs();
  list.splice(idx, 1);
  saveQbs(list);
  renderQbList();
}
function renderQbList() {
  const list = getQbs();
  const box = document.getElementById("qbList");
  if (!list.length) {
    box.innerHTML = "<p style='color:var(--muted);'>No saved QB's yet. Add your favorite traps above!</p>";
    return;
  }
  box.innerHTML = list.map((item, i) => `
    <div class="player-item">
      <div>
        <div style="font-weight:700;">${escapeHtml(item.q)}</div>
        <div style="font-size:0.82rem;color:var(--accent);">Ans: ${escapeHtml(item.a)}</div>
      </div>
      <button class="pill-btn" style="color:#ef4444;" onclick="deleteQbItem(${i})">Delete</button>
    </div>
  `).join("");
}

function saveCurrentInputsToQb() {
  const qEl = document.getElementById("askerQInput");
  const aEl = document.getElementById("askerAInput");
  if (!qEl || !aEl) return;
  const q = qEl.value.trim();
  const a = aEl.value.trim();
  if (!q || !a) return alert("Type a question and secret answer first.");
  const list = getQbs();
  list.push({ q, a });
  saveQbs(list);
  playSfx("lock");
  alert("Saved to My QB's!");
}

function loadNextUnusedQb() {
  const list = getQbs();
  if (!list.length) return alert("Your QB bank is empty! Tap 'My QB's' to save questions first.");
  let idx = list.findIndex((_, i) => !usedQbIndices.has(i));
  if (idx === -1) {
    usedQbIndices.clear();
    idx = 0;
  }
  usedQbIndices.add(idx);
  const qEl = document.getElementById("askerQInput");
  const aEl = document.getElementById("askerAInput");
  if (qEl && aEl) {
    qEl.value = list[idx].q;
    aEl.value = list[idx].a;
    playSfx("lock");
  }
}

function applySelectedQb(sel) {
  if (sel.value === "") return;
  const list = getQbs();
  const idx = parseInt(sel.value, 10);
  if (list[idx]) {
    usedQbIndices.add(idx);
    document.getElementById("askerQInput").value = list[idx].q;
    document.getElementById("askerAInput").value = list[idx].a;
    playSfx("lock");
  }
}

function applyStarterPrompt(sel) {
  if (sel.value === "") return;
  const prompts = window._starterPrompts || [];
  const idx = parseInt(sel.value, 10);
  if (prompts[idx]) {
    document.getElementById("askerQInput").value = prompts[idx][1];
    document.getElementById("askerAInput").value = prompts[idx][2];
    playSfx("lock");
  }
}

let roomCode = "";
let playerId = localStorage.getItem("ds_pid") || ("p_" + Math.random().toString(36).slice(2, 10));
localStorage.setItem("ds_pid", playerId);
let pollTimer = null;
let lastRenderKey = "";

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined
  });
  return res.json();
}

async function createRoom() {
  unlockAudio();
  const name = document.getElementById("playerName").value.trim();
  if (!name) return alert("Please enter your name.");
  const data = await api("/api/create", {
    pid: playerId,
    name,
    max_players: parseInt(document.getElementById("maxPlayers").value, 10) || 2,
    q_per_player: parseInt(document.getElementById("qPerPlayer").value, 10) || 3,
    time_limit: parseInt(document.getElementById("timeLimit").value, 10) || 30,
    umpire_mode: document.getElementById("umpireCheck").checked
  });
  if (data.error) return alert(data.error);
  roomCode = data.code;
  playSfx("lock");
  startPolling();
}

async function joinRoom() {
  unlockAudio();
  const name = document.getElementById("playerName").value.trim();
  const code = document.getElementById("joinCode").value.trim().toUpperCase();
  if (!name || code.length !== 4) return alert("Enter your name and the 4-letter room code.");
  const data = await api("/api/join", { pid: playerId, name, code });
  if (data.error) return alert(data.error);
  roomCode = code;
  playSfx("lock");
  startPolling();
}

function startPolling() {
  document.getElementById("homeView").classList.add("hidden");
  document.getElementById("roomView").classList.remove("hidden");
  if (pollTimer) clearInterval(pollTimer);
  fetchState();
  pollTimer = setInterval(fetchState, 1200);
}

async function fetchState() {
  if (!roomCode) return;
  const st = await api(`/api/state?code=${encodeURIComponent(roomCode)}&pid=${encodeURIComponent(playerId)}`);
  if (st.error) {
    clearInterval(pollTimer);
    alert(st.error);
    location.href = "/";
    return;
  }
  window._starterPrompts = st.starter_prompts || [];
  renderRoom(st);
}

function copyInviteLink() {
  const url = `${location.origin}/?room=${roomCode}`;
  navigator.clipboard.writeText(url).then(() => alert("Invite link copied: " + url));
}

function renderRoom(st) {
  const rv = document.getElementById("roomView");
  const isHost = st.host_id === playerId;
  const isAsker = st.asker_id === playerId;
  const isGuesser = st.guesser_id === playerId;

  if (st.phase === "asking" && isAsker) {
    const askKey = `asking_${st.round_num}_${st.turn_index}`;
    if (lastRenderKey === askKey && document.getElementById("askerQInput")) return;
    lastRenderKey = askKey;
  } else {
    lastRenderKey = `${st.phase}_${st.round_num}_${st.turn_index}_${st.players.length}_${st.contested}`;
  }

  if (st.phase === "lobby") {
    const inviteUrl = `${location.origin}/?room=${st.code}`;
    rv.innerHTML = `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span class="badge">${st.umpire_mode ? "⚖️ UMPIRE MODE" : "⚔️ STANDARD DUEL"}</span>
          <span class="badge">${st.time_limit}s Timer • ${st.q_per_player} Q/Player</span>
        </div>
        <div class="room-code-box">${st.code}</div>
        <button class="btn btn-ghost" onclick="copyInviteLink()">🔗 Copy One-Tap Invite Link</button>
        <p style="font-size:0.8rem;color:var(--muted);text-align:center;margin-top:6px;">${inviteUrl}</p>

        <h3 style="margin-top:16px;">Players in Lobby (${st.players.length}/${st.max_players})</h3>
        ${st.umpire_mode ? `<div class="player-item"><span>⚖️ <strong>${escapeHtml(st.umpire_name)}</strong> (Umpire / Organizer)</span><span class="badge">HOST</span></div>` : ""}
        ${st.players.map(p => `
          <div class="player-item">
            <span>🎮 <strong>${escapeHtml(p.name)}</strong> ${p.id === st.host_id ? "(Host)" : ""}</span>
            ${isHost && p.id !== playerId ? `<button class="pill-btn" style="color:#ef4444;" onclick="kickPlayer('${p.id}')">Kick</button>` : ""}
          </div>
        `).join("")}

        ${isHost ? `<button class="btn btn-primary" onclick="startGame()">🚀 Start Game Now</button>` : `<p style="text-align:center;color:var(--muted);margin-top:12px;">Waiting for host to start the match...</p>`}
      </div>
    `;
    return;
  }

  if (st.phase === "asking") {
    if (isAsker) {
      const qbs = getQbs();
      const prompts = window._starterPrompts || [];
      rv.innerHTML = `
        <div class="card">
          <span class="badge">Round ${st.round_num} • Your Turn to Set Question</span>
          <h3 style="margin-top:8px;">Target Guesser: ${escapeHtml(st.guesser_name)}</h3>

          <div class="row" style="margin-top:10px;">
            <button class="btn btn-ghost" style="margin-top:0;" onclick="loadNextUnusedQb()">⚡ Next Unused QB</button>
            <button class="btn btn-ghost" style="margin-top:0;" onclick="saveCurrentInputsToQb()">💾 Save to My QB's</button>
          </div>

          <label>Load From My QB's (${qbs.length} saved)</label>
          <select onchange="applySelectedQb(this)">
            <option value="">-- Choose a saved QB --</option>
            ${qbs.map((item, i) => `<option value="${i}">${escapeHtml(item.q)}</option>`).join("")}
          </select>

          <label>Or Pick an Editable Starter Prompt</label>
          <select onchange="applyStarterPrompt(this)">
            <option value="">-- Choose a starter prompt --</option>
            ${prompts.map((p, i) => `<option value="${i}">[${escapeHtml(p[0])}] ${escapeHtml(p[1])}</option>`).join("")}
          </select>

          <label>Question for ${escapeHtml(st.guesser_name)}</label>
          <textarea id="askerQInput" rows="2" placeholder="Write or edit your question..."></textarea>

          <label>Exact Secret Answer</label>
          <input id="askerAInput" type="text" placeholder="Write or edit the exact answer...">

          <button class="btn btn-primary" onclick="submitQuestion()">🔒 Lock Question & Start Timer</button>
        </div>
      `;
    } else {
      rv.innerHTML = `
        <div class="card" style="text-align:center;">
          <span class="badge">Round ${st.round_num}</span>
          <h2 style="margin-top:12px;">${escapeHtml(st.asker_name)} is setting a question...</h2>
          <p style="color:var(--muted);">Guesser on deck: <strong>${escapeHtml(st.guesser_name)}</strong></p>
        </div>
      `;
    }
    return;
  }

  if (st.phase === "guessing") {
    const rem = Math.max(0, Math.ceil(st.deadline - st.now));
    if (rem === 0 && isGuesser && !window._autoTimedOut) {
      window._autoTimedOut = true;
      submitGuess(true);
    }
    rv.innerHTML = `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span class="badge">Round ${st.round_num}</span>
          <span class="badge">Guesser: ${escapeHtml(st.guesser_name)}</span>
        </div>
        <div class="timer-box ${rem <= 5 ? "urgent" : ""}">${rem}s</div>
        <h3>Question:</h3>
        <p style="font-size:1.2rem;font-weight:700;margin:8px 0;">${escapeHtml(st.question)}</p>
        <div class="hint-box">🤖 Manager Hint: ${escapeHtml(st.hint)}</div>

        ${isGuesser ? `
          <label>Your Answer</label>
          <input id="guessInput" type="text" placeholder="Type your answer quickly..." autocomplete="off">
          <button class="btn btn-success" onclick="submitGuess(false)">⚡ Lock In Answer</button>
        ` : `<p style="text-align:center;color:var(--muted);margin-top:12px;">Waiting for <strong>${escapeHtml(st.guesser_name)}</strong> to submit an answer...</p>`}
      </div>
    `;
    return;
  }

  if (st.phase === "review") {
    rv.innerHTML = `
      <div class="card">
        <span class="badge">Round ${st.round_num} Result</span>
        <h2 style="margin-top:10px;color:${st.last_correct ? "var(--success)" : "var(--danger)"};">
          ${st.last_correct ? "✅ CORRECT! (+5 Pts to " + escapeHtml(st.guesser_name) + ")" : "❌ WRONG / TIME UP! (+5 Pts to " + escapeHtml(st.asker_name) + ")"}
        </h2>
        <p style="margin:8px 0;"><strong>Question:</strong> ${escapeHtml(st.question)}</p>
        <p style="margin:4px 0;"><strong>Secret Answer:</strong> ${escapeHtml(st.secret_answer)}</p>
        <p style="margin:4px 0;"><strong>${escapeHtml(st.guesser_name)}'s Guess:</strong> ${escapeHtml(st.last_guess || "(No answer)")}</p>
        <p style="margin:4px 0;color:var(--muted);">Time Taken: ${st.last_time}s</p>

        ${!st.last_correct && !st.umpire_mode && !st.contested && isGuesser ? `
          <button class="btn btn-danger" onclick="contestAnswer()">🚩 CONTEST ANSWER (Dispute Call)</button>
        ` : ""}

        ${st.contested ? `
          <div class="hint-box" style="border-color:var(--accent);color:var(--text);">
            🚩 <strong>${escapeHtml(st.guesser_name)} contested this result!</strong><br>
            ${isAsker ? `
              <div class="row" style="margin-top:10px;">
                <button class="btn btn-success" style="margin-top:0;" onclick="resolveContest('accept')">✅ Accept Guess (+5 Pts to Guesser)</button>
                <button class="btn btn-blue" style="margin-top:0;" onclick="resolveContest('reask')">🔄 Send New Question (0 Pts & Re-Ask)</button>
              </div>
            ` : `<p style="margin-top:6px;color:var(--accent);">Waiting for ${escapeHtml(st.asker_name)} to decide...</p>`}
          </div>
        ` : ""}

        ${!st.contested && (isAsker || isHost) ? `
          <button class="btn btn-primary" onclick="nextTurn()">Next Turn ⏭</button>
        ` : ""}
      </div>
    `;
    return;
  }

  if (st.phase === "gameover") {
    rv.innerHTML = `
      <div class="card">
        <h2>🏆 Final Standings</h2>
        <p style="color:var(--muted);font-size:0.85rem;margin-bottom:12px;">Ties are broken by shortest cumulative answering time.</p>
        ${st.standings.map((p, i) => `
          <div class="player-item" style="${i === 0 ? "border:1px solid var(--accent);" : ""}">
            <span>${i === 0 ? "👑" : "#" + (i + 1)} <strong>${escapeHtml(p.name)}</strong></span>
            <span><strong>${p.score} pts</strong> <span style="color:var(--muted);font-size:0.85rem;">(${p.total_time.toFixed(1)}s)</span></span>
          </div>
        `).join("")}
        ${isHost ? `<button class="btn btn-primary" onclick="location.href='/'">🔄 Play Another Match</button>` : ""}
      </div>
    `;
  }
}

async function kickPlayer(targetId) {
  await api("/api/kick", { code: roomCode, pid: playerId, target_id: targetId });
  fetchState();
}

async function startGame() {
  unlockAudio();
  const res = await api("/api/start", { code: roomCode, pid: playerId });
  if (res.error) alert(res.error);
  playSfx("lock");
  fetchState();
}

async function submitQuestion() {
  const q = document.getElementById("askerQInput").value.trim();
  const a = document.getElementById("askerAInput").value.trim();
  if (!q || !a) return alert("Enter both a question and a secret answer.");
  window._autoTimedOut = false;
  const res = await api("/api/ask", { code: roomCode, pid: playerId, question: q, answer: a });
  if (res.error) return alert(res.error);
  playSfx("lock");
  fetchState();
}

async function submitGuess(timedOut) {
  const inp = document.getElementById("guessInput");
  const guess = timedOut ? "" : (inp ? inp.value.trim() : "");
  const res = await api("/api/guess", { code: roomCode, pid: playerId, guess });
  if (res.error) return alert(res.error);
  playSfx(res.correct ? "win" : "wrong");
  fetchState();
}

async function contestAnswer() {
  await api("/api/contest", { code: roomCode, pid: playerId });
  playSfx("wrong");
  fetchState();
}

async function resolveContest(decision) {
  await api("/api/resolve", { code: roomCode, pid: playerId, decision });
  playSfx("lock");
  fetchState();
}

async function nextTurn() {
  await api("/api/next", { code: roomCode, pid: playerId });
  playSfx("lock");
  fetchState();
}

window.addEventListener("DOMContentLoaded", () => {
  initThemeSong();
  startIntroSequence();
  const params = new URLSearchParams(location.search);
  const r = params.get("room");
  if (r) document.getElementById("joinCode").value = r.toUpperCase();
});
</script>
</body>
</html>
"""

def build_hint(answer):
    words = [w for w in answer.strip().split() if w]
    letters = sum(c.isalpha() for c in answer)
    digits = sum(c.isdigit() for c in answer)
    parts = [f"{len(words)} word{'s' if len(words) != 1 else ''}", f"{letters} letter{'s' if letters != 1 else ''}"]
    if digits > 0:
        parts.append(f"{digits} digit{'s' if digits != 1 else ''}")
    return ", ".join(parts)

def gen_code():
    while True:
        c = "".join(random.choices(string.ascii_uppercase, k=4))
        if c not in ROOMS:
            return c

@app.route("/")
def index():
    return HTML_PAGE

@app.route("/media/<name>")
def serve_media(name):
    mapping = {
        "double_sage_icon": ["double_sage_icon.jpg", "double_sage_icon.png", "icon.jpg", "icon.png"],
        "double_sage_battle": ["double_sage_battle.jpg", "double_sage_battle.png", "battle.jpg", "battle.png"],
        "double_sage_banner": ["double_sage_banner.jpg", "double_sage_banner.png", "banner.jpg", "banner.png"],
        "double_sage_tournament": ["double_sage_tournament.jpg", "double_sage_tournament.png", "tournament.jpg", "tournament.png"],
        "theme_song": ["theme.mp3", "theme.m4a", "theme.ogg", "theme.wav"]
    }
    candidates = mapping.get(name, [])
    for folder in [".", "static"]:
        if not os.path.isdir(folder):
            continue
        files = os.listdir(folder)
        lower_map = {f.lower(): f for f in files}
        for cand in candidates:
            if cand.lower() in lower_map:
                return send_from_directory(folder, lower_map[cand.lower()])
    abort(404)

@app.route("/api/create", methods=["POST"])
def api_create():
    d = request.get_json(force=True)
    name = str(d.get("name", "")).strip()[:20]
    pid = str(d.get("pid", "")).strip()
    if not name or not pid:
        return jsonify({"error": "Name required"})
    code = gen_code()
    umpire_mode = bool(d.get("umpire_mode", False))
    players = [] if umpire_mode else [{"id": pid, "name": name, "score": 0, "total_time": 0.0, "asked": 0}]
    ROOMS[code] = {
        "code": code,
        "host_id": pid,
        "umpire_mode": umpire_mode,
        "umpire_name": name if umpire_mode else "",
        "max_players": max(2, min(10, int(d.get("max_players", 2)))),
        "q_per_player": max(1, min(15, int(d.get("q_per_player", 3)))),
        "time_limit": max(10, min(60, int(d.get("time_limit", 30)))),
        "players": players,
        "phase": "lobby",
        "round_num": 1,
        "turn_index": 0,
        "asker_id": "",
        "guesser_id": "",
        "question": "",
        "secret_answer": "",
        "hint": "",
        "start_ts": 0.0,
        "deadline": 0.0,
        "last_guess": "",
        "last_correct": False,
        "last_time": 0.0,
        "contested": False
    }
    return jsonify({"code": code})

@app.route("/api/join", methods=["POST"])
def api_join():
    d = request.get_json(force=True)
    code = str(d.get("code", "")).strip().upper()
    name = str(d.get("name", "")).strip()[:20]
    pid = str(d.get("pid", "")).strip()
    room = ROOMS.get(code)
    if not room:
        return jsonify({"error": "Room not found"})
    if room["phase"] != "lobby":
        return jsonify({"error": "Game already started"})
    if room["umpire_mode"] and pid == room["host_id"]:
        return jsonify({"ok": True})
    if any(p["id"] == pid for p in room["players"]):
        return jsonify({"ok": True})
    if len(room["players"]) >= room["max_players"]:
        return jsonify({"error": "Room is full"})
    room["players"].append({"id": pid, "name": name, "score": 0, "total_time": 0.0, "asked": 0})
    return jsonify({"ok": True})

@app.route("/api/kick", methods=["POST"])
def api_kick():
    d = request.get_json(force=True)
    room = ROOMS.get(d.get("code", ""))
    if room and room["host_id"] == d.get("pid") and room["phase"] == "lobby":
        room["players"] = [p for p in room["players"] if p["id"] != d.get("target_id")]
    return jsonify({"ok": True})

def setup_turn(room):
    n = len(room["players"])
    if room["umpire_mode"]:
        total_turns = n * room["q_per_player"]
        if room["turn_index"] >= total_turns:
            room["phase"] = "gameover"
            return
        guesser = room["players"][room["turn_index"] % n]
        room["asker_id"] = room["host_id"]
        room["guesser_id"] = guesser["id"]
        room["round_num"] = (room["turn_index"] // n) + 1
    else:
        total_turns = n * room["q_per_player"]
        if room["turn_index"] >= total_turns:
            room["phase"] = "gameover"
            return
        asker = room["players"][room["turn_index"] % n]
        guesser = room["players"][(room["turn_index"] + 1) % n]
        room["asker_id"] = asker["id"]
        room["guesser_id"] = guesser["id"]
        room["round_num"] = (room["turn_index"] // n) + 1
    room["phase"] = "asking"
    room["contested"] = False

@app.route("/api/start", methods=["POST"])
def api_start():
    d = request.get_json(force=True)
    room = ROOMS.get(d.get("code", ""))
    if not room or room["host_id"] != d.get("pid"):
        return jsonify({"error": "Unauthorized"})
    if len(room["players"]) < 2:
        return jsonify({"error": "Need at least 2 players to start"})
    room["turn_index"] = 0
    setup_turn(room)
    return jsonify({"ok": True})

@app.route("/api/ask", methods=["POST"])
def api_ask():
    d = request.get_json(force=True)
    room = ROOMS.get(d.get("code", ""))
    if not room or room["asker_id"] != d.get("pid"):
        return jsonify({"error": "Not your turn to ask"})
    q = str(d.get("question", "")).strip()
    a = str(d.get("answer", "")).strip()
    if not q or not a:
        return jsonify({"error": "Question and answer required"})
    room["question"] = q
    room["secret_answer"] = a
    room["hint"] = build_hint(a)
    room["start_ts"] = time.time()
    room["deadline"] = room["start_ts"] + room["time_limit"]
    room["phase"] = "guessing"
    room["contested"] = False
    return jsonify({"ok": True})

@app.route("/api/guess", methods=["POST"])
def api_guess():
    d = request.get_json(force=True)
    room = ROOMS.get(d.get("code", ""))
    if not room or room["phase"] != "guessing" or room["guesser_id"] != d.get("pid"):
        return jsonify({"error": "Cannot submit guess right now"})
    guess = str(d.get("guess", "")).strip()
    elapsed = min(float(room["time_limit"]), max(0.1, round(time.time() - room["start_ts"], 1)))
    correct = guess.lower() == room["secret_answer"].strip().lower() and len(guess) > 0
    room["last_guess"] = guess
    room["last_correct"] = correct
    room["last_time"] = elapsed
    guesser = next((p for p in room["players"] if p["id"] == room["guesser_id"]), None)
    asker = next((p for p in room["players"] if p["id"] == room["asker_id"]), None)
    if guesser:
        guesser["total_time"] += elapsed
        if correct:
            guesser["score"] += 5
    if not correct and asker and not room["umpire_mode"]:
        asker["score"] += 5
    room["phase"] = "review"
    return jsonify({"ok": True, "correct": correct})

@app.route("/api/contest", methods=["POST"])
def api_contest():
    d = request.get_json(force=True)
    room = ROOMS.get(d.get("code", ""))
    if room and room["phase"] == "review" and not room["umpire_mode"] and room["guesser_id"] == d.get("pid"):
        room["contested"] = True
    return jsonify({"ok": True})

@app.route("/api/resolve", methods=["POST"])
def api_resolve():
    d = request.get_json(force=True)
    room = ROOMS.get(d.get("code", ""))
    if not room or not room["contested"] or room["asker_id"] != d.get("pid"):
        return jsonify({"error": "Unauthorized"})
    decision = d.get("decision")
    asker = next((p for p in room["players"] if p["id"] == room["asker_id"]), None)
    guesser = next((p for p in room["players"] if p["id"] == room["guesser_id"]), None)
    if asker:
        asker["score"] = max(0, asker["score"] - 5)
    if decision == "accept":
        if guesser:
            guesser["score"] += 5
        room["last_correct"] = True
        room["contested"] = False
    else:
        room["contested"] = False
        room["phase"] = "asking"
    return jsonify({"ok": True})

@app.route("/api/next", methods=["POST"])
def api_next():
    d = request.get_json(force=True)
    room = ROOMS.get(d.get("code", ""))
    if room and room["phase"] == "review" and not room["contested"]:
        room["turn_index"] += 1
        setup_turn(room)
    return jsonify({"ok": True})

@app.route("/api/state")
def api_state():
    code = request.args.get("code", "").upper()
    room = ROOMS.get(code)
    if not room:
        return jsonify({"error": "Room expired or not found"})
    asker_name = room["umpire_name"] if room["umpire_mode"] else next((p["name"] for p in room["players"] if p["id"] == room["asker_id"]), "")
    guesser_name = next((p["name"] for p in room["players"] if p["id"] == room["guesser_id"]), "")
    standings = sorted(room["players"], key=lambda p: (-p["score"], p["total_time"]))
    return jsonify({
        "code": room["code"],
        "host_id": room["host_id"],
        "umpire_mode": room["umpire_mode"],
        "umpire_name": room["umpire_name"],
        "max_players": room["max_players"],
        "q_per_player": room["q_per_player"],
        "time_limit": room["time_limit"],
        "players": room["players"],
        "phase": room["phase"],
        "round_num": room["round_num"],
        "turn_index": room["turn_index"],
        "asker_id": room["asker_id"],
        "asker_name": asker_name,
        "guesser_id": room["guesser_id"],
        "guesser_name": guesser_name,
        "question": room["question"],
        "secret_answer": room["secret_answer"] if room["phase"] == "review" else "",
        "hint": room["hint"],
        "deadline": room["deadline"],
        "now": time.time(),
        "last_guess": room["last_guess"],
        "last_correct": room["last_correct"],
        "last_time": room["last_time"],
        "contested": room["contested"],
        "standings": standings,
        "starter_prompts": STARTER_PROMPTS
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

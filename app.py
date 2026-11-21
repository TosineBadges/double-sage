import os
import time
import random
import string
from flask import Flask, request, jsonify, send_from_directory, render_template_string

app = Flask(__name__)

ROOMS = {}
ROOM_TTL_SECONDS = 7200
MAX_ROOMS = 250

def cleanup_rooms():
    now = time.time()
    expired = [code for code, r in ROOMS.items() if now - r.get("updated_at", r.get("created_at", now)) > ROOM_TTL_SECONDS]
    for code in expired:
        ROOMS.pop(code, None)
    if len(ROOMS) > MAX_ROOMS:
        oldest = sorted(ROOMS.items(), key=lambda x: x[1].get("updated_at", 0))[:len(ROOMS) - MAX_ROOMS]
        for code, _ in oldest:
            ROOMS.pop(code, None)

def make_room_code():
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(50):
        code = "".join(random.choices(chars, k=4))
        if code not in ROOMS:
            return code
    return "".join(random.choices(chars, k=4))

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Double Sage — Online Multiplayer Duel</title>
<style>
  :root {
    --bg: #070b14;
    --card: #0f172a;
    --card2: #1e293b;
    --border: #334155;
    --accent: #38bdf8;
    --gold: #f59e0b;
    --green: #10b981;
    --red: #ef4444;
    --purple: #a855f7;
    --text: #f8fafc;
    --muted: #94a3b8;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: radial-gradient(circle at top, #111c33 0%, var(--bg) 70%);
    color: var(--text);
    min-height: 100vh;
    padding-bottom: 40px;
  }
  /* Intro Splash */
  #introOverlay {
    position: fixed;
    inset: 0;
    z-index: 99990;
    background: #050811;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
    text-align: center;
  }
  #introSlideImg {
    width: 100%;
    max-width: 440px;
    max-height: 52vh;
    object-fit: contain;
    border-radius: 18px;
    border: 2px solid rgba(56, 189, 248, 0.45);
    box-shadow: 0 18px 50px rgba(0, 0, 0, 0.75);
    background: #0b1220;
    margin-bottom: 14px;
  }
  #introCaption {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 10px;
    letter-spacing: 0.4px;
  }
  .intro-bar-wrap {
    width: 100%;
    max-width: 340px;
    height: 8px;
    background: #1e293b;
    border-radius: 999px;
    overflow: hidden;
    margin-bottom: 18px;
  }
  #introBarFill {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, var(--accent), var(--gold));
    transition: width 0.1s linear;
  }
  .intro-actions {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: center;
    position: relative;
    z-index: 999999;
  }
  #introOverlay button {
    position: relative;
    z-index: 999999 !important;
    pointer-events: auto !important;
    cursor: pointer;
    border: none;
    border-radius: 999px;
    padding: 12px 22px;
    font-weight: 800;
    font-size: 0.95rem;
  }
  .btn-sound-hero {
    background: linear-gradient(135deg, var(--green), #059669);
    color: #fff;
    box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
  }
  .btn-skip-hero {
    background: var(--card2);
    color: #fff;
    border: 1.5px solid var(--accent) !important;
  }

  /* Top Audio & Brand Bar */
  .topbar {
    position: sticky;
    top: 0;
    z-index: 500;
    background: rgba(7, 11, 20, 0.94);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
    padding: 10px 14px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 900;
    font-size: 1.05rem;
    color: var(--accent);
  }
  .brand img {
    width: 30px;
    height: 30px;
    border-radius: 8px;
    object-fit: cover;
    border: 1px solid var(--accent);
  }
  .audio-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .pill-btn {
    background: var(--card2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px 11px;
    font-size: 0.78rem;
    font-weight: 700;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .pill-btn.active {
    border-color: var(--accent);
    color: var(--accent);
  }
  .pill-btn.reset-theme {
    border-color: var(--gold);
    color: var(--gold);
    display: none;
  }
  .vol-wrap {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: var(--card2);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 0.75rem;
  }
  .vol-wrap input[type="range"] {
    width: 68px;
    accent-color: var(--accent);
  }

  /* Layout */
  .container {
    max-width: 680px;
    margin: 0 auto;
    padding: 14px;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 14px;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
  }
  h2, h3 {
    margin: 0 0 10px 0;
    font-size: 1.1rem;
  }
  .sub {
    color: var(--muted);
    font-size: 0.86rem;
    margin-bottom: 12px;
    line-height: 1.4;
  }
  input[type="text"], input[type="number"], textarea, select {
    width: 100%;
    background: #090f1d;
    color: var(--text);
    border: 1.5px solid var(--border);
    border-radius: 12px;
    padding: 11px 12px;
    font-size: 0.95rem;
    margin-bottom: 10px;
    font-family: inherit;
  }
  input:focus, textarea:focus, select:focus {
    outline: none;
    border-color: var(--accent);
  }
  .btn {
    width: 100%;
    border: none;
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 0.95rem;
    font-weight: 800;
    cursor: pointer;
    margin-bottom: 8px;
    transition: transform 0.08s ease, opacity 0.15s ease;
  }
  .btn:active { transform: scale(0.98); }
  .btn-primary { background: linear-gradient(135deg, #0284c7, var(--accent)); color: #04101f; }
  .btn-green { background: linear-gradient(135deg, #059669, var(--green)); color: #fff; }
  .btn-gold { background: linear-gradient(135deg, #d97706, var(--gold)); color: #090d16; }
  .btn-red { background: linear-gradient(135deg, #dc2626, var(--red)); color: #fff; }
  .btn-purple { background: linear-gradient(135deg, #7e22ce, var(--purple)); color: #fff; }
  .btn-ghost { background: var(--card2); color: var(--text); border: 1px solid var(--border); }
  .btn-sm { width: auto; padding: 7px 12px; font-size: 0.8rem; margin-bottom: 0; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .row > * { flex: 1; }
  .badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 800;
    background: rgba(56, 189, 248, 0.15);
    color: var(--accent);
    border: 1px solid rgba(56, 189, 248, 0.35);
  }
  .badge-gold {
    background: rgba(245, 158, 11, 0.15);
    color: var(--gold);
    border-color: rgba(245, 158, 11, 0.35);
  }
  .player-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--card2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 8px;
  }
  .timer-box {
    font-size: 2rem;
    font-weight: 900;
    text-align: center;
    color: var(--gold);
    background: #090f1d;
    border: 1.5px solid var(--gold);
    border-radius: 14px;
    padding: 10px;
    margin: 10px 0;
  }
  .prompt-chip {
    background: var(--card2);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 10px;
    padding: 7px 10px;
    font-size: 0.8rem;
    cursor: pointer;
    text-align: left;
  }
  .prompt-chip:hover { border-color: var(--accent); }
  .qb-item {
    background: #090f1d;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 10px;
    margin-bottom: 8px;
  }
  .hidden { display: none !important; }
  .toast {
    position: fixed;
    bottom: 18px;
    left: 50%;
    transform: translateX(-50%);
    background: #1e293b;
    color: #fff;
    border: 1px solid var(--accent);
    padding: 10px 18px;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 700;
    z-index: 999999;
    box-shadow: 0 10px 30px rgba(0,0,0,0.6);
  }
</style>
</head>
<body>

<!-- 4-Slide 3-Second Intro Splash -->
<div id="introOverlay">
  <img id="introSlideImg" src="/media/double_sage_icon.jpg" alt="Double Sage" onerror="this.style.display='none'">
  <div id="introCaption">DOUBLE SAGE — MIND DUEL ARENA</div>
  <div class="intro-bar-wrap"><div id="introBarFill"></div></div>
  <div class="intro-actions">
    <button type="button" class="btn-sound-hero" onclick="enableLoudAudioAndNext()">🔊 Enable Loud Sound & Music</button>
    <button type="button" class="btn-skip-hero" onclick="forceCloseIntro()">Skip Intro ⏭</button>
  </div>
</div>

<!-- Sticky Top Bar -->
<div class="topbar">
  <div class="brand">
    <img src="/media/double_sage_icon.jpg" alt="Logo" onerror="this.style.display='none'">
    <span>DOUBLE SAGE</span>
  </div>
  <div class="audio-bar">
    <button type="button" id="btnMusic" class="pill-btn active" onclick="toggleMusic()">🎵 Music: ON</button>
    <button type="button" id="btnSfx" class="pill-btn active" onclick="toggleSfx()">🔊 SFX: ON</button>
    <label class="pill-btn" style="cursor:pointer;">
      📂 Load Song
      <input type="file" id="customSongInput" accept="audio/*" style="display:none;" onchange="loadLocalSong(event)">
    </label>
    <button type="button" id="resetThemeBtn" class="pill-btn reset-theme" onclick="resetToDefaultTheme()">🔄 Default Theme</button>
    <div class="vol-wrap">
      <span>🔉</span>
      <input type="range" id="volSlider" min="0" max="1" step="0.05" value="0.9" oninput="setMasterVolume(this.value)">
    </div>
    <button type="button" class="pill-btn" onclick="replayIntro()">🎬 Intro</button>
  </div>
</div>

<audio id="themeAudio" src="/media/theme.mp3" loop preload="auto"></audio>

<div class="container">

  <!-- LOBBY / WELCOME VIEW -->
  <div id="viewWelcome">
    <div class="card">
      <h2>⚔️ Enter Online Multiplayer Arena</h2>
      <p class="sub">Play across separate phones in real time! Create a 4-letter room or join a friend's invite link.</p>
      <input type="text" id="playerNameInput" placeholder="Enter your player name (e.g., SageKing)" maxlength="20">
      <div class="row">
        <button type="button" class="btn btn-primary" onclick="createRoom()">➕ Create Online Room</button>
      </div>
      <div style="margin: 10px 0; text-align:center; color:var(--muted); font-size:0.8rem;">— OR JOIN EXISTING ROOM —</div>
      <div class="row">
        <input type="text" id="joinCodeInput" placeholder="4-Letter Code" maxlength="4" style="text-transform:uppercase; margin-bottom:0;">
        <button type="button" class="btn btn-green btn-sm" style="padding:12px 18px;" onclick="joinRoom()">🚪 Join Room</button>
      </div>
    </div>

    <!-- Creator Monetization & Tournaments Hub -->
    <div class="card">
      <div class="row" style="justify-content:space-between; margin-bottom:8px;">
        <h3 style="margin:0;">🏆 Live Tournaments & Creator Hub</h3>
        <span class="badge badge-gold">Creator Tools</span>
      </div>
      <p class="sub">Pin your Paystack, Selar, or Flutterwave payment link for weekend tournament tickets or fan support tips.</p>
      <div id="creatorLinkDisplay" class="hidden" style="margin-bottom:10px;">
        <a id="creatorPayAnchor" href="#" target="_blank" rel="noopener" class="btn btn-gold" style="display:block; text-align:center; text-decoration:none;">🎟️ Buy Tournament Ticket / ☕ Support Creator</a>
      </div>
      <div class="row">
        <input type="text" id="creatorUrlInput" placeholder="https://selar.co/your-link or Paystack URL" style="margin-bottom:0;">
        <button type="button" class="btn btn-ghost btn-sm" style="padding:11px 14px;" onclick="saveCreatorLink()">💾 Save Link</button>
      </div>
    </div>

    <!-- Saved Question Banks & Pro QB Pack Unlocker -->
    <div class="card">
      <div class="row" style="justify-content:space-between; margin-bottom:8px;">
        <h3 style="margin:0;">📚 My QB's & 🎟️ Pro Pack Unlocker</h3>
        <span class="badge" id="qbCountBadge">0 Saved</span>
      </div>
      <p class="sub">Unlock curated Question Bank packs (try starter codes <b>NAIJA2026</b>, <b>FOOTYPRO</b>, <b>PARTYVIP</b>) or save your own questions so you never have to retype during a match.</p>
      <div class="row" style="margin-bottom:10px;">
        <input type="text" id="packCodeInput" placeholder="Enter Pack Code or DSPACK:..." style="margin-bottom:0;">
        <button type="button" class="btn btn-purple btn-sm" style="padding:11px 14px;" onclick="redeemPackCode()">🔓 Unlock</button>
      </div>
      <div class="row" style="margin-bottom:10px;">
        <button type="button" class="btn btn-ghost btn-sm" onclick="toggleQbDrawer()">📂 Manage My QB's</button>
        <button type="button" class="btn btn-gold btn-sm" onclick="exportSellablePack()">📤 Export Sellable Code (DSPACK)</button>
      </div>
      <div id="qbDrawer" class="hidden" style="margin-top:10px; border-top:1px solid var(--border); padding-top:10px;">
        <input type="text" id="newQbQuestion" placeholder="Question prompt (e.g., How many states are in Nigeria?)">
        <input type="text" id="newQbAnswer" placeholder="Exact Answer (e.g., 36)">
        <button type="button" class="btn btn-green btn-sm" onclick="addCustomQb()">➕ Save to My QB's</button>
        <div id="qbListContainer" style="margin-top:10px;"></div>
      </div>
    </div>
  </div>

  <!-- ACTIVE ROOM VIEW -->
  <div id="viewRoom" class="hidden">
    <div class="card">
      <div class="row" style="justify-content:space-between; margin-bottom:8px;">
        <div>
          <span class="badge" id="roomCodeBadge">ROOM: ----</span>
          <span class="badge badge-gold" id="modeBadge">Standard Mode</span>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" onclick="copyInviteLink()">🔗 Copy Invite Link</button>
      </div>

      <div id="hostSettingsBox" class="hidden" style="background:#090f1d; border:1px solid var(--border); border-radius:12px; padding:10px; margin-bottom:10px;">
        <div class="row" style="margin-bottom:8px;">
          <label style="font-size:0.82rem; color:var(--muted);">Ruling Mode:
            <select id="umpireSelect" onchange="updateSettings()" style="margin-top:4px; margin-bottom:0;">
              <option value="standard">Standard Contest & Approval</option>
              <option value="umpire">Umpire Mode (Final Ruling — No Contest)</option>
            </select>
          </label>
          <label style="font-size:0.82rem; color:var(--muted);">Target Points:
            <select id="targetPtsSelect" onchange="updateSettings()" style="margin-top:4px; margin-bottom:0;">
              <option value="15">15 Points</option>
              <option value="25" selected>25 Points</option>
              <option value="50">50 Points</option>
            </select>
          </label>
        </div>
        <button type="button" class="btn btn-green" onclick="startMatch()">🚀 Start Match</button>
      </div>

      <h3>👥 Players & Leaderboard</h3>
      <div id="playersList"></div>
      <button type="button" class="btn btn-red btn-sm" onclick="leaveRoom()">🚪 Leave Room</button>
    </div>

    <!-- GAMEPLAY STAGE -->
    <div id="gameStageCard" class="card hidden">
      <div class="row" style="justify-content:space-between; margin-bottom:6px;">
        <span class="badge" id="roundBadge">Round 1</span>
        <span class="badge badge-gold" id="roleBadge">Role</span>
      </div>
      <div id="countdownTimer" class="timer-box hidden">30s</div>
      <div id="stageContent"></div>
    </div>
  </div>

</div>

<div id="toastBox" class="toast hidden"></div>

<script>
// ==================== INTRO SPLASH ENGINE ====================
const INTRO_SLIDES = [
  { img: "/media/double_sage_icon.jpg", text: "DOUBLE SAGE — MIND DUEL ARENA" },
  { img: "/media/double_sage_battle.jpg", text: "OUTSMART • OUTGUESS • OUTPLAY" },
  { img: "/media/double_sage_banner.jpg", text: "LIVE MULTIPLAYER & PASS-AND-PLAY" },
  { img: "/media/double_sage_tournament.jpg", text: "TOURNAMENT READY — ENTER THE ARENA" }
];
let introIdx = 0;
let introProgress = 0;
window.introTimer = null;

function startIntroSequence() {
  const ov = document.getElementById("introOverlay");
  if (!ov) return;
  ov.style.display = "flex";
  introIdx = 0;
  introProgress = 0;
  renderIntroSlide();
  if (window.introTimer) clearInterval(window.introTimer);
  window.introTimer = setInterval(() => {
    introProgress += 100;
    const pct = Math.min(100, (introProgress / 3000) * 100);
    const fill = document.getElementById("introBarFill");
    if (fill) fill.style.width = pct + "%";
    if (introProgress >= 3000) {
      introProgress = 0;
      introIdx++;
      if (introIdx >= INTRO_SLIDES.length) {
        window.forceCloseIntro();
      } else {
        renderIntroSlide();
      }
    }
  }, 100);
}

function renderIntroSlide() {
  const s = INTRO_SLIDES[introIdx] || INTRO_SLIDES[0];
  const img = document.getElementById("introSlideImg");
  const cap = document.getElementById("introCaption");
  const fill = document.getElementById("introBarFill");
  if (img) {
    img.style.display = "block";
    img.src = s.img;
  }
  if (cap) cap.textContent = s.text;
  if (fill) fill.style.width = "0%";
}

window.forceCloseIntro = function() {
  if (window.introTimer) {
    clearInterval(window.introTimer);
    window.introTimer = null;
  }
  const ov = document.getElementById("introOverlay");
  if (ov) ov.style.display = "none";
  unlockAudio();
};

function replayIntro() {
  startIntroSequence();
}

function enableLoudAudioAndNext() {
  unlockAudio();
  playSfx("ding");
  showToast("🔊 Loud Sound & Music Enabled!");
}

// ==================== AUDIO & CUSTOM SONG ENGINE ====================
let audioCtx = null;
let masterGain = null;
let synthTimer = null;
let musicEnabled = true;
let sfxEnabled = true;
let masterVol = 0.9;
let usingCustomLocalSong = false;
let themeMp3Failed = false;

const themeAudio = document.getElementById("themeAudio");
themeAudio.addEventListener("error", () => {
  themeMp3Failed = true;
  if (musicEnabled && audioCtx && !synthTimer) startSynthLoop();
});

function unlockAudio() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) {
      audioCtx = new AC();
      const comp = audioCtx.createDynamicsCompressor();
      comp.threshold.value = -12;
      comp.ratio.value = 8;
      masterGain = audioCtx.createGain();
      masterGain.gain.value = masterVol;
      comp.connect(masterGain);
      masterGain.connect(audioCtx.destination);
      window._audioBus = comp;
    }
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume().catch(() => {});
  }
  if (musicEnabled) {
    themeAudio.volume = masterVol;
    if (!themeMp3Failed || usingCustomLocalSong) {
      themeAudio.play().then(() => {
        stopSynthLoop();
      }).catch(() => {
        if (!synthTimer) startSynthLoop();
      });
    } else if (!synthTimer) {
      startSynthLoop();
    }
  }
}

function startSynthLoop() {
  if (synthTimer) return;
  const notes = [130.81, 164.81, 196.00, 261.63, 196.00, 164.81, 146.83, 220.00];
  let step = 0;
  synthTimer = setInterval(() => {
    if (!musicEnabled || !audioCtx || audioCtx.state !== "running") return;
    const osc = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    osc.type = "sawtooth";
    osc.frequency.value = notes[step % notes.length];
    g.gain.setValueAtTime(0.25, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.22);
    osc.connect(g);
    g.connect(window._audioBus);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.24);
    step++;
  }, 260);
}

function stopSynthLoop() {
  if (synthTimer) {
    clearInterval(synthTimer);
    synthTimer = null;
  }
}

function toggleMusic() {
  musicEnabled = !musicEnabled;
  const btn = document.getElementById("btnMusic");
  btn.textContent = musicEnabled ? "🎵 Music: ON" : "🎵 Music: OFF";
  btn.classList.toggle("active", musicEnabled);
  if (!musicEnabled) {
    themeAudio.pause();
    stopSynthLoop();
  } else {
    unlockAudio();
  }
}

function toggleSfx() {
  sfxEnabled = !sfxEnabled;
  const btn = document.getElementById("btnSfx");
  btn.textContent = sfxEnabled ? "🔊 SFX: ON" : "🔊 SFX: OFF";
  btn.classList.toggle("active", sfxEnabled);
  if (sfxEnabled) playSfx("ding");
}

function setMasterVolume(val) {
  masterVol = parseFloat(val);
  themeAudio.volume = masterVol;
  if (masterGain && audioCtx) {
    masterGain.gain.setValueAtTime(masterVol, audioCtx.currentTime);
  }
}

function loadLocalSong(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  usingCustomLocalSong = true;
  stopSynthLoop();
  themeAudio.pause();
  themeAudio.src = url;
  themeAudio.loop = true;
  themeAudio.volume = masterVol;
  themeAudio.play().catch(() => {});
  document.getElementById("resetThemeBtn").style.display = "inline-flex";
  showToast("🎶 Loaded: " + file.name);
}

window.resetToDefaultTheme = function() {
  usingCustomLocalSong = false;
  themeMp3Failed = false;
  const inp = document.getElementById("customSongInput");
  if (inp) inp.value = "";
  themeAudio.pause();
  themeAudio.src = "/media/theme.mp3";
  themeAudio.loop = true;
  themeAudio.load();
  document.getElementById("resetThemeBtn").style.display = "none";
  if (musicEnabled) unlockAudio();
  showToast("🔄 Switched back to Default Theme");
};

function playSfx(type) {
  if (!sfxEnabled) return;
  unlockAudio();
  if (!audioCtx || !window._audioBus) return;
  const osc = audioCtx.createOscillator();
  const g = audioCtx.createGain();
  const now = audioCtx.currentTime;
  if (type === "win") {
    osc.type = "triangle";
    osc.frequency.setValueAtTime(523.25, now);
    osc.frequency.setValueAtTime(659.25, now + 0.1);
    osc.frequency.setValueAtTime(783.99, now + 0.2);
    g.gain.setValueAtTime(0.4, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
    osc.connect(g); g.connect(window._audioBus);
    osc.start(now); osc.stop(now + 0.46);
  } else if (type === "buzz") {
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(150, now);
    osc.frequency.linearRampToValueAtTime(95, now + 0.3);
    g.gain.setValueAtTime(0.35, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.32);
    osc.connect(g); g.connect(window._audioBus);
    osc.start(now); osc.stop(now + 0.34);
  } else {
    osc.type = "sine";
    osc.frequency.setValueAtTime(660, now);
    g.gain.setValueAtTime(0.3, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
    osc.connect(g); g.connect(window._audioBus);
    osc.start(now); osc.stop(now + 0.18);
  }
}

document.addEventListener("pointerdown", unlockAudio, { once: true });

// ==================== QB's & MONETIZATION PACKS ====================
const BUILTIN_PACKS = {
  "NAIJA2026": [
    { q: "What year did Nigeria gain independence?", a: "1960" },
    { q: "How many states are in Nigeria?", a: "36" },
    { q: "Which Nigerian artist won the Grammy for Best Global Music Album in 2021?", a: "Burna Boy" },
    { q: "What is the capital city of Ogun State?", a: "Abeokuta" },
    { q: "What is the highest mountain peak in Nigeria?", a: "Chappal Waddi" }
  ],
  "FOOTYPRO": [
    { q: "How many World Cup titles has Brazil won?", a: "5" },
    { q: "Which club has won the most UEFA Champions League trophies?", a: "Real Madrid" },
    { q: "In what year did Nigeria win the Olympic football gold medal?", a: "1996" },
    { q: "How many players are on the pitch for one football team?", a: "11" }
  ],
  "PARTYVIP": [
    { q: "How many continents are on Earth?", a: "7" },
    { q: "What is the chemical symbol for Gold?", a: "Au" },
    { q: "How many hours are in 3 full days?", a: "72" },
    { q: "Which planet is closest to the Sun?", a: "Mercury" }
  ]
};

let savedQbs = JSON.parse(localStorage.getItem("ds_saved_qbs") || "[]");
let qbCursor = 0;

function persistQbs() {
  localStorage.setItem("ds_saved_qbs", JSON.stringify(savedQbs));
  document.getElementById("qbCountBadge").textContent = savedQbs.length + " Saved";
  renderQbList();
}

function toggleQbDrawer() {
  document.getElementById("qbDrawer").classList.toggle("hidden");
  renderQbList();
}

function addCustomQb() {
  const q = document.getElementById("newQbQuestion").value.trim();
  const a = document.getElementById("newQbAnswer").value.trim();
  if (!q || !a) return showToast("Enter both a question and an answer.");
  savedQbs.push({ q, a });
  document.getElementById("newQbQuestion").value = "";
  document.getElementById("newQbAnswer").value = "";
  persistQbs();
  playSfx("ding");
  showToast("✅ Saved to My QB's!");
}

function deleteQb(idx) {
  savedQbs.splice(idx, 1);
  persistQbs();
}

function renderQbList() {
  const box = document.getElementById("qbListContainer");
  if (!box) return;
  if (savedQbs.length === 0) {
    box.innerHTML = '<div class="sub">No saved questions yet. Add one above or unlock a Pro Pack!</div>';
    return;
  }
  box.innerHTML = savedQbs.map((item, i) => `
    <div class="qb-item">
      <div style="font-weight:700; font-size:0.88rem;">Q: ${escapeHtml(item.q)}</div>
      <div style="color:var(--green); font-size:0.82rem; margin:4px 0;">A: ${escapeHtml(item.a)}</div>
      <button type="button" class="btn btn-red btn-sm" onclick="deleteQb(${i})">🗑 Remove</button>
    </div>
  `).join("");
}

function redeemPackCode() {
  const raw = document.getElementById("packCodeInput").value.trim();
  if (!raw) return showToast("Enter a Pack Code first.");
  const upper = raw.toUpperCase();
  if (BUILTIN_PACKS[upper]) {
    savedQbs = savedQbs.concat(BUILTIN_PACKS[upper]);
    document.getElementById("packCodeInput").value = "";
    persistQbs();
    playSfx("win");
    return showToast("🎉 Unlocked " + BUILTIN_PACKS[upper].length + " Pro Questions!");
  }
  if (raw.startsWith("DSPACK:")) {
    try {
      const decoded = JSON.parse(decodeURIComponent(escape(atob(raw.slice(7)))));
      if (Array.isArray(decoded) && decoded.length > 0) {
        savedQbs = savedQbs.concat(decoded);
        document.getElementById("packCodeInput").value = "";
        persistQbs();
        playSfx("win");
        return showToast("🎉 Imported " + decoded.length + " Questions!");
      }
    } catch (err) {}
  }
  playSfx("buzz");
  showToast("❌ Invalid Pack Code.");
}

function exportSellablePack() {
  if (savedQbs.length === 0) return showToast("Add questions to My QB's first!");
  const code = "DSPACK:" + btoa(unescape(encodeURIComponent(JSON.stringify(savedQbs))));
  navigator.clipboard?.writeText(code).catch(() => {});
  prompt("Copy this sellable DSPACK code for your buyers on Selar/Paystack:", code);
}

// Creator Payment Link
function saveCreatorLink() {
  const url = document.getElementById("creatorUrlInput").value.trim();
  if (!url) {
    localStorage.removeItem("ds_creator_link");
    document.getElementById("creatorLinkDisplay").classList.add("hidden");
    return showToast("Creator link cleared.");
  }
  localStorage.setItem("ds_creator_link", url);
  applyCreatorLink();
  showToast("🏆 Creator Payment Link Saved!");
}

function applyCreatorLink() {
  const url = localStorage.getItem("ds_creator_link");
  if (url) {
    document.getElementById("creatorUrlInput").value = url;
    document.getElementById("creatorPayAnchor").href = url;
    document.getElementById("creatorLinkDisplay").classList.remove("hidden");
  }
}

// ==================== MULTIPLAYER ROOM CLIENT ====================
let pid = localStorage.getItem("ds_pid") || ("p_" + Math.random().toString(36).slice(2, 10));
localStorage.setItem("ds_pid", pid);
let roomCode = "";
let pollTimer = null;
let lastRenderedSignature = "";

const STARTER_PROMPTS = [
  "How many days are in a leap year?",
  "What is the capital of France?",
  "How many continents are there on Earth?",
  "What is 15 multiplied by 4?"
];

async function api(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return res.json();
}

async function createRoom() {
  const name = document.getElementById("playerNameInput").value.trim() || "Host";
  localStorage.setItem("ds_name", name);
  const data = await api("/api/create", { pid, name });
  if (data.error) return showToast(data.error);
  enterRoomView(data.code);
}

async function joinRoom(overrideCode) {
  const code = (overrideCode || document.getElementById("joinCodeInput").value).trim().toUpperCase();
  const name = document.getElementById("playerNameInput").value.trim() || ("Player_" + pid.slice(-3));
  if (code.length !== 4) return showToast("Enter a 4-letter room code.");
  localStorage.setItem("ds_name", name);
  const data = await api("/api/join", { pid, name, code });
  if (data.error) return showToast(data.error);
  enterRoomView(code);
}

function enterRoomView(code) {
  roomCode = code;
  lastRenderedSignature = "";
  document.getElementById("viewWelcome").classList.add("hidden");
  document.getElementById("viewRoom").classList.remove("hidden");
  document.getElementById("roomCodeBadge").textContent = "ROOM: " + code;
  if (pollTimer) clearInterval(pollTimer);
  pollState();
  pollTimer = setInterval(pollState, 1500);
}

async function leaveRoom() {
  if (roomCode) {
    await api("/api/action", { code: roomCode, pid, action: "leave" }).catch(() => {});
  }
  if (pollTimer) clearInterval(pollTimer);
  roomCode = "";
  document.getElementById("viewRoom").classList.add("hidden");
  document.getElementById("viewWelcome").classList.remove("hidden");
}

function copyInviteLink() {
  const url = window.location.origin + "/?room=" + roomCode;
  navigator.clipboard?.writeText(url).catch(() => {});
  showToast("🔗 Invite link copied: " + url);
}

async function updateSettings() {
  const umpire = document.getElementById("umpireSelect").value === "umpire";
  const target = parseInt(document.getElementById("targetPtsSelect").value, 10) || 25;
  await api("/api/action", { code: roomCode, pid, action: "settings", umpire, target });
}

async function startMatch() {
  playSfx("win");
  await api("/api/action", { code: roomCode, pid, action: "start" });
  pollState();
}

async function kickPlayer(targetPid) {
  await api("/api/action", { code: roomCode, pid, action: "kick", target_pid: targetPid });
  pollState();
}

async function pollState() {
  if (!roomCode) return;
  try {
    const res = await fetch(`/api/state?code=${encodeURIComponent(roomCode)}&pid=${encodeURIComponent(pid)}`);
    const state = await res.json();
    if (state.error) {
      showToast(state.error);
      leaveRoom();
      return;
    }
    renderRoomState(state);
  } catch (e) {}
}

function renderRoomState(state) {
  const isHost = state.host_pid === pid;
  document.getElementById("modeBadge").textContent = state.umpire ? "⚖️ Umpire Mode" : "🛡️ Standard Contest Mode";
  document.getElementById("hostSettingsBox").classList.toggle("hidden", !(isHost && state.phase === "lobby"));

  // Leaderboard
  const plist = document.getElementById("playersList");
  plist.innerHTML = state.players.map(p => `
    <div class="player-item">
      <div>
        <strong>${escapeHtml(p.name)}</strong>
        ${p.pid === state.host_pid ? '<span class="badge" style="margin-left:6px;">HOST</span>' : ''}
        ${p.pid === state.manager_pid ? '<span class="badge badge-gold" style="margin-left:6px;">MANAGER</span>' : ''}
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <strong style="color:var(--green);">${p.score} pts</strong>
        ${(isHost && p.pid !== pid) ? `<button type="button" class="btn btn-red btn-sm" onclick="kickPlayer('${p.pid}')">Kick</button>` : ''}
      </div>
    </div>
  `).join("");

  const stageCard = document.getElementById("gameStageCard");
  if (state.phase === "lobby") {
    stageCard.classList.add("hidden");
    return;
  }
  stageCard.classList.remove("hidden");
  document.getElementById("roundBadge").textContent = `Round ${state.round} • Target ${state.target} pts`;

  const isManager = state.manager_pid === pid;
  document.getElementById("roleBadge").textContent = isManager ? "🧠 You are the Manager" : "🎯 Guesser";

  // Timer update without rebuilding inputs
  const timerBox = document.getElementById("countdownTimer");
  if (state.phase === "guessing" && state.deadline) {
    const rem = Math.max(0, Math.ceil(state.deadline - state.server_time));
    timerBox.classList.remove("hidden");
    timerBox.textContent = rem + "s remaining";
  } else {
    timerBox.classList.add("hidden");
  }

  // Prevent polling from overwriting user typing in inputs
  const sig = JSON.stringify({
    phase: state.phase,
    round: state.round,
    manager: state.manager_pid,
    question: state.question,
    guessesCount: (state.guesses || []).length,
    contested: state.contested,
    winner: state.winner
  });
  if (sig === lastRenderedSignature) return;
  lastRenderedSignature = sig;

  const box = document.getElementById("stageContent");

  if (state.phase === "asking") {
    if (isManager) {
      box.innerHTML = `
        <p class="sub">Write your question and exact secret answer, pick a starter prompt, or load from <b>My QB's</b>:</p>
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px;">
          ${STARTER_PROMPTS.map(pr => `<button type="button" class="prompt-chip" onclick="usePrompt('${escapeAttr(pr)}')">${escapeHtml(pr)}</button>`).join("")}
          ${savedQbs.length > 0 ? `<button type="button" class="prompt-chip" style="border-color:var(--gold); color:var(--gold);" onclick="loadNextSavedQb()">⚡ Next QB (${savedQbs.length})</button>` : ''}
        </div>
        <input type="text" id="askQuestionInput" placeholder="Type your question here...">
        <input type="text" id="askAnswerInput" placeholder="Type the exact answer here...">
        <button type="button" class="btn btn-primary" onclick="submitQuestion()">📨 Send Question to Arena</button>
      `;
    } else {
      box.innerHTML = `<p class="sub">⏳ Waiting for the <b>Manager</b> to send the round question...</p>`;
    }
  } else if (state.phase === "guessing") {
    const alreadyGuessed = (state.guesses || []).some(g => g.pid === pid);
    const ansIsDigits = /^\d+$/.test((state.answer || "").trim());
    const hintLine = (isManager && ansIsDigits)
      ? `<div class="badge badge-gold" style="margin-bottom:8px;">Manager Digit Hint: Answer has ${(state.answer || "").trim().length} digits</div>`
      : "";

    if (isManager) {
      box.innerHTML = `
        <div style="font-weight:800; font-size:1.05rem; margin-bottom:6px;">Q: ${escapeHtml(state.question)}</div>
        <div style="color:var(--green); font-size:0.88rem; margin-bottom:8px;">Secret Answer: <b>${escapeHtml(state.answer)}</b></div>
        ${hintLine}
        <p class="sub">Guesses submitted so far: <b>${(state.guesses || []).length}</b></p>
        <button type="button" class="btn btn-gold" onclick="closeGuessing()">⏹ Close Guesses & Review</button>
      `;
    } else if (alreadyGuessed) {
      box.innerHTML = `
        <div style="font-weight:800; font-size:1.05rem; margin-bottom:8px;">Q: ${escapeHtml(state.question)}</div>
        <p class="sub">✅ Your guess is locked in! Waiting for other players...</p>
      `;
    } else {
      box.innerHTML = `
        <div style="font-weight:800; font-size:1.05rem; margin-bottom:10px;">Q: ${escapeHtml(state.question)}</div>
        <input type="text" id="guessInput" placeholder="Type your guess quickly (speed breaks ties!)...">
        <button type="button" class="btn btn-green" onclick="submitGuess()">⚡ Lock In Guess</button>
      `;
    }
  } else if (state.phase === "review") {
    const guessesHtml = (state.guesses || []).map(g => `
      <div class="player-item">
        <div>
          <strong>${escapeHtml(g.name)}</strong>: <span style="color:var(--accent);">${escapeHtml(g.guess)}</span>
          <div style="font-size:0.75rem; color:var(--muted);">Time: ${g.elapsed}s</div>
        </div>
        ${isManager ? `<button type="button" class="btn btn-green btn-sm" onclick="awardWinner('${g.pid}')">✅ Accept (+5 Pts)</button>` : ''}
      </div>
    `).join("") || '<p class="sub">No guesses were submitted this round.</p>';

    box.innerHTML = `
      <div style="font-weight:800; margin-bottom:4px;">Q: ${escapeHtml(state.question)}</div>
      <div style="color:var(--green); margin-bottom:10px;">Official Answer: <b>${escapeHtml(state.answer)}</b></div>
      ${guessesHtml}
      ${isManager ? `
        <div class="row" style="margin-top:10px;">
          <button type="button" class="btn btn-gold btn-sm" onclick="reAskNewQuestion()">🔄 Send New Question (0 Pts & Re-Ask)</button>
          <button type="button" class="btn btn-ghost btn-sm" onclick="nextRound()">⏭ No Winner — Next Turn</button>
        </div>
      ` : (!state.umpire ? `
        <button type="button" class="btn btn-red btn-sm" style="margin-top:8px;" onclick="contestRound()">🚩 Contest Ruling</button>
      ` : '')}
      ${state.contested ? `<div class="badge badge-gold" style="margin-top:8px;">⚠️ A player contested this ruling! Manager can Accept Guess (+5 Pts) or Send New Question.</div>` : ''}
    `;
  } else if (state.phase === "gameover") {
    box.innerHTML = `
      <h2 style="color:var(--gold); text-align:center;">🏆 CHAMPION: ${escapeHtml(state.winner || "Winner")}!</h2>
      <p class="sub" style="text-align:center;">Target score reached! Ready for a rematch?</p>
      ${isHost ? `<button type="button" class="btn btn-primary" onclick="startMatch()">🔁 Play Rematch</button>` : ''}
    `;
  }
}

function usePrompt(txt) {
  const inp = document.getElementById("askQuestionInput");
  if (inp) inp.value = txt;
}

function loadNextSavedQb() {
  if (savedQbs.length === 0) return;
  const item = savedQbs[qbCursor % savedQbs.length];
  qbCursor++;
  const qInp = document.getElementById("askQuestionInput");
  const aInp = document.getElementById("askAnswerInput");
  if (qInp) qInp.value = item.q;
  if (aInp) aInp.value = item.a;
  playSfx("ding");
}

async function submitQuestion() {
  const q = document.getElementById("askQuestionInput").value.trim();
  const a = document.getElementById("askAnswerInput").value.trim();
  if (!q || !a) return showToast("Enter both a question and an answer.");
  playSfx("ding");
  await api("/api/action", { code: roomCode, pid, action: "ask", question: q, answer: a });
  pollState();
}

async function submitGuess() {
  const g = document.getElementById("guessInput").value.trim();
  if (!g) return showToast("Type your guess first!");
  playSfx("ding");
  await api("/api/action", { code: roomCode, pid, action: "guess", guess: g });
  pollState();
}

async function closeGuessing() {
  await api("/api/action", { code: roomCode, pid, action: "close_guesses" });
  pollState();
}

async function awardWinner(winnerPid) {
  playSfx("win");
  await api("/api/action", { code: roomCode, pid, action: "award", winner_pid: winnerPid });
  pollState();
}

async function reAskNewQuestion() {
  await api("/api/action", { code: roomCode, pid, action: "reask" });
  pollState();
}

async function nextRound() {
  await api("/api/action", { code: roomCode, pid, action: "next_round" });
  pollState();
}

async function contestRound() {
  playSfx("buzz");
  await api("/api/action", { code: roomCode, pid, action: "contest" });
  pollState();
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}
function escapeAttr(s) {
  return String(s || "").replace(/'/g, "\'");
}

let toastTimeout = null;
function showToast(msg) {
  const t = document.getElementById("toastBox");
  t.textContent = msg;
  t.classList.remove("hidden");
  if (toastTimeout) clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => t.classList.add("hidden"), 2800);
}

// Init on load
window.addEventListener("DOMContentLoaded", () => {
  const savedName = localStorage.getItem("ds_name");
  if (savedName) document.getElementById("playerNameInput").value = savedName;
  applyCreatorLink();
  persistQbs();
  startIntroSequence();

  const params = new URLSearchParams(window.location.search);
  const autoRoom = params.get("room");
  if (autoRoom) {
    document.getElementById("joinCodeInput").value = autoRoom.toUpperCase();
  }
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/media/<path:filename>")
def serve_media(filename):
    return send_from_directory(".", filename)

@app.route("/health")
def health():
    cleanup_rooms()
    return jsonify({"status": "ok", "rooms": len(ROOMS)})

@app.route("/api/create", methods=["POST"])
def api_create():
    cleanup_rooms()
    data = request.get_json(silent=True) or {}
    pid = str(data.get("pid", "")).strip()
    name = str(data.get("name", "Host")).strip()[:20] or "Host"
    if not pid:
        return jsonify({"error": "Missing player ID"}), 400
    code = make_room_code()
    now = time.time()
    ROOMS[code] = {
        "code": code,
        "host_pid": pid,
        "manager_idx": 0,
        "players": [{"pid": pid, "name": name, "score": 0}],
        "umpire": False,
        "target": 25,
        "phase": "lobby",
        "round": 1,
        "question": "",
        "answer": "",
        "asked_at": 0,
        "deadline": 0,
        "guesses": [],
        "contested": False,
        "winner": "",
        "created_at": now,
        "updated_at": now
    }
    return jsonify({"code": code})

@app.route("/api/join", methods=["POST"])
def api_join():
    cleanup_rooms()
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip().upper()
    pid = str(data.get("pid", "")).strip()
    name = str(data.get("name", "Player")).strip()[:20] or "Player"
    room = ROOMS.get(code)
    if not room:
        return jsonify({"error": "Room not found. Check the 4-letter code."}), 404
    room["updated_at"] = time.time()
    existing = next((p for p in room["players"] if p["pid"] == pid), None)
    if existing:
        existing["name"] = name
    else:
        room["players"].append({"pid": pid, "name": name, "score": 0})
    return jsonify({"ok": True, "code": code})

@app.route("/api/state")
def api_state():
    code = str(request.args.get("code", "")).strip().upper()
    pid = str(request.args.get("pid", "")).strip()
    room = ROOMS.get(code)
    if not room:
        return jsonify({"error": "Room closed or expired."}), 404
    if not any(p["pid"] == pid for p in room["players"]):
        return jsonify({"error": "You are no longer in this room."}), 403

    now = time.time()
    if room["phase"] == "guessing" and room["deadline"] and now >= room["deadline"]:
        room["phase"] = "review"
        room["updated_at"] = now

    players = room["players"]
    mgr_idx = room["manager_idx"] % len(players) if players else 0
    manager_pid = players[mgr_idx]["pid"] if players else ""

    return jsonify({
        "code": room["code"],
        "host_pid": room["host_pid"],
        "manager_pid": manager_pid,
        "players": players,
        "umpire": room["umpire"],
        "target": room["target"],
        "phase": room["phase"],
        "round": room["round"],
        "question": room["question"],
        "answer": room["answer"] if (pid == manager_pid or room["phase"] == "review") else "",
        "deadline": room["deadline"],
        "server_time": now,
        "guesses": room["guesses"],
        "contested": room["contested"],
        "winner": room["winner"]
    })

@app.route("/api/action", methods=["POST"])
def api_action():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip().upper()
    pid = str(data.get("pid", "")).strip()
    action = str(data.get("action", "")).strip()
    room = ROOMS.get(code)
    if not room:
        return jsonify({"error": "Room not found"}), 404

    now = time.time()
    room["updated_at"] = now
    players = room["players"]
    if not players:
        return jsonify({"error": "Empty room"}), 400

    mgr_idx = room["manager_idx"] % len(players)
    manager_pid = players[mgr_idx]["pid"]
    is_host = (pid == room["host_pid"])
    is_mgr = (pid == manager_pid)

    if action == "leave":
        room["players"] = [p for p in players if p["pid"] != pid]
        if not room["players"]:
            ROOMS.pop(code, None)
        elif room["host_pid"] == pid:
            room["host_pid"] = room["players"][0]["pid"]
        return jsonify({"ok": True})

    if action == "kick" and is_host:
        target = str(data.get("target_pid", ""))
        room["players"] = [p for p in players if p["pid"] != target]
        return jsonify({"ok": True})

    if action == "settings" and is_host:
        room["umpire"] = bool(data.get("umpire", False))
        room["target"] = int(data.get("target", 25))
        return jsonify({"ok": True})

    if action == "start" and is_host:
        for p in players:
            p["score"] = 0
        room["round"] = 1
        room["manager_idx"] = 0
        room["phase"] = "asking"
        room["question"] = ""
        room["answer"] = ""
        room["guesses"] = []
        room["contested"] = False
        room["winner"] = ""
        return jsonify({"ok": True})

    if action == "ask" and is_mgr:
        room["question"] = str(data.get("question", "")).strip()[:240]
        room["answer"] = str(data.get("answer", "")).strip()[:120]
        room["guesses"] = []
        room["contested"] = False
        room["asked_at"] = now
        room["deadline"] = now + 30
        room["phase"] = "guessing"
        return jsonify({"ok": True})

    if action == "guess" and room["phase"] == "guessing" and not is_mgr:
        if not any(g["pid"] == pid for g in room["guesses"]):
            player = next((p for p in players if p["pid"] == pid), None)
            if player:
                elapsed = round(max(0.1, now - room["asked_at"]), 2)
                room["guesses"].append({
                    "pid": pid,
                    "name": player["name"],
                    "guess": str(data.get("guess", "")).strip()[:120],
                    "elapsed": elapsed
                })
                room["guesses"].sort(key=lambda x: x["elapsed"])
        non_mgr_count = max(1, len(players) - 1)
        if len(room["guesses"]) >= non_mgr_count:
            room["phase"] = "review"
        return jsonify({"ok": True})

    if action == "close_guesses" and is_mgr:
        room["phase"] = "review"
        return jsonify({"ok": True})

    if action == "contest" and not is_mgr and not room["umpire"]:
        room["contested"] = True
        return jsonify({"ok": True})

    if action == "reask" and is_mgr:
        room["phase"] = "asking"
        room["question"] = ""
        room["answer"] = ""
        room["guesses"] = []
        room["contested"] = False
        return jsonify({"ok": True})

    if action == "award" and is_mgr:
        winner_pid = str(data.get("winner_pid", ""))
        target_player = next((p for p in players if p["pid"] == winner_pid), None)
        if target_player:
            target_player["score"] += 5
            if target_player["score"] >= room["target"]:
                room["winner"] = target_player["name"]
                room["phase"] = "gameover"
                return jsonify({"ok": True})
        room["round"] += 1
        room["manager_idx"] = (room["manager_idx"] + 1) % len(players)
        room["phase"] = "asking"
        room["question"] = ""
        room["answer"] = ""
        room["guesses"] = []
        room["contested"] = False
        return jsonify({"ok": True})

    if action == "next_round" and is_mgr:
        room["round"] += 1
        room["manager_idx"] = (room["manager_idx"] + 1) % len(players)
        room["phase"] = "asking"
        room["question"] = ""
        room["answer"] = ""
        room["guesses"] = []
        room["contested"] = False
        return jsonify({"ok": True})

    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

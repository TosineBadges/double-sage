import os
import time
import random
import string
import threading
from flask import Flask, request, jsonify, render_template_string, send_from_directory

app = Flask(__name__)

# Render Free-Tier Memory Guard
ROOMS = {}
ROOMS_LOCK = threading.Lock()
ROOM_TTL = 7200  # 2 hours
MAX_ROOMS = 250


def cleanup_rooms():
    now = time.time()
    with ROOMS_LOCK:
        expired = [c for c, r in ROOMS.items() if now - r.get("updated_at", now) > ROOM_TTL]
        for c in expired:
            del ROOMS[c]
        if len(ROOMS) > MAX_ROOMS:
            oldest = sorted(ROOMS.items(), key=lambda x: x[1].get("updated_at", 0))[: len(ROOMS) - MAX_ROOMS]
            for c, _ in oldest:
                del ROOMS[c]


def make_code():
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(50):
        code = "".join(random.choice(chars) for _ in range(4))
        if code not in ROOMS:
            return code
    return "".join(random.choice(chars) for _ in range(5))


def build_hint(answer: str) -> str:
    ans = (answer or "").strip()
    if not ans:
        return ""
    words = [w for w in ans.split() if w]
    letters = sum(1 for ch in ans if ch.isalpha())
    digits = sum(1 for ch in ans if ch.isdigit())
    parts = []
    if letters > 0:
        parts.append(f"{len(words)} {'word' if len(words) == 1 else 'words'}")
        parts.append(f"{letters} {'letter' if letters == 1 else 'letters'}")
    if digits > 0:
        parts.append(f"{digits} {'digit' if digits == 1 else 'digits'}")
    if not parts:
        parts.append(f"{len(words)} {'word' if len(words) == 1 else 'words'}")
    return ", ".join(parts)


@app.route("/media/<path:filename>")
def serve_media(filename):
    for folder in [".", "static", "assets", "media"]:
        path = os.path.join(folder, filename)
        if os.path.isfile(path):
            return send_from_directory(folder, filename)
    return ("Not found", 404)


@app.route("/api/room/create", methods=["POST"])
def create_room():
    cleanup_rooms()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "Host").strip()[:24]
    mode = data.get("mode") or "standard"
    rounds = max(1, min(30, int(data.get("rounds") or 5)))
    timer_sec = max(10, min(180, int(data.get("timer") or 30)))
    pid = "p_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    with ROOMS_LOCK:
        code = make_code()
        ROOMS[code] = {
            "code": code,
            "host_id": pid,
            "mode": mode,
            "total_rounds": rounds,
            "timer_sec": timer_sec,
            "phase": "lobby",
            "round": 1,
            "setter_idx": 0,
            "players": [
                {"id": pid, "name": name, "score": 0, "total_time": 0.0}
            ],
            "question": "",
            "answer": "",
            "hint": "",
            "guess": "",
            "guess_time": 0.0,
            "ruling": None,
            "contested": False,
            "winner_awarded": None,
            "updated_at": time.time(),
        }
    return jsonify({"ok": True, "code": code, "player_id": pid, "room": sanitize_room(ROOMS[code], pid)})


@app.route("/api/room/join", methods=["POST"])
def join_room():
    cleanup_rooms()
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "Player").strip()[:24]
    with ROOMS_LOCK:
        room = ROOMS.get(code)
        if not room:
            return jsonify({"ok": False, "error": "Room not found."}), 404
        if len(room["players"]) >= 12:
            return jsonify({"ok": False, "error": "Room is full."}), 400
        pid = "p_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        room["players"].append({"id": pid, "name": name, "score": 0, "total_time": 0.0})
        room["updated_at"] = time.time()
        return jsonify({"ok": True, "code": code, "player_id": pid, "room": sanitize_room(room, pid)})


@app.route("/api/room/state", methods=["GET"])
def room_state():
    code = (request.args.get("code") or "").strip().upper()
    pid = request.args.get("pid") or ""
    with ROOMS_LOCK:
        room = ROOMS.get(code)
        if not room:
            return jsonify({"ok": False, "error": "Room expired or not found."}), 404
        if not any(p["id"] == pid for p in room["players"]):
            return jsonify({"ok": False, "kicked": True, "error": "You were removed from the room."}), 403
        return jsonify({"ok": True, "room": sanitize_room(room, pid)})


@app.route("/api/room/action", methods=["POST"])
def room_action():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    pid = data.get("pid") or ""
    action = data.get("action") or ""
    with ROOMS_LOCK:
        room = ROOMS.get(code)
        if not room:
            return jsonify({"ok": False, "error": "Room not found."}), 404
        players = room["players"]
        if not any(p["id"] == pid for p in players):
            return jsonify({"ok": False, "error": "Not in room."}), 403
        setter = players[room["setter_idx"] % len(players)]
        guesser = players[(room["setter_idx"] + 1) % len(players)] if len(players) > 1 else setter

        if action == "kick" and pid == room["host_id"]:
            target = data.get("target_id")
            if target and target != pid:
                room["players"] = [p for p in players if p["id"] != target]
        elif action == "start" and pid == room["host_id"]:
            if len(players) < 2:
                return jsonify({"ok": False, "error": "Need at least 2 players."}), 400
            for p in players:
                p["score"] = 0
                p["total_time"] = 0.0
            room["round"] = 1
            room["setter_idx"] = 0
            room["phase"] = "set_question"
            room["question"] = ""
            room["answer"] = ""
            room["hint"] = ""
            room["guess"] = ""
            room["ruling"] = None
            room["contested"] = False
            room["winner_awarded"] = None
        elif action == "set_question" and pid == setter["id"]:
            q = (data.get("question") or "").strip()
            a = (data.get("answer") or "").strip()
            if not q or not a:
                return jsonify({"ok": False, "error": "Question and answer required."}), 400
            room["question"] = q
            room["answer"] = a
            room["hint"] = build_hint(a)
            room["guess"] = ""
            room["ruling"] = None
            room["contested"] = False
            room["winner_awarded"] = None
            room["phase"] = "guessing"
        elif action == "submit_guess" and pid == guesser["id"] and room["phase"] == "guessing":
            g = (data.get("guess") or "").strip()
            elapsed = max(0.0, float(data.get("elapsed") or 0.0))
            room["guess"] = g
            room["guess_time"] = round(elapsed, 2)
            guesser["total_time"] = round(guesser["total_time"] + elapsed, 2)
            if room["mode"] == "umpire":
                room["phase"] = "umpire_review"
            else:
                matched = g.lower() == room["answer"].strip().lower()
                if matched:
                    guesser["score"] += 5
                    room["winner_awarded"] = "guesser"
                    room["ruling"] = "Guesser matched the answer! (+5 pts)"
                else:
                    setter["score"] += 5
                    room["winner_awarded"] = "setter"
                    room["ruling"] = "Did not match exact answer — Setter awarded +5 pts."
                room["phase"] = "review"
        elif action == "contest" and pid == guesser["id"] and room["phase"] == "review" and room["mode"] != "umpire":
            if room["winner_awarded"] == "setter" and not room["contested"]:
                room["contested"] = True
                room["phase"] = "contested"
        elif action == "resolve_contest" and pid == setter["id"] and room["phase"] == "contested":
            accept = bool(data.get("accept"))
            if accept and room["winner_awarded"] == "setter":
                setter["score"] = max(0, setter["score"] - 5)
                guesser["score"] += 5
                room["winner_awarded"] = "guesser"
                room["ruling"] = "Setter accepted contest! +5 pts transferred to Guesser."
            else:
                room["ruling"] = "Setter rejected contest — Setter keeps +5 pts."
            room["phase"] = "review"
        elif action == "umpire_rule" and pid == room["host_id"] and room["phase"] == "umpire_review":
            winner = data.get("winner")
            if winner == "guesser":
                guesser["score"] += 5
                room["winner_awarded"] = "guesser"
                room["ruling"] = "Umpire final ruling: Guesser wins +5 pts."
            else:
                setter["score"] += 5
                room["winner_awarded"] = "setter"
                room["ruling"] = "Umpire final ruling: Setter wins +5 pts."
            room["phase"] = "review"
        elif action == "next_round" and pid in (room["host_id"], setter["id"]) and room["phase"] == "review":
            if room["round"] >= room["total_rounds"]:
                room["phase"] = "gameover"
            else:
                room["round"] += 1
                room["setter_idx"] = (room["setter_idx"] + 1) % len(players)
                room["phase"] = "set_question"
                room["question"] = ""
                room["answer"] = ""
                room["hint"] = ""
                room["guess"] = ""
                room["ruling"] = None
                room["contested"] = False
                room["winner_awarded"] = None
        room["updated_at"] = time.time()
        return jsonify({"ok": True, "room": sanitize_room(room, pid)})


def sanitize_room(room, pid):
    players = room["players"]
    setter = players[room["setter_idx"] % len(players)] if players else None
    guesser = players[(room["setter_idx"] + 1) % len(players)] if len(players) > 1 else setter
    reveal_ans = (
        room["phase"] in ("review", "contested", "umpire_review", "gameover")
        or (setter and pid == setter["id"])
        or (room["mode"] == "umpire" and pid == room["host_id"])
    )
    return {
        "code": room["code"],
        "host_id": room["host_id"],
        "mode": room["mode"],
        "total_rounds": room["total_rounds"],
        "timer_sec": room["timer_sec"],
        "phase": room["phase"],
        "round": room["round"],
        "players": players,
        "setter_id": setter["id"] if setter else "",
        "setter_name": setter["name"] if setter else "",
        "guesser_id": guesser["id"] if guesser else "",
        "guesser_name": guesser["name"] if guesser else "",
        "question": room["question"],
        "answer": room["answer"] if reveal_ans else "",
        "hint": room["hint"],
        "guess": room["guess"],
        "guess_time": room["guess_time"],
        "ruling": room["ruling"],
        "contested": room["contested"],
        "winner_awarded": room["winner_awarded"],
    }


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Double Sage — Online Multiplayer</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
body{background:#070b14;color:#f1f5f9;min-height:100vh;padding:14px}
.wrap{max-width:720px;margin:0 auto}
.topbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;justify-content:space-between;background:#0f172a;border:1px solid #1e293b;padding:10px 12px;border-radius:14px;margin-bottom:14px}
.brand{font-weight:800;font-size:18px;color:#38bdf8}
.btn{background:#1e293b;color:#f8fafc;border:1px solid #334155;padding:7px 12px;border-radius:10px;font-size:13px;font-weight:600;cursor:pointer}
.btn-primary{background:linear-gradient(135deg,#0284c7,#2563eb);border:none;color:#fff}
.btn-green{background:#16a34a;border:none;color:#fff}
.btn-red{background:#dc2626;border:none;color:#fff}
.btn-amber{background:#d97706;border:none;color:#fff}
.card{background:#0f172a;border:1px solid #1e293b;border-radius:16px;padding:16px;margin-bottom:14px}
h2{font-size:17px;margin-bottom:10px;color:#38bdf8}
input,select,textarea{width:100%;background:#020617;color:#f8fafc;border:1px solid #334155;border-radius:10px;padding:10px;font-size:14px;margin-bottom:10px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.pill{display:inline-block;background:#1e293b;color:#38bdf8;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700}
.hint-box{background:#0c4a6e;border:1px solid #0284c7;color:#e0f2fe;padding:10px 12px;border-radius:10px;font-weight:700;margin:8px 0}
#introOverlay{position:fixed;inset:0;z-index:99990;background:#070b14;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;text-align:center}
#introImg{max-width:340px;width:85%;max-height:52vh;object-fit:contain;border-radius:18px;border:2px solid #38bdf8;margin-bottom:16px}
.skip-btn{position:relative;z-index:999999 !important;pointer-events:auto !important;background:#ef4444;color:#fff;border:none;padding:11px 20px;border-radius:999px;font-weight:800;font-size:15px;cursor:pointer}
.player-item{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:#020617;border-radius:10px;margin-bottom:6px}
.modal{display:none;position:fixed;inset:0;z-index:9990;background:rgba(2,6,23,.88);padding:16px;overflow-y:auto}
.modal-inner{max-width:600px;margin:20px auto;background:#0f172a;border:1px solid #334155;border-radius:16px;padding:16px}
</style>
</head>
<body>

<div id="introOverlay">
  <img id="introImg" src="/media/double_sage_icon.jpg" alt="Double Sage">
  <div id="introCaption" style="font-size:18px;font-weight:800;color:#38bdf8;margin-bottom:14px">DOUBLE SAGE ARENA</div>
  <div class="row" style="justify-content:center">
    <button type="button" class="btn btn-primary" onclick="unlockAudio()">🔊 Enable Sound</button>
    <button type="button" class="skip-btn" onclick="forceCloseIntro()">Skip Intro ⏭</button>
  </div>
</div>

<div class="wrap">
  <div class="topbar">
    <span class="brand">⚡ DOUBLE SAGE</span>
    <div class="row">
      <button type="button" class="btn" id="musicBtn" onclick="toggleMusic()">🎵 Music: ON</button>
      <button type="button" class="btn" id="sfxBtn" onclick="toggleSfx()">🔊 SFX: ON</button>
      <input type="range" id="volSlider" min="0" max="1" step="0.05" value="0.9" style="width:70px;margin:0" oninput="setVol(this.value)">
      <label class="btn" style="margin:0">📂 Load Song<input type="file" id="songPicker" accept="audio/*" style="display:none" onchange="loadCustomSong(this)"></label>
      <button type="button" class="btn" id="resetThemeBtn" style="display:none;color:#38bdf8;border-color:#38bdf8" onclick="resetTheme()">🔄 Default Theme</button>
      <button type="button" class="btn" onclick="openQbModal()">📚 My QB's</button>
    </div>
  </div>

  <div id="homeView">
    <div class="card">
      <h2>Create Online Room</h2>
      <input id="hostName" placeholder="Your Name (e.g. SageKing)">
      <div class="row">
        <select id="gameMode" style="flex:1">
          <option value="standard">Standard Mode (Contest & Approval)</option>
          <option value="umpire">Umpire Mode (Host Final Ruling)</option>
        </select>
        <input id="roundCount" type="number" value="5" min="1" max="30" style="width:90px" title="Rounds">
        <input id="timerSec" type="number" value="30" min="10" max="180" style="width:90px" title="Seconds">
      </div>
      <button type="button" class="btn btn-primary" style="width:100%" onclick="createRoom()">🚀 Create Multiplayer Room</button>
    </div>

    <div class="card">
      <h2>Join Room</h2>
      <div class="row">
        <input id="joinName" placeholder="Your Name" style="flex:1">
        <input id="joinCode" placeholder="4-Letter Code" maxlength="5" style="width:140px;text-transform:uppercase">
      </div>
      <button type="button" class="btn btn-green" style="width:100%" onclick="joinRoom()">🎮 Join Room</button>
    </div>

    <div class="card">
      <h2>🏆 Live Tournaments & Creator Hub</h2>
      <div class="row" style="margin-bottom:8px">
        <input id="creatorLinkInput" placeholder="Paste Paystack / Selar / Flutterwave Link" style="flex:1;margin:0">
        <button type="button" class="btn btn-amber" onclick="saveCreatorLink()">Save Link</button>
      </div>
      <a id="creatorPayBtn" href="#" target="_blank" style="display:none;text-decoration:none">
        <button type="button" class="btn btn-green" style="width:100%">🎟️ Buy Tournament Ticket / ☕ Support Creator</button>
      </a>
    </div>
  </div>

  <div id="roomView" style="display:none">
    <div class="card">
      <div class="row" style="justify-content:space-between;margin-bottom:10px">
        <div>
          <span class="pill" id="roomCodeBadge">ROOM: ----</span>
          <span class="pill" id="roundBadge">Round 1/5</span>
          <span class="pill" id="modeBadge">Standard</span>
        </div>
        <button type="button" class="btn" onclick="copyInvite()">🔗 Copy Invite Link</button>
      </div>
      <div id="playerList"></div>
      <div id="lobbyControls" style="margin-top:10px"></div>
    </div>

    <div class="card" id="stageCard"></div>
  </div>
</div>

<div id="qbModal" class="modal">
  <div class="modal-inner">
    <div class="row" style="justify-content:space-between;margin-bottom:10px">
      <h2 style="margin:0">📚 My QB's & Pro Packs</h2>
      <button type="button" class="btn btn-red" onclick="closeQbModal()">Close ✕</button>
    </div>
    <div class="row">
      <input id="qbQuestion" placeholder="Type a question..." style="flex:1">
      <button type="button" class="btn btn-amber" onclick="suggestAnswer('qbQuestion','qbAnswer','qbStatus')">✨ Suggest Answer</button>
    </div>
    <div id="qbStatus" style="font-size:12px;color:#94a3b8;margin-bottom:6px"></div>
    <input id="qbAnswer" placeholder="Secret Answer">
    <button type="button" class="btn btn-primary" style="width:100%;margin-bottom:12px" onclick="saveQbItem()">➕ Save to My QB's</button>

    <div class="row" style="margin-bottom:10px">
      <input id="packCodeInput" placeholder="Enter Pro Pack Code (e.g. NAIJA2026, FOOTYPRO, PARTYVIP)" style="flex:1;margin:0">
      <button type="button" class="btn btn-green" onclick="redeemPack()">🎟️ Unlock</button>
    </div>
    <button type="button" class="btn" style="width:100%;margin-bottom:12px" onclick="exportQbPack()">📦 Export Sellable Code (DSPACK:...)</button>
    <div id="qbList"></div>
  </div>
</div>

<script>
const SLIDES = [
  {src:'/media/double_sage_icon.jpg', text:'DOUBLE SAGE ARENA'},
  {src:'/media/double_sage_battle.jpg', text:'HEAD-TO-HEAD MIND DUELS'},
  {src:'/media/double_sage_banner.jpg', text:'CUSTOM QB & LIVE TOURNAMENTS'},
  {src:'/media/double_sage_tournament.jpg', text:'FASTEST MIND WINS'}
];
let slideIdx = 0;
let introTimer = setInterval(() => {
  slideIdx++;
  if (slideIdx >= SLIDES.length) { forceCloseIntro(); return; }
  const img = document.getElementById('introImg');
  const cap = document.getElementById('introCaption');
  if (img) img.src = SLIDES[slideIdx].src;
  if (cap) cap.textContent = SLIDES[slideIdx].text;
}, 3000);

function forceCloseIntro() {
  if (introTimer) { clearInterval(introTimer); introTimer = null; }
  const ov = document.getElementById('introOverlay');
  if (ov) ov.remove();
  unlockAudio();
}

let audioCtx = null, masterGain = null, bgmTimer = null, themeAudio = null;
let musicOn = true, sfxOn = true, masterVol = 0.9, usingCustomSong = false;

function unlockAudio() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) {
      audioCtx = new AC();
      const comp = audioCtx.createDynamicsCompressor();
      masterGain = audioCtx.createGain();
      masterGain.gain.value = masterVol;
      comp.connect(masterGain);
      masterGain.connect(audioCtx.destination);
      window._out = comp;
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
  if (!themeAudio) {
    themeAudio = new Audio('/media/theme.mp3');
    themeAudio.loop = true;
    themeAudio.volume = masterVol;
    themeAudio.onerror = () => { if (!bgmTimer) startSynth(); };
  }
  if (musicOn) {
    themeAudio.play().catch(() => { if (!bgmTimer) startSynth(); });
  }
}

function startSynth() {
  const notes = [130.81, 164.81, 196.0, 261.63, 196.0, 164.81, 146.83, 220.0];
  let s = 0;
  bgmTimer = setInterval(() => {
    if (!musicOn || usingCustomSong || !audioCtx || audioCtx.state !== 'running') return;
    if (themeAudio && !themeAudio.paused) return;
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = 'sawtooth';
    o.frequency.value = notes[s % notes.length];
    g.gain.setValueAtTime(0.22, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.22);
    o.connect(g); g.connect(window._out);
    o.start(); o.stop(audioCtx.currentTime + 0.24);
    s++;
  }, 260);
}

function playSfx(freq = 520) {
  if (!sfxOn) return;
  unlockAudio();
  if (!audioCtx) return;
  const o = audioCtx.createOscillator(), g = audioCtx.createGain();
  o.type = 'triangle'; o.frequency.value = freq;
  g.gain.setValueAtTime(0.3, audioCtx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.16);
  o.connect(g); g.connect(window._out);
  o.start(); o.stop(audioCtx.currentTime + 0.17);
}

function toggleMusic() {
  musicOn = !musicOn;
  document.getElementById('musicBtn').textContent = musicOn ? '🎵 Music: ON' : '🎵 Music: OFF';
  if (themeAudio) { musicOn ? themeAudio.play().catch(()=>{}) : themeAudio.pause(); }
}
function toggleSfx() {
  sfxOn = !sfxOn;
  document.getElementById('sfxBtn').textContent = sfxOn ? '🔊 SFX: ON' : '🔊 SFX: OFF';
}
function setVol(v) {
  masterVol = parseFloat(v);
  if (masterGain) masterGain.gain.value = masterVol;
  if (themeAudio) themeAudio.volume = masterVol;
}
function loadCustomSong(inp) {
  if (!inp.files || !inp.files[0]) return;
  unlockAudio();
  usingCustomSong = true;
  themeAudio.src = URL.createObjectURL(inp.files[0]);
  themeAudio.loop = true;
  themeAudio.volume = masterVol;
  if (musicOn) themeAudio.play().catch(()=>{});
  document.getElementById('resetThemeBtn').style.display = 'inline-block';
}
function resetTheme() {
  usingCustomSong = false;
  document.getElementById('songPicker').value = '';
  themeAudio.pause();
  themeAudio.src = '/media/theme.mp3';
  themeAudio.load();
  if (musicOn) themeAudio.play().catch(()=>{ if (!bgmTimer) startSynth(); });
  document.getElementById('resetThemeBtn').style.display = 'none';
}
document.addEventListener('pointerdown', unlockAudio, { once: true });

// Personal question check + AI Suggested Answer helper
function isPersonalQuestion(q) {
  return /\b(i|me|my|mine|myself|our|ours|we|us|nickname|birthday|favorite|favourite)\b/i.test(q);
}
async function suggestAnswer(qId, aId, statusId) {
  const q = (document.getElementById(qId).value || '').trim();
  const st = document.getElementById(statusId);
  if (!q) { st.textContent = 'Type a question first.'; return; }
  if (isPersonalQuestion(q)) {
    st.textContent = '🔒 Personal question detected — enter your own secret answer!';
    playSfx(320);
    return;
  }
  st.textContent = '✨ Finding suggested answer...';
  try {
    const clean = q.replace(/^(what is|who is|where is|capital of|define)\s+/i, '').replace(/\?+$/, '').trim();
    const res = await fetch('https://en.wikipedia.org/api/rest_v1/page/summary/' + encodeURIComponent(clean));
    if (res.ok) {
      const data = await res.json();
      if (data.title && data.type !== 'disambiguation') {
        document.getElementById(aId).value = data.title;
        st.textContent = '✅ Suggested answer filled! You can edit it anytime.';
        playSfx(660);
        return;
      }
    }
    const sRes = await fetch('https://en.wikipedia.org/w/api.php?action=opensearch&limit=1&format=json&origin=*&search=' + encodeURIComponent(clean));
    const sData = await sRes.json();
    if (sData && sData[1] && sData[1][0]) {
      document.getElementById(aId).value = sData[1][0];
      st.textContent = '✅ Suggested answer filled! You can edit it anytime.';
      playSfx(660);
      return;
    }
    st.textContent = 'Could not auto-suggest — type your custom answer.';
  } catch (e) {
    st.textContent = 'Offline or unavailable — type your custom answer.';
  }
}

// QB & Pro Packs
const PRO_PACKS = {
  NAIJA2026: [
    {q:'Capital city of Nigeria?', a:'Abuja'},
    {q:'Popular Nigerian rice dish cooked in tomato stew?', a:'Jollof Rice'},
    {q:'Year Nigeria gained independence?', a:'1960'}
  ],
  FOOTYPRO: [
    {q:'Country that won the 2022 FIFA World Cup?', a:'Argentina'},
    {q:'Nickname of Arsenal FC?', a:'Gunners'},
    {q:'Number of players per team on a football pitch?', a:'11'}
  ],
  PARTYVIP: [
    {q:'Yellow fruit monkeys love?', a:'Banana'},
    {q:'Breakfast food laid by a hen?', a:'Fried Egg'},
    {q:'Primary color of a ripe tomato?', a:'Red'}
  ]
};
function getQb() {
  try { return JSON.parse(localStorage.getItem('ds_qb') || '[]'); } catch { return []; }
}
function setQb(list) { localStorage.setItem('ds_qb', JSON.stringify(list)); renderQbList(); }
function openQbModal() { document.getElementById('qbModal').style.display = 'block'; renderQbList(); }
function closeQbModal() { document.getElementById('qbModal').style.display = 'none'; }
function saveQbItem() {
  const q = document.getElementById('qbQuestion').value.trim();
  const a = document.getElementById('qbAnswer').value.trim();
  if (!q || !a) return;
  const list = getQb();
  list.unshift({q, a});
  setQb(list);
  document.getElementById('qbQuestion').value = '';
  document.getElementById('qbAnswer').value = '';
  playSfx(600);
}
function redeemPack() {
  const raw = document.getElementById('packCodeInput').value.trim();
  const up = raw.toUpperCase();
  const list = getQb();
  if (PRO_PACKS[up]) {
    setQb([...PRO_PACKS[up], ...list]);
    document.getElementById('packCodeInput').value = '';
    alert('Unlocked ' + up + ' pack!');
  } else if (raw.startsWith('DSPACK:')) {
    try {
      const items = JSON.parse(atob(raw.slice(7)));
      setQb([...items, ...list]);
      document.getElementById('packCodeInput').value = '';
      alert('Imported ' + items.length + ' questions!');
    } catch { alert('Invalid DSPACK code.'); }
  } else {
    alert('Invalid pack code.');
  }
}
function exportQbPack() {
  const list = getQb();
  if (!list.length) { alert('Add questions to My QB first.'); return; }
  const code = 'DSPACK:' + btoa(JSON.stringify(list));
  navigator.clipboard?.writeText(code);
  prompt('Copy your sellable DSPACK code:', code);
}
function renderQbList() {
  const list = getQb();
  const el = document.getElementById('qbList');
  el.innerHTML = list.map((item, i) => `
    <div class="player-item">
      <div style="font-size:13px"><b>${item.q}</b><br><span style="color:#38bdf8">${item.a}</span></div>
      <div class="row">
        <button type="button" class="btn btn-primary" onclick="useQbItem(${i})">Use</button>
        <button type="button" class="btn btn-red" onclick="delQbItem(${i})">✕</button>
      </div>
    </div>
  `).join('') || '<div style="color:#64748b;font-size:13px">No saved questions yet.</div>';
}
function useQbItem(i) {
  const item = getQb()[i];
  if (!item) return;
  const qIn = document.getElementById('liveQuestion');
  const aIn = document.getElementById('liveAnswer');
  if (qIn && aIn) { qIn.value = item.q; aIn.value = item.a; closeQbModal(); }
  else { alert('Enter a room and wait for your Setter turn to load this question!'); }
}
function delQbItem(i) { const list = getQb(); list.splice(i, 1); setQb(list); }

// Creator Link
function saveCreatorLink() {
  const url = document.getElementById('creatorLinkInput').value.trim();
  if (url) { localStorage.setItem('ds_creator_url', url); loadCreatorLink(); }
}
function loadCreatorLink() {
  const url = localStorage.getItem('ds_creator_url') || '';
  const btn = document.getElementById('creatorPayBtn');
  if (url) { btn.href = url; btn.style.display = 'block'; document.getElementById('creatorLinkInput').value = url; }
}
loadCreatorLink();

// Multiplayer State
let ROOM_CODE = '', PLAYER_ID = '', pollTimer = null, roundStartMs = 0, lastPhase = '';
const urlRoom = new URLSearchParams(location.search).get('room');
if (urlRoom) document.getElementById('joinCode').value = urlRoom.toUpperCase();

async function createRoom() {
  unlockAudio();
  const res = await fetch('/api/room/create', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name: document.getElementById('hostName').value || 'Host',
      mode: document.getElementById('gameMode').value,
      rounds: document.getElementById('roundCount').value,
      timer: document.getElementById('timerSec').value
    })
  });
  const d = await res.json();
  if (!d.ok) return alert(d.error);
  ROOM_CODE = d.code; PLAYER_ID = d.player_id;
  enterRoom(d.room);
}

async function joinRoom() {
  unlockAudio();
  const res = await fetch('/api/room/join', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name: document.getElementById('joinName').value || 'Player',
      code: document.getElementById('joinCode').value
    })
  });
  const d = await res.json();
  if (!d.ok) return alert(d.error);
  ROOM_CODE = d.code; PLAYER_ID = d.player_id;
  enterRoom(d.room);
}

function enterRoom(room) {
  document.getElementById('homeView').style.display = 'none';
  document.getElementById('roomView').style.display = 'block';
  renderRoom(room);
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollRoom, 1500);
}

async function pollRoom() {
  if (!ROOM_CODE) return;
  const res = await fetch(`/api/room/state?code=${ROOM_CODE}&pid=${PLAYER_ID}`);
  const d = await res.json();
  if (!d.ok) { clearInterval(pollTimer); alert(d.error || 'Disconnected'); location.reload(); return; }
  renderRoom(d.room);
}

async function sendAction(action, extra = {}) {
  const res = await fetch('/api/room/action', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ code: ROOM_CODE, pid: PLAYER_ID, action, ...extra })
  });
  const d = await res.json();
  if (!d.ok) return alert(d.error);
  renderRoom(d.room);
}

function copyInvite() {
  const link = `${location.origin}/?room=${ROOM_CODE}`;
  navigator.clipboard?.writeText(link);
  alert('Invite link copied: ' + link);
}

function renderRoom(r) {
  document.getElementById('roomCodeBadge').textContent = 'ROOM: ' + r.code;
  document.getElementById('roundBadge').textContent = `Round ${r.round}/${r.total_rounds}`;
  document.getElementById('modeBadge').textContent = r.mode === 'umpire' ? 'Umpire Mode' : 'Standard Mode';

  const isHost = PLAYER_ID === r.host_id;
  const isSetter = PLAYER_ID === r.setter_id;
  const isGuesser = PLAYER_ID === r.guesser_id;

  document.getElementById('playerList').innerHTML = r.players.map(p => `
    <div class="player-item">
      <div><b>${p.name}</b> ${p.id === r.host_id ? '👑' : ''} <span style="color:#94a3b8;font-size:12px">(${p.total_time}s)</span></div>
      <div class="row">
        <span class="pill">${p.score} pts</span>
        ${isHost && p.id !== PLAYER_ID ? `<button type="button" class="btn btn-red" onclick="sendAction('kick',{target_id:'${p.id}'})">Kick</button>` : ''}
      </div>
    </div>
  `).join('');

  const lobbyCtrl = document.getElementById('lobbyControls');
  lobbyCtrl.innerHTML = (r.phase === 'lobby' && isHost)
    ? `<button type="button" class="btn btn-green" style="width:100%" onclick="sendAction('start')">▶️ Start Match</button>`
    : '';

  const stage = document.getElementById('stageCard');
  if (r.phase === 'lobby') {
    stage.innerHTML = `<div style="text-align:center;color:#94a3b8">Waiting for host to start the match...</div>`;
    return;
  }

  if (r.phase === 'set_question') {
    if (isSetter) {
      if (!document.getElementById('liveQuestion')) {
        stage.innerHTML = `
          <h2>✍️ Your Turn to Set a Question</h2>
          <div class="row">
            <input id="liveQuestion" placeholder="Type your question..." style="flex:1">
            <button type="button" class="btn btn-amber" onclick="suggestAnswer('liveQuestion','liveAnswer','liveAiStatus')">✨ Suggest Answer</button>
          </div>
          <div id="liveAiStatus" style="font-size:12px;color:#94a3b8;margin-bottom:6px"></div>
          <input id="liveAnswer" placeholder="Secret Answer">
          <div class="row">
            <button type="button" class="btn" onclick="openQbModal()">📚 Pick from My QB's</button>
            <button type="button" class="btn btn-primary" style="flex:1" onclick="submitLiveQuestion()">Lock In Question 🔒</button>
          </div>
        `;
      }
    } else {
      stage.innerHTML = `<div style="text-align:center;color:#94a3b8">⏳ <b>${r.setter_name}</b> is setting a question for <b>${r.guesser_name}</b>...</div>`;
    }
    return;
  }

  if (r.phase === 'guessing') {
    if (lastPhase !== 'guessing') { roundStartMs = Date.now(); playSfx(580); }
    lastPhase = 'guessing';
    if (isGuesser) {
      if (!document.getElementById('guessInput')) {
        stage.innerHTML = `
          <h2>🎯 Your Turn to Guess!</h2>
          <div style="font-size:17px;font-weight:700;margin-bottom:8px">${r.question}</div>
          <div class="hint-box">💡 Hint: ${r.hint}</div>
          <input id="guessInput" placeholder="Type your guess...">
          <button type="button" class="btn btn-green" style="width:100%" onclick="submitLiveGuess()">Submit Guess ⚡</button>
        `;
      }
    } else {
      stage.innerHTML = `
        <h2>👀 Watching Guess</h2>
        <div style="font-size:16px;font-weight:700;margin-bottom:6px">${r.question}</div>
        <div class="hint-box">💡 Hint: ${r.hint}</div>
        <div style="color:#94a3b8">Waiting for <b>${r.guesser_name}</b> to answer...</div>
      `;
    }
    return;
  }
  lastPhase = r.phase;

  if (r.phase === 'umpire_review') {
    stage.innerHTML = `
      <h2>⚖️ Umpire Final Ruling</h2>
      <p><b>Question:</b> ${r.question}</p>
      <p><b>Secret Answer:</b> <span style="color:#38bdf8">${r.answer}</span></p>
      <p style="margin-bottom:10px"><b>${r.guesser_name}'s Guess:</b> <span style="color:#fbbf24">${r.guess}</span> (${r.guess_time}s)</p>
      ${isHost ? `
        <div class="row">
          <button type="button" class="btn btn-green" style="flex:1" onclick="sendAction('umpire_rule',{winner:'guesser'})">✅ Guesser Right (+5)</button>
          <button type="button" class="btn btn-primary" style="flex:1" onclick="sendAction('umpire_rule',{winner:'setter'})">❌ Setter Wins (+5)</button>
        </div>
      ` : '<div style="color:#94a3b8">Waiting for Umpire ruling...</div>'}
    `;
    return;
  }

  if (r.phase === 'contested') {
    stage.innerHTML = `
      <h2>⚖️ Ruling Contested by ${r.guesser_name}!</h2>
      <p><b>Question:</b> ${r.question}</p>
      <p><b>Your Secret Answer:</b> <span style="color:#38bdf8">${r.answer}</span></p>
      <p style="margin-bottom:12px"><b>${r.guesser_name}'s Guess:</b> <span style="color:#fbbf24">${r.guess}</span></p>
      ${isSetter ? `
        <div class="row">
          <button type="button" class="btn btn-green" style="flex:1" onclick="sendAction('resolve_contest',{accept:true})">✅ Accept Guesser is Right (+5 to Guesser)</button>
          <button type="button" class="btn btn-red" style="flex:1" onclick="sendAction('resolve_contest',{accept:false})">❌ Reject Contest (Keep +5 Pts)</button>
        </div>
      ` : `<div style="color:#94a3b8">Waiting for <b>${r.setter_name}</b> to review the contest...</div>`}
    `;
    return;
  }

  if (r.phase === 'review') {
    const canContest = r.mode !== 'umpire' && isGuesser && r.winner_awarded === 'setter' && !r.contested;
    stage.innerHTML = `
      <h2>📊 Round Result</h2>
      <p><b>Question:</b> ${r.question}</p>
      <p><b>Secret Answer:</b> <span style="color:#38bdf8">${r.answer}</span></p>
      <p><b>Guess:</b> ${r.guess} (${r.guess_time}s)</p>
      <div class="hint-box">${r.ruling}</div>
      <div class="row" style="margin-top:10px">
        ${canContest ? `<button type="button" class="btn btn-amber" onclick="sendAction('contest')">⚖️ Contest Ruling</button>` : ''}
        ${(isHost || isSetter) ? `<button type="button" class="btn btn-primary" style="flex:1" onclick="sendAction('next_round')">Next Round ➡️</button>` : ''}
      </div>
    `;
    return;
  }

  if (r.phase === 'gameover') {
    const sorted = [...r.players].sort((a, b) => (b.score - a.score) || (a.total_time - b.total_time));
    const champ = sorted[0];
    stage.innerHTML = `
      <h2>🏆 Match Complete!</h2>
      <div class="hint-box">Champion: ${champ.name} (${champ.score} pts • ${champ.total_time}s)</div>
      ${isHost ? `<button type="button" class="btn btn-green" style="width:100%;margin-top:10px" onclick="sendAction('start')">🔄 Play Again</button>` : ''}
    `;
  }
}

function submitLiveQuestion() {
  sendAction('set_question', {
    question: document.getElementById('liveQuestion').value,
    answer: document.getElementById('liveAnswer').value
  });
}
function submitLiveGuess() {
  const elapsed = (Date.now() - roundStartMs) / 1000;
  sendAction('submit_guess', {
    guess: document.getElementById('guessInput').value,
    elapsed
  });
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

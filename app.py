import os
import random
import string
import time
from flask import Flask, request, jsonify, send_from_directory, abort

app = Flask(__name__)

ROOMS = {}

STARTER_PROMPTS = [
    {"cat": "Logic & Riddles", "q": "What has keys that open no locks, space without room, and you can enter but not go outside?", "a": "A keyboard"},
    {"cat": "Logic & Riddles", "q": "I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I?", "a": "An echo"},
    {"cat": "Pop Culture", "q": "Which sci-fi movie series features a character named Morpheus offering a red pill and a blue pill?", "a": "The Matrix"},
    {"cat": "World & Geography", "q": "What is the only country in the world that is also a continent?", "a": "Australia"},
    {"cat": "Science & Tech", "q": "What planet in our solar system has the most moons?", "a": "Saturn"},
    {"cat": "Sports & Games", "q": "How many squares are on a standard chessboard?", "a": "64"},
    {"cat": "Wordplay", "q": "What 5-letter word becomes shorter when you add two letters to it?", "a": "Short"},
    {"cat": "History", "q": "In what year did humans first land on the Moon?", "a": "1969"}
]

def gen_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase, k=4))
        if code not in ROOMS:
            return code

def check_timer(room):
    if room["phase"] == "answering" and room["deadline"] is not None:
        now = time.time()
        if now >= room["deadline"]:
            room["last_guess"] = "(Time Expired)"
            room["last_time"] = float(room["timer_sec"])
            room["phase"] = "judging"
            room["deadline"] = None

@app.route("/media/<path:filename>")
def serve_media(filename):
    safe_name = os.path.basename(filename)
    for folder in [".", "static"]:
        if os.path.exists(os.path.join(folder, safe_name)):
            return send_from_directory(folder, safe_name)
    base_no_ext = os.path.splitext(safe_name)[0].lower()
    for folder in [".", "static"]:
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                if os.path.splitext(f)[0].lower() == base_no_ext:
                    return send_from_directory(folder, f)
    abort(404)

@app.route("/api/create", methods=["POST"])
def api_create():
    data = request.json or {}
    name = (data.get("name") or "Host").strip()[:20]
    pid = data.get("pid") or ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    max_p = max(2, min(10, int(data.get("max_players", 4))))
    q_per_p = max(1, min(10, int(data.get("q_per_player", 2))))
    timer_sec = max(10, min(60, int(data.get("timer_sec", 25))))
    umpire = bool(data.get("umpire", False))

    code = gen_code()
    players = []
    if not umpire:
        players.append({"pid": pid, "name": name, "score": 0, "total_time": 0.0, "asked": 0})

    ROOMS[code] = {
        "code": code,
        "host_pid": pid,
        "host_name": name,
        "umpire": umpire,
        "max_players": max_p,
        "q_per_player": q_per_p,
        "timer_sec": timer_sec,
        "players": players,
        "phase": "lobby",
        "asker_idx": 0,
        "guesser_idx": 1,
        "question": "",
        "secret_answer": "",
        "last_guess": "",
        "last_time": 0.0,
        "deadline": None,
        "result_msg": "",
        "last_correct": False
    }
    return jsonify({"ok": True, "code": code, "pid": pid})

@app.route("/api/join", methods=["POST"])
def api_join():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "Player").strip()[:20]
    pid = data.get("pid") or ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

    room = ROOMS.get(code)
    if not room:
        return jsonify({"ok": False, "error": "Room not found."})
    if room["umpire"] and pid == room["host_pid"]:
        return jsonify({"ok": True, "code": code, "pid": pid})
    for p in room["players"]:
        if p["pid"] == pid:
            p["name"] = name
            return jsonify({"ok": True, "code": code, "pid": pid})
    if room["phase"] != "lobby":
        return jsonify({"ok": False, "error": "Match already in progress."})
    if len(room["players"]) >= room["max_players"]:
        return jsonify({"ok": False, "error": "Room is full."})

    room["players"].append({"pid": pid, "name": name, "score": 0, "total_time": 0.0, "asked": 0})
    return jsonify({"ok": True, "code": code, "pid": pid})

@app.route("/api/kick", methods=["POST"])
def api_kick():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or data.get("pid") != room["host_pid"] or room["phase"] != "lobby":
        return jsonify({"ok": False})
    target = data.get("target_pid")
    room["players"] = [p for p in room["players"] if p["pid"] != target]
    return jsonify({"ok": True})

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or data.get("pid") != room["host_pid"]:
        return jsonify({"ok": False})
    if len(room["players"]) < 2:
        return jsonify({"ok": False, "error": "Need at least 2 players to start."})
    for p in room["players"]:
        p["score"] = 0
        p["total_time"] = 0.0
        p["asked"] = 0
    room["asker_idx"] = 0
    room["guesser_idx"] = 0 if room["umpire"] else 1
    room["phase"] = "asking"
    return jsonify({"ok": True})

@app.route("/api/ask", methods=["POST"])
def api_ask():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "asking":
        return jsonify({"ok": False})
    pid = data.get("pid")
    expected_asker = room["host_pid"] if room["umpire"] else room["players"][room["asker_idx"]]["pid"]
    if pid != expected_asker:
        return jsonify({"ok": False})
    q = (data.get("question") or "").strip()
    a = (data.get("answer") or "").strip()
    if not q or not a:
        return jsonify({"ok": False, "error": "Enter both a question and secret answer."})
    room["question"] = q
    room["secret_answer"] = a
    room["last_guess"] = ""
    room["phase"] = "answering"
    room["deadline"] = time.time() + room["timer_sec"]
    return jsonify({"ok": True})

@app.route("/api/answer", methods=["POST"])
def api_answer():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "answering":
        return jsonify({"ok": False})
    guesser = room["players"][room["guesser_idx"]]
    if data.get("pid") != guesser["pid"]:
        return jsonify({"ok": False})
    elapsed = max(0.1, round(room["timer_sec"] - max(0.0, room["deadline"] - time.time()), 1))
    room["last_guess"] = (data.get("guess") or "(Blank)").strip()
    room["last_time"] = elapsed
    room["deadline"] = None
    room["phase"] = "judging"
    return jsonify({"ok": True})

@app.route("/api/judge", methods=["POST"])
def api_judge():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "judging":
        return jsonify({"ok": False})
    expected_asker = room["host_pid"] if room["umpire"] else room["players"][room["asker_idx"]]["pid"]
    if data.get("pid") != expected_asker:
        return jsonify({"ok": False})
    correct = bool(data.get("correct"))
    guesser = room["players"][room["guesser_idx"]]
    guesser["total_time"] = round(guesser["total_time"] + room["last_time"], 1)
    if correct:
        guesser["score"] += 5
        room["last_correct"] = True
        room["result_msg"] = f"{guesser['name']} scored +5 Pts!"
    else:
        room["last_correct"] = False
        room["result_msg"] = f"Marked Wrong by {'Umpire' if room['umpire'] else 'Asker'}."
    room["phase"] = "round_result"
    return jsonify({"ok": True})

@app.route("/api/contest", methods=["POST"])
def api_contest():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["umpire"] or room["phase"] != "round_result" or room["last_correct"]:
        return jsonify({"ok": False})
    guesser = room["players"][room["guesser_idx"]]
    if data.get("pid") != guesser["pid"]:
        return jsonify({"ok": False})
    room["phase"] = "contest_review"
    return jsonify({"ok": True})

@app.route("/api/resolve_contest", methods=["POST"])
def api_resolve_contest():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["umpire"] or room["phase"] != "contest_review":
        return jsonify({"ok": False})
    asker = room["players"][room["asker_idx"]]
    if data.get("pid") != asker["pid"]:
        return jsonify({"ok": False})
    guesser = room["players"][room["guesser_idx"]]
    decision = data.get("decision")
    if decision == "accept":
        guesser["score"] += 5
        room["last_correct"] = True
        room["result_msg"] = f"Contest Accepted! {guesser['name']} awarded +5 Pts."
        room["phase"] = "round_result"
    else:
        guesser["total_time"] = max(0.0, round(guesser["total_time"] - room["last_time"], 1))
        room["question"] = ""
        room["secret_answer"] = ""
        room["last_guess"] = ""
        room["phase"] = "asking"
    return jsonify({"ok": True})

@app.route("/api/next", methods=["POST"])
def api_next():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "round_result":
        return jsonify({"ok": False})
    expected_asker = room["host_pid"] if room["umpire"] else room["players"][room["asker_idx"]]["pid"]
    if data.get("pid") != expected_asker:
        return jsonify({"ok": False})

    n = len(room["players"])
    if room["umpire"]:
        room["players"][room["guesser_idx"]]["asked"] += 1
        if all(p["asked"] >= room["q_per_player"] for p in room["players"]):
            room["phase"] = "finished"
        else:
            room["guesser_idx"] = (room["guesser_idx"] + 1) % n
            room["phase"] = "asking"
    else:
        room["players"][room["asker_idx"]]["asked"] += 1
        if all(p["asked"] >= room["q_per_player"] for p in room["players"]):
            room["phase"] = "finished"
        else:
            room["asker_idx"] = (room["asker_idx"] + 1) % n
            room["guesser_idx"] = (room["asker_idx"] + 1) % n
            room["phase"] = "asking"
    return jsonify({"ok": True})

@app.route("/api/state")
def api_state():
    code = (request.args.get("code") or "").upper()
    pid = request.args.get("pid") or ""
    room = ROOMS.get(code)
    if not room:
        return jsonify({"ok": False})
    check_timer(room)
    n = len(room["players"])
    asker_pid = room["host_pid"] if room["umpire"] else (room["players"][room["asker_idx"]]["pid"] if n else "")
    asker_name = f"Umpire ({room['host_name']})" if room["umpire"] else (room["players"][room["asker_idx"]]["name"] if n else "")
    guesser_pid = room["players"][room["guesser_idx"]]["pid"] if n else ""
    guesser_name = room["players"][room["guesser_idx"]]["name"] if n else ""
    rem = max(0, int(round(room["deadline"] - time.time()))) if room["deadline"] else 0

    show_secret = (pid == asker_pid) or (room["phase"] in ["round_result", "contest_review", "finished"])
    digit_hint = any(ch.isdigit() for ch in room["secret_answer"]) and room["phase"] == "answering"

    leaderboard = sorted(room["players"], key=lambda x: (-x["score"], x["total_time"]))
    return jsonify({
        "ok": True,
        "code": room["code"],
        "host_pid": room["host_pid"],
        "umpire": room["umpire"],
        "max_players": room["max_players"],
        "q_per_player": room["q_per_player"],
        "timer_sec": room["timer_sec"],
        "players": room["players"],
        "leaderboard": leaderboard,
        "phase": room["phase"],
        "asker_pid": asker_pid,
        "asker_name": asker_name,
        "guesser_pid": guesser_pid,
        "guesser_name": guesser_name,
        "question": room["question"],
        "secret_answer": room["secret_answer"] if show_secret else "",
        "digit_hint": digit_hint,
        "last_guess": room["last_guess"],
        "last_time": room["last_time"],
        "remaining": rem,
        "result_msg": room["result_msg"],
        "last_correct": room["last_correct"]
    })

@app.route("/")
def index():
    return HTML_PAGE

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Double Sage — Online Multiplayer</title>
<style>
  :root { --bg:#070b14; --card:#111827; --border:#1f2937; --accent:#f59e0b; --blue:#3b82f6; --green:#10b981; --red:#ef4444; --text:#f3f4f6; --muted:#9ca3af; }
  * { box-sizing:border-box; font-family:system-ui,-apple-system,sans-serif; }
  body { margin:0; background:var(--bg); color:var(--text); padding-bottom:40px; }
  #introOverlay { position:fixed; inset:0; z-index:99990; background:#050811; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:20px; text-align:center; }
  #introOverlay img { max-width:90%; max-height:55vh; border-radius:16px; border:2px solid var(--accent); box-shadow:0 0 30px rgba(245,158,11,0.35); object-fit:contain; }
  .intro-bar { width:260px; height:6px; background:#1f2937; border-radius:99px; overflow:hidden; margin:16px 0; }
  .intro-fill { height:100%; width:0%; background:var(--accent); transition:width 0.2s linear; }
  .intro-btns { display:flex; gap:12px; flex-wrap:wrap; justify-content:center; margin-top:8px; position:relative; z-index:999999; pointer-events:auto; }
  .topbar { position:sticky; top:0; z-index:100; background:rgba(17,24,39,0.95); backdrop-filter:blur(8px); border-bottom:1px solid var(--border); padding:10px 14px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; }
  .brand { display:flex; align-items:center; gap:8px; font-weight:800; color:var(--accent); letter-spacing:0.5px; }
  .brand img { width:30px; height:30px; border-radius:8px; object-fit:cover; }
  .controls { display:flex; flex-wrap:wrap; align-items:center; gap:6px; }
  button { background:#1f2937; color:var(--text); border:1px solid #374151; padding:8px 12px; border-radius:10px; font-weight:700; cursor:pointer; font-size:0.85rem; }
  button:active { transform:scale(0.97); }
  .btn-gold { background:var(--accent); color:#000; border:none; }
  .btn-blue { background:var(--blue); color:#fff; border:none; }
  .btn-green { background:var(--green); color:#000; border:none; }
  .btn-red { background:var(--red); color:#fff; border:none; }
  .wrap { max-width:680px; margin:16px auto; padding:0 14px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:16px; margin-bottom:14px; }
  .showcase { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:14px; }
  .showcase img { width:100%; height:92px; object-fit:cover; border-radius:12px; border:1px solid var(--border); }
  input, select, textarea { width:100%; background:#0b1120; color:var(--text); border:1px solid #374151; border-radius:10px; padding:10px; margin:6px 0 12px; font-size:0.95rem; }
  label { font-size:0.82rem; color:var(--muted); font-weight:600; }
  .row { display:flex; gap:10px; }
  .row > div { flex:1; }
  .pill { display:inline-block; padding:4px 10px; border-radius:99px; font-size:0.78rem; font-weight:700; background:#1f2937; color:var(--accent); }
  .timer-box { font-size:2rem; font-weight:900; text-align:center; color:var(--accent); padding:10px; background:#0b1120; border-radius:12px; margin:10px 0; }
  .timer-urgent { color:var(--red); animation:pulse 0.6s infinite alternate; }
  @keyframes pulse { from{transform:scale(1);} to{transform:scale(1.05);} }
  .modal { display:none; position:fixed; inset:0; z-index:500; background:rgba(0,0,0,0.8); padding:16px; overflow-y:auto; }
  .modal-inner { max-width:520px; margin:30px auto; background:var(--card); border:1px solid var(--border); border-radius:16px; padding:18px; }
  .qb-item { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:8px; background:#0b1120; border-radius:10px; margin-bottom:8px; }
  .hidden { display:none !important; }
</style>
</head>
<body>

<div id="introOverlay">
  <div style="font-weight:900;color:#f59e0b;letter-spacing:1.5px;margin-bottom:10px;">DOUBLE SAGE — MIND DUEL</div>
  <img id="introImg" src="/media/double_sage_icon.jpg" alt="Double Sage">
  <div id="introCaption" style="margin-top:10px;font-weight:700;color:#e5e7eb;">1 / 4 — DOUBLE SAGE</div>
  <div class="intro-bar"><div id="introFill" class="intro-fill"></div></div>
  <div class="intro-btns">
    <button type="button" class="btn-gold" style="position:relative;z-index:999999;pointer-events:auto;" onclick="unlockAudio(true)">🔊 Enable Loud Sound</button>
    <button type="button" style="position:relative;z-index:999999;pointer-events:auto;" onclick="forceCloseIntro()">Skip Intro ⏭</button>
  </div>
</div>

<div class="topbar">
  <div class="brand">
    <img src="/media/double_sage_icon.jpg" onerror="this.style.display='none'">
    <span>DOUBLE SAGE</span>
  </div>
  <div class="controls">
    <button type="button" onclick="replayIntro()">🎬 Intro</button>
    <button type="button" onclick="openQB()">📚 My QB's</button>
    <button type="button" id="btnMusic" onclick="toggleMusic()">🎵 Music: ON</button>
    <button type="button" id="btnSfx" onclick="toggleSfx()">🔊 SFX: ON</button>
    <input type="range" id="volSlider" min="0" max="1" step="0.05" value="0.9" style="width:70px;margin:0;" oninput="setVol(this.value)">
    <button type="button" onclick="document.getElementById('songPicker').click()">📂 Load Song</button>
    <input type="file" id="songPicker" accept="audio/*" class="hidden" onchange="loadUserSong(this)">
  </div>
</div>

<audio id="themeAudio" src="/media/theme.mp3" loop preload="auto"></audio>

<div class="wrap">
  <div class="showcase">
    <img src="/media/double_sage_battle.jpg" alt="Battle" onerror="this.style.display='none'">
    <img src="/media/double_sage_banner.jpg" alt="Banner" onerror="this.style.display='none'">
    <img src="/media/double_sage_tournament.jpg" alt="Tournament" onerror="this.style.display='none'">
  </div>

  <div id="homeView">
    <div class="card">
      <h3 style="margin-top:0;color:var(--accent);">🎮 Create Online Room</h3>
      <label>Your Name</label>
      <input id="cName" placeholder="Enter your name" maxlength="20">
      <div class="row">
        <div><label>Players (2–10)</label><input id="cMax" type="number" min="2" max="10" value="4"></div>
        <div><label>Questions / Player</label><input id="cQpp" type="number" min="1" max="10" value="2"></div>
        <div><label>Timer (10–60s)</label><input id="cTimer" type="number" min="10" max="60" value="25"></div>
      </div>
      <label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;color:#fff;">
        <input id="cUmpire" type="checkbox" style="width:auto;margin:0;">
        ⚖ Play as Umpire (Organizer sets all questions; ruling is final)
      </label>
      <button type="button" class="btn-gold" style="width:100%;" onclick="createRoom()">Create Room & Generate Code</button>
    </div>

    <div class="card">
      <h3 style="margin-top:0;color:var(--blue);">🔑 Join Existing Room</h3>
      <div class="row">
        <div><label>Your Name</label><input id="jName" placeholder="Your name" maxlength="20"></div>
        <div><label>4-Letter Code</label><input id="jCode" placeholder="ABCD" maxlength="4" style="text-transform:uppercase;"></div>
      </div>
      <button type="button" class="btn-blue" style="width:100%;" onclick="joinRoom()">Join Match</button>
    </div>
  </div>

  <div id="roomView" class="hidden">
    <div class="card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
      <div>
        <span class="pill">ROOM: <strong id="rCode">----</strong></span>
        <span class="pill" id="rModePill">STANDARD</span>
      </div>
      <button type="button" class="btn-blue" onclick="copyInvite()">🔗 Copy Invite Link</button>
    </div>

    <div id="lobbyPanel" class="card hidden">
      <h3 style="margin-top:0;">Waiting Lobby</h3>
      <div id="lobbyPlayers"></div>
      <button type="button" id="btnStartMatch" class="btn-green hidden" style="width:100%;margin-top:10px;" onclick="startMatch()">🚀 Start Match</button>
    </div>

    <div id="askPanel" class="card hidden">
      <h3 style="margin-top:0;color:var(--accent);" id="askHeader">Set Your Question</h3>
      <div id="askerForm">
        <label>Pick Starter Prompt or Saved QB (Editable)</label>
        <div class="row">
          <div>
            <select id="promptSelect" onchange="applySelectedPrompt()">
              <option value="">-- Choose Starter or My QB --</option>
            </select>
          </div>
          <div style="flex:0 0 auto;display:flex;align-items:center;">
            <button type="button" onclick="loadNextUnusedQB()">⚡ Next QB</button>
          </div>
        </div>
        <label>Question</label>
        <textarea id="inQuestion" rows="2" placeholder="Type or edit your question..."></textarea>
        <label>Secret Answer</label>
        <input id="inAnswer" placeholder="Exact secret answer...">
        <div class="row">
          <button type="button" onclick="saveCurrentToQB()">💾 Save to My QB's</button>
          <button type="button" class="btn-gold" onclick="submitQuestion()">🔒 Lock & Send Question</button>
        </div>
      </div>
      <div id="askerWait" class="hidden" style="color:var(--muted);text-align:center;padding:16px;">
        Waiting for <strong id="waitAskerName"></strong> to lock in a question...
      </div>
    </div>

    <div id="answerPanel" class="card hidden">
      <div class="pill" id="turnBadge">TURN</div>
      <h3 id="displayQuestion" style="margin:10px 0;"></h3>
      <div id="digitHintBox" class="pill hidden" style="background:#312e81;color:#c7d2fe;margin-bottom:8px;">🔢 Manager Hint: Answer contains numbers/digits!</div>
      <div id="timerDisplay" class="timer-box">25s</div>
      <div id="guesserForm" class="hidden">
        <input id="inGuess" placeholder="Type your answer quickly...">
        <button type="button" class="btn-green" style="width:100%;" onclick="submitGuess()">✅ Submit Answer</button>
      </div>
      <div id="answerWait" class="hidden" style="color:var(--muted);text-align:center;">
        <strong id="activeGuesserName"></strong> is answering...
      </div>
    </div>

    <div id="judgePanel" class="card hidden">
      <h3 style="margin-top:0;">Review Answer</h3>
      <p><strong>Question:</strong> <span id="jQuestion"></span></p>
      <p><strong>Secret Answer:</strong> <span id="jSecret" style="color:var(--accent);"></span></p>
      <p><strong>Guesser's Reply:</strong> <span id="jGuess" style="color:#60a5fa;"></span> (<span id="jTime"></span>s)</p>
      <div id="judgeBtns" class="row hidden">
        <button type="button" class="btn-green" onclick="sendJudge(true)">✅ Correct (+5 Pts)</button>
        <button type="button" class="btn-red" onclick="sendJudge(false)">❌ Wrong (0 Pts)</button>
      </div>
      <div id="judgeWait" class="hidden" style="color:var(--muted);">Waiting for ruling...</div>
    </div>

    <div id="resultPanel" class="card hidden">
      <h3 id="resTitle" style="margin-top:0;">Round Result</h3>
      <p id="resDetail"></p>
      <div id="contestArea" class="hidden" style="margin:10px 0;">
        <button type="button" class="btn-red" style="width:100%;" onclick="contestResult()">⚠️ CONTEST ANSWER (Dispute Result)</button>
      </div>
      <div id="contestResolveArea" class="hidden" style="background:#1f2937;padding:12px;border-radius:12px;margin:10px 0;">
        <p style="margin-top:0;font-weight:700;color:var(--accent);">Guesser Contested! Choose Action:</p>
        <div class="row">
          <button type="button" class="btn-green" onclick="resolveContest('accept')">✅ Accept Guess (+5 Pts)</button>
          <button type="button" class="btn-gold" onclick="resolveContest('reask')">🔄 Send New Question (0 Pts)</button>
        </div>
      </div>
      <button type="button" id="btnNextRound" class="btn-blue hidden" style="width:100%;margin-top:10px;" onclick="nextRound()">Next Turn ➡</button>
    </div>

    <div class="card">
      <h3 style="margin-top:0;color:var(--accent);">🏆 Live Leaderboard</h3>
      <div id="leaderboardList"></div>
    </div>
  </div>
</div>

<div id="qbModal" class="modal">
  <div class="modal-inner">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h3 style="margin:0;color:var(--accent);">📚 My QB's (Saved Question Banks)</h3>
      <button type="button" onclick="closeQB()">✖</button>
    </div>
    <p style="font-size:0.85rem;color:var(--muted);">Saved permanently on this device for instant one-tap loading.</p>
    <input id="qbNewQ" placeholder="New Question">
    <input id="qbNewA" placeholder="Secret Answer">
    <button type="button" class="btn-gold" style="width:100%;margin-bottom:14px;" onclick="addQBManual()">💾 Add to My QB's</button>
    <div id="qbList"></div>
  </div>
</div>

<script>
const STARTERS = """ + repr(STARTER_PROMPTS) + """;
const SLIDES = [
  {src: "/media/double_sage_icon.jpg", label: "1 / 4 — DOUBLE SAGE"},
  {src: "/media/double_sage_battle.jpg", label: "2 / 4 — HEAD-TO-HEAD DUEL"},
  {src: "/media/double_sage_banner.jpg", label: "3 / 4 — MIND ARENA"},
  {src: "/media/double_sage_tournament.jpg", label: "4 / 4 — TOURNAMENT CLASH"}
];

let slideIdx = 0, introInterval = null;
function forceCloseIntro() {
  if (introInterval) { clearInterval(introInterval); introInterval = null; }
  const ov = document.getElementById("introOverlay");
  if (ov) ov.style.display = "none";
  unlockAudio(false);
}
function startIntroSequence() {
  slideIdx = 0;
  const ov = document.getElementById("introOverlay");
  const img = document.getElementById("introImg");
  const cap = document.getElementById("introCaption");
  const fill = document.getElementById("introFill");
  if (!ov) return;
  ov.style.display = "flex";
  img.src = SLIDES[0].src;
  cap.textContent = SLIDES[0].label;
  fill.style.width = "25%";
  if (introInterval) clearInterval(introInterval);
  introInterval = setInterval(() => {
    slideIdx++;
    if (slideIdx >= SLIDES.length) {
      forceCloseIntro();
      return;
    }
    img.src = SLIDES[slideIdx].src;
    cap.textContent = SLIDES[slideIdx].label;
    fill.style.width = ((slideIdx + 1) * 25) + "%";
  }, 3000);
}
function replayIntro() { startIntroSequence(); }

let audioCtx = null, masterGain = null, synthTimer = null;
let musicOn = true, sfxOn = true, masterVol = 0.9, usingCustomFile = false;

function unlockAudio(forcePlay) {
  const aud = document.getElementById("themeAudio");
  if (aud) {
    aud.volume = masterVol;
    if (musicOn) {
      aud.play().then(() => { usingCustomFile = true; if (synthTimer) { clearInterval(synthTimer); synthTimer = null; } }).catch(() => { startSynthFallback(); });
    }
  }
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) {
      audioCtx = new AC();
      const comp = audioCtx.createDynamicsCompressor();
      masterGain = audioCtx.createGain();
      masterGain.gain.value = masterVol;
      comp.connect(masterGain);
      masterGain.connect(audioCtx.destination);
      window._outNode = comp;
    }
  }
  if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
  if (forcePlay) playSfx(660, 0.15);
}

function startSynthFallback() {
  if (usingCustomFile || synthTimer) return;
  const notes = [130.81, 164.81, 196.0, 261.63, 196.0, 164.81, 146.83, 220.0];
  let step = 0;
  synthTimer = setInterval(() => {
    if (!musicOn || usingCustomFile || !audioCtx || audioCtx.state !== "running") return;
    const osc = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    osc.type = "sawtooth";
    osc.frequency.value = notes[step % notes.length];
    g.gain.setValueAtTime(0.25, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.22);
    osc.connect(g);
    g.connect(window._outNode);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.24);
    step++;
  }, 260);
}

function playSfx(freq, dur) {
  if (!sfxOn) return;
  unlockAudio(false);
  if (!audioCtx || !window._outNode) return;
  const osc = audioCtx.createOscillator();
  const g = audioCtx.createGain();
  osc.type = "triangle";
  osc.frequency.value = freq;
  g.gain.setValueAtTime(0.35, audioCtx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
  osc.connect(g);
  g.connect(window._outNode);
  osc.start();
  osc.stop(audioCtx.currentTime + dur + 0.02);
}

function toggleMusic() {
  musicOn = !musicOn;
  document.getElementById("btnMusic").textContent = musicOn ? "🎵 Music: ON" : "🎵 Music: OFF";
  const aud = document.getElementById("themeAudio");
  if (!musicOn && aud) aud.pause();
  if (musicOn) unlockAudio(false);
}
function toggleSfx() {
  sfxOn = !sfxOn;
  document.getElementById("btnSfx").textContent = sfxOn ? "🔊 SFX: ON" : "🔊 SFX: OFF";
}
function setVol(v) {
  masterVol = parseFloat(v);
  const aud = document.getElementById("themeAudio");
  if (aud) aud.volume = masterVol;
  if (masterGain) masterGain.gain.value = masterVol;
}
function loadUserSong(inp) {
  if (!inp.files || !inp.files[0]) return;
  const url = URL.createObjectURL(inp.files[0]);
  const aud = document.getElementById("themeAudio");
  aud.src = url;
  usingCustomFile = true;
  musicOn = true;
  document.getElementById("btnMusic").textContent = "🎵 Music: ON";
  aud.volume = masterVol;
  aud.play();
}

function getQBs() {
  try { return JSON.parse(localStorage.getItem("ds_qbs") || "[]"); } catch { return []; }
}
function saveQBs(list) {
  localStorage.setItem("ds_qbs", JSON.stringify(list));
  refreshPromptDropdown();
}
function openQB() { renderQBList(); document.getElementById("qbModal").style.display = "block"; }
function closeQB() { document.getElementById("qbModal").style.display = "none"; }
function addQBManual() {
  const q = document.getElementById("qbNewQ").value.trim();
  const a = document.getElementById("qbNewA").value.trim();
  if (!q || !a) return;
  const list = getQBs();
  list.push({q, a});
  saveQBs(list);
  document.getElementById("qbNewQ").value = "";
  document.getElementById("qbNewA").value = "";
  renderQBList();
}
function delQB(idx) {
  const list = getQBs();
  list.splice(idx, 1);
  saveQBs(list);
  renderQBList();
}
function renderQBList() {
  const list = getQBs();
  const el = document.getElementById("qbList");
  if (!list.length) { el.innerHTML = "<p style='color:var(--muted);'>No saved QB's yet.</p>"; return; }
  el.innerHTML = list.map((item, i) => `<div class="qb-item"><div><strong>${item.q}</strong><br><small style="color:var(--accent);">Ans: ${item.a}</small></div><button type="button" class="btn-red" onclick="delQB(${i})">🗑</button></div>`).join("");
}
function saveCurrentToQB() {
  const q = document.getElementById("inQuestion").value.trim();
  const a = document.getElementById("inAnswer").value.trim();
  if (!q || !a) return alert("Type a question and secret answer first.");
  const list = getQBs();
  list.push({q, a});
  saveQBs(list);
  playSfx(880, 0.15);
  alert("Saved to My QB's!");
}
let usedQBIndices = new Set();
function loadNextUnusedQB() {
  const list = getQBs();
  if (!list.length) return alert("Your QB bank is empty! Add questions in 📚 My QB's first.");
  let idx = list.findIndex((_, i) => !usedQBIndices.has(i));
  if (idx === -1) { usedQBIndices.clear(); idx = 0; }
  usedQBIndices.add(idx);
  document.getElementById("inQuestion").value = list[idx].q;
  document.getElementById("inAnswer").value = list[idx].a;
  playSfx(740, 0.12);
}
function refreshPromptDropdown() {
  const sel = document.getElementById("promptSelect");
  if (!sel || document.activeElement === sel) return;
  const curVal = sel.value;
  const qbs = getQBs();
  let html = '<option value="">-- Choose Starter or My QB --</option>';
  if (qbs.length) {
    html += '<optgroup label="📚 My Saved QBs">';
    qbs.forEach((item, i) => { html += `<option value="qb:${i}">${item.q.slice(0,55)}</option>`; });
    html += '</optgroup>';
  }
  html += '<optgroup label="✨ Starter Prompts">';
  STARTERS.forEach((item, i) => { html += `<option value="st:${i}">[${item.cat}] ${item.q.slice(0,48)}</option>`; });
  html += '</optgroup>';
  sel.innerHTML = html;
  sel.value = curVal;
}
function applySelectedPrompt() {
  const val = document.getElementById("promptSelect").value;
  if (!val) return;
  const [type, idxStr] = val.split(":");
  const idx = parseInt(idxStr, 10);
  const item = type === "qb" ? getQBs()[idx] : STARTERS[idx];
  if (item) {
    document.getElementById("inQuestion").value = item.q;
    document.getElementById("inAnswer").value = item.a;
    playSfx(600, 0.1);
  }
}

let myPid = localStorage.getItem("ds_pid") || Math.random().toString(36).slice(2, 12);
localStorage.setItem("ds_pid", myPid);
let roomCode = "", pollTimer = null, lastPhase = "";

async function postApi(url, body) {
  const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
  return r.json();
}
async function createRoom() {
  unlockAudio(true);
  const res = await postApi("/api/create", {
    name: document.getElementById("cName").value || "Host",
    pid: myPid,
    max_players: document.getElementById("cMax").value,
    q_per_player: document.getElementById("cQpp").value,
    timer_sec: document.getElementById("cTimer").value,
    umpire: document.getElementById("cUmpire").checked
  });
  if (res.ok) enterRoom(res.code);
}
async function joinRoom() {
  unlockAudio(true);
  const res = await postApi("/api/join", {
    name: document.getElementById("jName").value || "Player",
    code: document.getElementById("jCode").value,
    pid: myPid
  });
  if (res.ok) enterRoom(res.code);
  else alert(res.error || "Unable to join.");
}
function enterRoom(code) {
  roomCode = code;
  document.getElementById("homeView").classList.add("hidden");
  document.getElementById("roomView").classList.remove("hidden");
  document.getElementById("rCode").textContent = code;
  refreshPromptDropdown();
  if (pollTimer) clearInterval(pollTimer);
  pollState();
  pollTimer = setInterval(pollState, 1500);
}
function copyInvite() {
  const link = `${location.origin}/?room=${roomCode}`;
  navigator.clipboard.writeText(link).then(() => alert("Invite link copied: " + link));
}
async function kickPlayer(targetPid) { await postApi("/api/kick", {code: roomCode, pid: myPid, target_pid: targetPid}); pollState(); }
async function startMatch() { playSfx(880, 0.2); const r = await postApi("/api/start", {code: roomCode, pid: myPid}); if (!r.ok && r.error) alert(r.error); pollState(); }
async function submitQuestion() {
  const r = await postApi("/api/ask", {code: roomCode, pid: myPid, question: document.getElementById("inQuestion").value, answer: document.getElementById("inAnswer").value});
  if (!r.ok && r.error) return alert(r.error);
  document.getElementById("inQuestion").value = "";
  document.getElementById("inAnswer").value = "";
  playSfx(780, 0.15);
  pollState();
}
async function submitGuess() {
  await postApi("/api/answer", {code: roomCode, pid: myPid, guess: document.getElementById("inGuess").value});
  document.getElementById("inGuess").value = "";
  playSfx(660, 0.15);
  pollState();
}
async function sendJudge(correct) { await postApi("/api/judge", {code: roomCode, pid: myPid, correct}); playSfx(correct ? 920 : 220, 0.2); pollState(); }
async function contestResult() { await postApi("/api/contest", {code: roomCode, pid: myPid}); playSfx(440, 0.2); pollState(); }
async function resolveContest(decision) { await postApi("/api/resolve_contest", {code: roomCode, pid: myPid, decision}); pollState(); }
async function nextRound() { await postApi("/api/next", {code: roomCode, pid: myPid}); pollState(); }

async function pollState() {
  if (!roomCode) return;
  const r = await fetch(`/api/state?code=${roomCode}&pid=${myPid}`).then(x => x.json()).catch(() => null);
  if (!r || !r.ok) return;

  document.getElementById("rModePill").textContent = r.umpire ? "⚖ UMPIRE MODE" : "⚔ STANDARD MODE";
  const isHost = (myPid === r.host_pid);
  const isAsker = (myPid === r.asker_pid);
  const isGuesser = (myPid === r.guesser_pid);

  ["lobbyPanel","askPanel","answerPanel","judgePanel","resultPanel"].forEach(id => document.getElementById(id).classList.add("hidden"));

  if (r.phase === "lobby") {
    document.getElementById("lobbyPanel").classList.remove("hidden");
    document.getElementById("lobbyPlayers").innerHTML = r.players.map(p => `<div class="qb-item"><span>${p.name}</span>${isHost && p.pid !== myPid ? `<button type="button" class="btn-red" onclick="kickPlayer('${p.pid}')">Kick</button>` : ""}</div>`).join("");
    document.getElementById("btnStartMatch").classList.toggle("hidden", !isHost);
  } else if (r.phase === "asking") {
    document.getElementById("askPanel").classList.remove("hidden");
    document.getElementById("askHeader").textContent = `${r.asker_name} -> Asking ${r.guesser_name}`;
    document.getElementById("askerForm").classList.toggle("hidden", !isAsker);
    document.getElementById("askerWait").classList.toggle("hidden", isAsker);
    document.getElementById("waitAskerName").textContent = r.asker_name;
    if (isAsker) refreshPromptDropdown();
  } else if (r.phase === "answering") {
    document.getElementById("answerPanel").classList.remove("hidden");
    document.getElementById("turnBadge").textContent = `${r.guesser_name}'s Turn to Answer`;
    document.getElementById("displayQuestion").textContent = r.question;
    document.getElementById("digitHintBox").classList.toggle("hidden", !r.digit_hint);
    const tBox = document.getElementById("timerDisplay");
    tBox.textContent = r.remaining + "s";
    tBox.classList.toggle("timer-urgent", r.remaining <= 5);
    if (r.remaining <= 5 && r.remaining > 0) playSfx(520, 0.06);
    document.getElementById("guesserForm").classList.toggle("hidden", !isGuesser);
    document.getElementById("answerWait").classList.toggle("hidden", isGuesser);
    document.getElementById("activeGuesserName").textContent = r.guesser_name;
  } else if (r.phase === "judging") {
    document.getElementById("judgePanel").classList.remove("hidden");
    document.getElementById("jQuestion").textContent = r.question;
    document.getElementById("jSecret").textContent = r.secret_answer;
    document.getElementById("jGuess").textContent = r.last_guess;
    document.getElementById("jTime").textContent = r.last_time;
    document.getElementById("judgeBtns").classList.toggle("hidden", !isAsker);
    document.getElementById("judgeWait").classList.toggle("hidden", isAsker);
  } else if (r.phase === "round_result" || r.phase === "contest_review") {
    document.getElementById("resultPanel").classList.remove("hidden");
    document.getElementById("resTitle").textContent = r.phase === "contest_review" ? "⚠️ Answer Contested!" : "Round Result";
    document.getElementById("resDetail").textContent = `${r.result_msg} (Secret: ${r.secret_answer} | Guess: ${r.last_guess})`;
    const canContest = (!r.umpire && r.phase === "round_result" && !r.last_correct && isGuesser);
    document.getElementById("contestArea").classList.toggle("hidden", !canContest);
    document.getElementById("contestResolveArea").classList.toggle("hidden", !(r.phase === "contest_review" && isAsker));
    document.getElementById("btnNextRound").classList.toggle("hidden", !(r.phase === "round_result" && isAsker));
  } else if (r.phase === "finished") {
    document.getElementById("resultPanel").classList.remove("hidden");
    const win = r.leaderboard[0];
    document.getElementById("resTitle").textContent = "🏆 MATCH COMPLETE!";
    document.getElementById("resDetail").textContent = win ? `Champion: ${win.name} (${win.score} Pts in ${win.total_time}s)!` : "Game Over!";
    document.getElementById("contestArea").classList.add("hidden");
    document.getElementById("contestResolveArea").classList.add("hidden");
    document.getElementById("btnNextRound").classList.add("hidden");
    if (lastPhase !== "finished") playSfx(1040, 0.35);
  }
  lastPhase = r.phase;

  document.getElementById("leaderboardList").innerHTML = r.leaderboard.map((p, i) =>
    `<div class="qb-item"><span>#${i+1} <strong>${p.name}</strong></span><span><strong>${p.score} Pts</strong> <small style="color:var(--muted);">(${p.total_time}s)</small></span></div>`
  ).join("");
}

window.addEventListener("DOMContentLoaded", () => {
  startIntroSequence();
  const params = new URLSearchParams(location.search);
  const autoRoom = params.get("room");
  if (autoRoom) document.getElementById("jCode").value = autoRoom.toUpperCase();
});
(function() {
  const inp = document.querySelector('input[type="file"][accept*="audio"]');
  if (!inp) return;
  const host = inp.closest('label, button') || inp;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.id = 'resetThemeBtn';
  btn.textContent = '🔄 Default Theme';
  btn.style.cssText = 'display:none;background:#1e293b;color:#38bdf8;border:1px solid #38bdf8;padding:4px 10px;border-radius:999px;font-size:12px;cursor:pointer;margin-left:6px;';
  host.insertAdjacentElement('afterend', btn);

  inp.addEventListener('change', () => {
    btn.style.display = (inp.files && inp.files.length > 0) ? 'inline-block' : 'none';
  });

  btn.onclick = () => {
    inp.value = '';
    document.querySelectorAll('audio').forEach(a => {
      a.pause();
      a.src = '/media/theme.mp3';
      a.loop = true;
      a.load();
      a.play().catch(() => { if (window.unlockAudio) window.unlockAudio(); });
    });
    btn.style.display = 'none';
  };
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

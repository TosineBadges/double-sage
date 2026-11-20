import os
import random
import string
import time
from flask import Flask, request, jsonify, render_template_string, send_from_directory

app = Flask(__name__)
rooms = {}

STARTER_PROMPTS = [
    ("General", "What is the hardest natural substance on Earth?", "Diamond"),
    ("General", "Which planet in our solar system has the most moons?", "Saturn"),
    ("General", "What is the capital city of Australia?", "Canberra"),
    ("General", "How many bones are in an adult human body?", "206"),
    ("General", "Which ocean is the largest on Earth?", "Pacific Ocean"),
    ("Numbers", "In what year did the Titanic sink?", "1912"),
    ("Numbers", "How many minutes are in a full day?", "1440"),
    ("Numbers", "What year did the first human walk on the Moon?", "1969"),
    ("Numbers", "How many keys are on a standard full-size piano?", "88"),
    ("Sports", "How many players are on a standard soccer team on the field?", "11"),
    ("Sports", "Which country won the first FIFA World Cup in 1930?", "Uruguay"),
    ("Sports", "How many points is a touchdown worth in American football?", "6"),
    ("Movies", "Who directed the 1994 movie Pulp Fiction?", "Quentin Tarantino"),
    ("Movies", "What is the name of the fictional African country in Black Panther?", "Wakanda"),
    ("Science", "What is the chemical symbol for gold?", "Au"),
    ("Science", "What gas do plants absorb from the atmosphere?", "Carbon dioxide"),
]

def gen_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase, k=4))
        if code not in rooms:
            return code

def generate_hint(ans):
    words = len(ans.split())
    letters = sum(1 for c in ans if c.isalpha())
    digits = sum(1 for c in ans if c.isdigit())
    parts = [f"{words} {'word' if words == 1 else 'words'}", f"{letters} {'letter' if letters == 1 else 'letters'}"]
    if digits > 0:
        parts.append(f"{digits} {'digit' if digits == 1 else 'digits'}")
    return ", ".join(parts)

def build_turn_queue(room):
    players = [p["name"] for p in room["players"]]
    q_per_player = room["q_per_player"]
    queue = []
    if room["umpire_mode"]:
        for _ in range(q_per_player):
            for p in players:
                queue.append({"asker": room["host"], "guesser": p})
    else:
        n = len(players)
        for _ in range(q_per_player):
            for i in range(n):
                queue.append({"asker": players[i], "guesser": players[(i + 1) % n]})
    return queue

@app.route("/media/<path:filename>")
def serve_media(filename):
    base_name = os.path.splitext(filename)[0].lower()
    search_dirs = [os.getcwd(), os.path.join(os.getcwd(), "static")]
    aliases = {
        "double_sage_icon": ["double_sage_icon", "icon", "logo"],
        "double_sage_battle": ["double_sage_battle", "battle"],
        "double_sage_banner": ["double_sage_banner", "banner"],
        "double_sage_tournament": ["double_sage_tournament", "tournament"],
    }
    targets = aliases.get(base_name, [base_name])
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            name_no_ext, ext = os.path.splitext(f)
            if ext.lower() in [".jpg", ".jpeg", ".png", ".webp"] and name_no_ext.lower() in targets:
                return send_from_directory(d, f)
    return ("Not Found", 404)

@app.route("/api/create", methods=["POST"])
def create_room():
    data = request.json or {}
    host = (data.get("name") or "Host").strip()
    max_players = max(2, min(10, int(data.get("max_players", 2))))
    q_per_player = max(1, min(10, int(data.get("q_per_player", 3))))
    time_limit = max(10, min(60, int(data.get("time_limit", 30))))
    umpire_mode = bool(data.get("umpire_mode", False))

    code = gen_code()
    players = [] if umpire_mode else [{"name": host, "score": 0, "time_spent": 0.0}]
    rooms[code] = {
        "code": code,
        "host": host,
        "max_players": max_players,
        "q_per_player": q_per_player,
        "time_limit": time_limit,
        "umpire_mode": umpire_mode,
        "players": players,
        "state": "lobby",
        "queue": [],
        "turn_idx": 0,
        "current": None,
        "result": None,
        "contest": None,
    }
    return jsonify({"ok": True, "code": code, "room": rooms[code]})

@app.route("/api/join", methods=["POST"])
def join_room():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if code not in rooms:
        return jsonify({"ok": False, "error": "Room not found."})
    room = rooms[code]
    if room["umpire_mode"] and name == room["host"]:
        return jsonify({"ok": True, "room": room})
    existing = [p for p in room["players"] if p["name"].lower() == name.lower()]
    if existing:
        return jsonify({"ok": True, "room": room})
    if room["state"] != "lobby":
        return jsonify({"ok": False, "error": "Game already started."})
    if len(room["players"]) >= room["max_players"]:
        return jsonify({"ok": False, "error": "Room is full."})
    room["players"].append({"name": name, "score": 0, "time_spent": 0.0})
    return jsonify({"ok": True, "room": room})

@app.route("/api/kick", methods=["POST"])
def kick_player():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    host = data.get("host")
    target = data.get("target")
    room = rooms.get(code)
    if room and room["host"] == host and room["state"] == "lobby":
        room["players"] = [p for p in room["players"] if p["name"] != target]
    return jsonify({"ok": True, "room": room})

@app.route("/api/start", methods=["POST"])
def start_game():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    host = data.get("host")
    room = rooms.get(code)
    if not room or room["host"] != host:
        return jsonify({"ok": False, "error": "Unauthorized."})
    if len(room["players"]) < 2:
        return jsonify({"ok": False, "error": "Need at least 2 players to start."})
    room["queue"] = build_turn_queue(room)
    room["turn_idx"] = 0
    room["state"] = "asking"
    room["current"] = None
    room["result"] = None
    room["contest"] = None
    return jsonify({"ok": True, "room": room})

@app.route("/api/ask", methods=["POST"])
def submit_question():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    asker = data.get("asker")
    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    room = rooms.get(code)
    if not room or room["state"] != "asking":
        return jsonify({"ok": False, "error": "Invalid state."})
    turn = room["queue"][room["turn_idx"]]
    if turn["asker"] != asker or not question or not answer:
        return jsonify({"ok": False, "error": "Invalid input or turn."})
    room["current"] = {
        "asker": asker,
        "guesser": turn["guesser"],
        "question": question,
        "answer": answer,
        "hint": generate_hint(answer),
        "start_ts": time.time(),
    }
    room["state"] = "guessing"
    room["result"] = None
    room["contest"] = None
    return jsonify({"ok": True, "room": room})

@app.route("/api/guess", methods=["POST"])
def submit_guess():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    guesser = data.get("guesser")
    guess = (data.get("guess") or "").strip()
    timed_out = bool(data.get("timed_out", False))
    room = rooms.get(code)
    if not room or room["state"] != "guessing":
        return jsonify({"ok": True, "room": room})
    cur = room["current"]
    if cur["guesser"] != guesser:
        return jsonify({"ok": False, "error": "Not your turn."})
    elapsed = min(float(room["time_limit"]), round(time.time() - cur["start_ts"], 2))
    if timed_out:
        elapsed = float(room["time_limit"])
    correct = (not timed_out) and (guess.lower() == cur["answer"].lower())
    for p in room["players"]:
        if p["name"] == guesser:
            p["time_spent"] = round(p["time_spent"] + elapsed, 2)
            if correct:
                p["score"] += 5
        if not correct and not room["umpire_mode"] and p["name"] == cur["asker"]:
            p["score"] += 5
    room["result"] = {
        "correct": correct,
        "guess": "(Time Expired)" if timed_out else (guess or "(Blank)"),
        "answer": cur["answer"],
        "question": cur["question"],
        "asker": cur["asker"],
        "guesser": guesser,
        "elapsed": elapsed,
        "contested": False,
    }
    room["state"] = "result"
    return jsonify({"ok": True, "room": room})

@app.route("/api/contest", methods=["POST"])
def raise_contest():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    guesser = data.get("guesser")
    reason = (data.get("reason") or "My answer was right!").strip()
    room = rooms.get(code)
    if not room or room["state"] != "result" or room["umpire_mode"]:
        return jsonify({"ok": False, "error": "Cannot contest."})
    res = room["result"]
    if res["guesser"] != guesser or res["correct"] or res["contested"]:
        return jsonify({"ok": False, "error": "Invalid contest."})
    res["contested"] = True
    room["contest"] = {"guesser": guesser, "asker": res["asker"], "reason": reason}
    room["state"] = "contest"
    return jsonify({"ok": True, "room": room})

@app.route("/api/resolve_contest", methods=["POST"])
def resolve_contest():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    asker = data.get("asker")
    decision = data.get("decision") # "accept_guess" or "reask"
    room = rooms.get(code)
    if not room or room["state"] != "contest":
        return jsonify({"ok": False, "error": "No active contest."})
    res = room["result"]
    if res["asker"] != asker:
        return jsonify({"ok": False, "error": "Only the Asker can decide."})
    # Reverse the +5 originally given to Asker
    for p in room["players"]:
        if p["name"] == asker:
            p["score"] = max(0, p["score"] - 5)
    if decision == "accept_guess":
        for p in room["players"]:
            if p["name"] == res["guesser"]:
                p["score"] += 5
        res["correct"] = True
        room["contest"] = None
        room["state"] = "result"
    else:
        # Void round and re-ask fresh question
        for p in room["players"]:
            if p["name"] == res["guesser"]:
                p["time_spent"] = max(0.0, round(p["time_spent"] - res["elapsed"], 2))
        room["current"] = None
        room["result"] = None
        room["contest"] = None
        room["state"] = "asking"
    return jsonify({"ok": True, "room": room})

@app.route("/api/next", methods=["POST"])
def next_turn():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    room = rooms.get(code)
    if not room or room["state"] != "result":
        return jsonify({"ok": True, "room": room})
    room["turn_idx"] += 1
    if room["turn_idx"] >= len(room["queue"]):
        room["state"] = "gameover"
    else:
        room["state"] = "asking"
        room["current"] = None
        room["result"] = None
        room["contest"] = None
    return jsonify({"ok": True, "room": room})

@app.route("/api/state")
def get_state():
    code = (request.args.get("code") or "").upper()
    room = rooms.get(code)
    if not room:
        return jsonify({"ok": False, "error": "Room closed."})
    if room["state"] == "guessing" and room["current"]:
        elapsed = time.time() - room["current"]["start_ts"]
        if elapsed >= room["time_limit"]:
            # Auto-timeout
            cur = room["current"]
            guesser = cur["guesser"]
            tl = float(room["time_limit"])
            for p in room["players"]:
                if p["name"] == guesser:
                    p["time_spent"] = round(p["time_spent"] + tl, 2)
                if not room["umpire_mode"] and p["name"] == cur["asker"]:
                    p["score"] += 5
            room["result"] = {
                "correct": False,
                "guess": "(Time Expired)",
                "answer": cur["answer"],
                "question": cur["question"],
                "asker": cur["asker"],
                "guesser": guesser,
                "elapsed": tl,
                "contested": False,
            }
            room["state"] = "result"
    return jsonify({"ok": True, "room": room})

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Double Sage — Online Multiplayer</title>
<style>
  :root { --bg:#090d1a; --card:#12192e; --gold:#f5b73b; --teal:#22d3ee; --text:#f1f5f9; --muted:#94a3b8; --danger:#f43f5e; --ok:#10b981; }
  * { box-sizing:border-box; font-family:system-ui,-apple-system,sans-serif; }
  body { margin:0; background:var(--bg); color:var(--text); }
  .topbar { position:sticky; top:0; z-index:20; background:#0d1426; border-bottom:1px solid #1e293b; padding:10px 14px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; }
  .brand { display:flex; align-items:center; gap:8px; font-weight:800; color:var(--gold); font-size:1.1rem; }
  .brand img { width:32px; height:32px; border-radius:8px; object-fit:cover; }
  .audio-bar { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
  .pill { background:#1e293b; color:var(--text); border:1px solid #334155; border-radius:999px; padding:5px 10px; font-size:0.78rem; cursor:pointer; font-weight:600; }
  .pill.active { border-color:var(--teal); color:var(--teal); }
  input[type=range] { width:75px; accent-color:var(--gold); }
  .wrap { max-width:560px; margin:16px auto; padding:0 14px 40px; }
  .card { background:var(--card); border:1px solid #1e293b; border-radius:16px; padding:18px; margin-bottom:14px; box-shadow:0 10px 25px rgba(0,0,0,0.35); }
  h2, h3 { margin:0 0 10px; }
  label { display:block; font-size:0.82rem; color:var(--muted); margin:10px 0 4px; }
  input[type=text], input[type=number], select, textarea { width:100%; padding:11px; border-radius:10px; border:1px solid #334155; background:#0b1120; color:var(--text); font-size:0.95rem; }
  .btn { width:100%; padding:12px; border:none; border-radius:12px; font-weight:700; font-size:0.95rem; cursor:pointer; margin-top:10px; }
  .btn-gold { background:linear-gradient(135deg,#f5b73b,#d97706); color:#090d1a; }
  .btn-teal { background:linear-gradient(135deg,#22d3ee,#0284c7); color:#090d1a; }
  .btn-danger { background:var(--danger); color:#fff; }
  .btn-ok { background:var(--ok); color:#090d1a; }
  .btn-ghost { background:#1e293b; color:var(--text); }
  .row { display:flex; gap:8px; }
  .row > * { flex:1; }
  .code-box { font-size:2rem; font-weight:900; letter-spacing:6px; text-align:center; color:var(--gold); background:#090d1a; padding:12px; border-radius:12px; border:1px dashed var(--gold); margin:8px 0; }
  .hint-box { background:#0b1120; border-left:4px solid var(--teal); padding:10px 12px; border-radius:8px; color:var(--teal); font-weight:700; margin:10px 0; }
  .timer { font-size:1.8rem; font-weight:900; text-align:center; color:var(--gold); margin:6px 0; }
  .timer.urgent { color:var(--danger); animation:pulse 0.6s infinite; }
  @keyframes pulse { 50% { opacity:0.4; } }
  table { width:100%; border-collapse:collapse; margin-top:8px; font-size:0.9rem; }
  th, td { padding:8px; text-align:left; border-bottom:1px solid #1e293b; }
  th { color:var(--muted); font-size:0.78rem; }
  .hidden { display:none !important; }
  /* 4-Slide Intro Splash */
  #splash { position:fixed; inset:0; z-index:999; background:#050811; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:20px; text-align:center; }
  #splash img { max-width:92vw; max-height:62vh; border-radius:18px; border:2px solid var(--gold); box-shadow:0 0 35px rgba(245,183,59,0.3); object-fit:contain; }
  .dots { display:flex; gap:8px; margin:14px 0 8px; }
  .dot { width:10px; height:10px; border-radius:50%; background:#334155; }
  .dot.on { background:var(--gold); transform:scale(1.25); }
  .prog { width:240px; height:5px; background:#1e293b; border-radius:99px; overflow:hidden; margin-bottom:14px; }
  .prog-fill { height:100%; width:0%; background:linear-gradient(90deg,var(--gold),var(--teal)); transition:width 0.1s linear; }
  .qb-item { display:flex; justify-content:space-between; align-items:center; background:#0b1120; padding:8px 10px; border-radius:8px; margin-top:6px; font-size:0.85rem; }
</style>
</head>
<body>

<div id="splash">
  <img id="splashImg" src="/media/double_sage_icon.jpg" alt="Double Sage">
  <div id="splashLabel" style="color:var(--gold);font-weight:800;margin-top:10px;letter-spacing:1px;">DOUBLE SAGE</div>
  <div class="dots">
    <div class="dot on" id="d0"></div><div class="dot" id="d1"></div><div class="dot" id="d2"></div><div class="dot" id="d3"></div>
  </div>
  <div class="prog"><div class="prog-fill" id="progFill"></div></div>
  <div class="row" style="width:280px;">
    <button class="btn btn-gold" onclick="enableSoundAndSkip(false)" style="margin:0;">🔊 Sound On</button>
    <button class="btn btn-ghost" onclick="closeSplash()" style="margin:0;">Skip Intro</button>
  </div>
</div>

<div class="topbar">
  <div class="brand">
    <img src="/media/double_sage_icon.jpg" onerror="this.style.display='none'">
    <span>DOUBLE SAGE</span>
  </div>
  <div class="audio-bar">
    <button class="pill" onclick="startSplash()">🎬 Intro</button>
    <button class="pill active" id="musicBtn" onclick="toggleMusic()">🎵 Music: ON</button>
    <button class="pill active" id="sfxBtn" onclick="toggleSfx()">🔊 SFX: ON</button>
    <input type="range" id="volSlider" min="0" max="100" value="85" oninput="setVol(this.value)" title="Volume">
  </div>
</div>

<div class="wrap">
  <!-- HOME VIEW -->
  <div id="homeView">
    <div class="card">
      <div class="row" style="margin-bottom:10px;">
        <button class="btn btn-gold" onclick="showTab('createTab')" style="margin:0;">Create Room</button>
        <button class="btn btn-teal" onclick="showTab('joinTab')" style="margin:0;">Join Room</button>
        <button class="btn btn-ghost" onclick="toggleQBModal()" style="margin:0;">📚 My QB's</button>
      </div>

      <div id="createTab">
        <h3>Host a New Match</h3>
        <label>Your Name</label>
        <input type="text" id="hostName" placeholder="Enter your name">
        <div class="row">
          <div>
            <label>Players (2-10)</label>
            <input type="number" id="maxPlayers" min="2" max="10" value="2">
          </div>
          <div>
            <label>Questions / Player</label>
            <input type="number" id="qPerPlayer" min="1" max="10" value="3">
          </div>
        </div>
        <label>Time Limit: <span id="tlVal" style="color:var(--gold);font-weight:700;">30</span> seconds</label>
        <input type="range" id="timeLimit" min="10" max="60" value="30" style="width:100%;" oninput="document.getElementById('tlVal').textContent=this.value">
        <label style="display:flex;align-items:center;gap:8px;margin-top:12px;color:var(--text);cursor:pointer;">
          <input type="checkbox" id="umpireMode" style="width:auto;">
          <span><b>Umpire Mode</b> (You organize & set questions only; ruling is always final)</span>
        </label>
        <button class="btn btn-gold" onclick="createRoom()">Generate Room Code</button>
      </div>

      <div id="joinTab" class="hidden">
        <h3>Join Existing Room</h3>
        <label>Your Name</label>
        <input type="text" id="joinName" placeholder="Enter your name">
        <label>4-Letter Room Code</label>
        <input type="text" id="joinCode" maxlength="4" placeholder="e.g. SAGE" style="text-transform:uppercase;">
        <button class="btn btn-teal" onclick="joinRoom()">Join Match</button>
      </div>
    </div>

    <!-- MY QB's MANAGER -->
    <div id="qbCard" class="card hidden">
      <h3>📚 My QB's (Saved Question Banks)</h3>
      <p style="font-size:0.82rem;color:var(--muted);margin:0 0 8px;">Save your favorite questions & answers on this device to load them with one tap during any round.</p>
      <input type="text" id="qbNewQ" placeholder="New Question...">
      <input type="text" id="qbNewA" placeholder="Secret Answer..." style="margin-top:6px;">
      <button class="btn btn-teal" onclick="addQBItem()">+ Add to My QB's</button>
      <div id="qbList" style="margin-top:10px;"></div>
    </div>
  </div>

  <!-- ROOM VIEW -->
  <div id="roomView" class="hidden">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="color:var(--muted);font-size:0.85rem;">ROOM: <b id="roomCodeBadge" style="color:var(--gold);"></b></span>
        <span id="modeBadge" style="font-size:0.78rem;color:var(--teal);font-weight:700;"></span>
      </div>

      <!-- LOBBY -->
      <div id="lobbySec" class="hidden">
        <div class="code-box" id="lobbyCode"></div>
        <button class="btn btn-ghost" onclick="copyInvite()">🔗 Copy One-Tap Invite Link</button>
        <div id="lobbyPlayers" style="margin-top:12px;"></div>
        <button id="startBtn" class="btn btn-gold hidden" onclick="startGame()">Start Match</button>
        <p id="waitHostMsg" class="hidden" style="text-align:center;color:var(--muted);font-size:0.88rem;">Waiting for host to start...</p>
      </div>

      <!-- ASKING -->
      <div id="askSec" class="hidden">
        <h3 id="askHeader"></h3>
        <div id="askerForm" class="hidden">
          <div class="row">
            <select id="qbSelect" onchange="loadFromQBSelect()">
              <option value="">-- Load from My QB's --</option>
            </select>
            <button class="btn btn-ghost" onclick="loadNextUnusedQB()" style="margin:0;flex:0.7;">⚡ Next QB</button>
          </div>
          <select id="starterSelect" onchange="loadFromStarter()" style="margin-top:8px;">
            <option value="">-- Or Pick & Edit a Starter Prompt --</option>
          </select>
          <label>Question (Editable)</label>
          <textarea id="qInput" rows="2" placeholder="Type or edit your question..."></textarea>
          <label>Secret Answer (Editable)</label>
          <input type="text" id="aInput" placeholder="Exact answer...">
          <div class="row">
            <button class="btn btn-ghost" onclick="saveCurrentToQB()">💾 Save to QB's</button>
            <button class="btn btn-gold" onclick="submitQuestion()">Lock In Question</button>
          </div>
        </div>
        <p id="waitAskerMsg" class="hidden" style="color:var(--muted);text-align:center;padding:16px 0;"></p>
      </div>

      <!-- GUESSING -->
      <div id="guessSec" class="hidden">
        <div class="timer" id="timerDisplay">30s</div>
        <div style="font-size:0.85rem;color:var(--muted);">Question for <b id="guesserLabel" style="color:var(--gold);"></b>:</div>
        <h3 id="liveQuestion" style="margin-top:6px;"></h3>
        <div class="hint-box" id="liveHint"></div>
        <div id="guesserForm" class="hidden">
          <input type="text" id="guessInput" placeholder="Type your guess fast...">
          <button class="btn btn-teal" onclick="submitGuess(false)">Submit Guess</button>
        </div>
        <p id="waitGuesserMsg" class="hidden" style="color:var(--muted);text-align:center;"></p>
      </div>

      <!-- RESULT -->
      <div id="resultSec" class="hidden">
        <h3 id="resBanner"></h3>
        <p style="font-size:0.9rem;margin:6px 0;"><b>Question:</b> <span id="resQ"></span></p>
        <p style="font-size:0.9rem;margin:6px 0;"><b>Guess:</b> <span id="resGuess"></span> | <b>Answer:</b> <span id="resAns" style="color:var(--gold);"></span></p>
        <p style="font-size:0.82rem;color:var(--muted);" id="resTime"></p>
        <div id="contestTriggerBox" class="hidden" style="margin-top:10px;padding-top:10px;border-top:1px solid #1e293b;">
          <input type="text" id="contestReason" placeholder="Why was your answer right? (Optional)">
          <button class="btn btn-danger" onclick="raiseContest()">⚖️ CONTEST ANSWER</button>
        </div>
        <button id="nextBtn" class="btn btn-gold hidden" onclick="nextTurn()">Next Round →</button>
      </div>

      <!-- CONTEST APPROVAL -->
      <div id="contestSec" class="hidden">
        <h3 style="color:var(--gold);">⚖️ Answer Contested!</h3>
        <p id="contestDetails" style="font-size:0.9rem;"></p>
        <div id="askerDecisionBox" class="hidden">
          <button class="btn btn-ok" onclick="resolveContest('accept_guess')">✅ Accept Guess (+5 Pts to Guesser)</button>
          <button class="btn btn-danger" onclick="resolveContest('reask')">🔄 Send New Question (0 Pts & Re-Ask)</button>
        </div>
        <p id="waitDecisionMsg" class="hidden" style="color:var(--muted);text-align:center;"></p>
      </div>

      <!-- GAME OVER -->
      <div id="overSec" class="hidden">
        <h2 style="color:var(--gold);text-align:center;">🏆 MATCH COMPLETE!</h2>
        <p id="winnerBanner" style="text-align:center;font-weight:800;font-size:1.1rem;"></p>
        <button class="btn btn-gold" onclick="location.href='/'">Play Again</button>
      </div>
    </div>

    <!-- SCOREBOARD -->
    <div class="card">
      <h3>📊 Live Scoreboard (Tie-Breaker: Shortest Time)</h3>
      <table>
        <thead><tr><th>Rank</th><th>Player</th><th>Points</th><th>Time Spent</th></tr></thead>
        <tbody id="scoreBody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const STARTERS = {{ starters | tojson }};
let myName = "", roomCode = "", lastState = "", pollTimer = null, usedQBs = new Set();

// --- AUDIO ENGINE (LOUD SYNTH MUSIC + SFX) ---
let audioCtx = null, masterGain = null, musicOn = true, sfxOn = true, volume = 0.85, beatTimer = null, step = 0;
function initAudio() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    masterGain = audioCtx.createGain();
    masterGain.gain.value = volume;
    masterGain.connect(audioCtx.destination);
  }
  if (audioCtx.state === "suspended") audioCtx.resume();
}
function setVol(v) {
  volume = v / 100;
  if (masterGain) masterGain.gain.value = volume;
}
function toggleMusic() {
  initAudio();
  musicOn = !musicOn;
  const b = document.getElementById("musicBtn");
  b.textContent = musicOn ? "🎵 Music: ON" : "🎵 Music: OFF";
  b.classList.toggle("active", musicOn);
}
function toggleSfx() {
  initAudio();
  sfxOn = !sfxOn;
  const b = document.getElementById("sfxBtn");
  b.textContent = sfxOn ? "🔊 SFX: ON" : "🔊 SFX: OFF";
  b.classList.toggle("active", sfxOn);
}
function playTone(freq, dur, type="triangle", gainVal=0.45) {
  if (!sfxOn) return;
  initAudio();
  const osc = audioCtx.createOscillator();
  const g = audioCtx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
  g.gain.setValueAtTime(gainVal, audioCtx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
  osc.connect(g); g.connect(masterGain);
  osc.start(); osc.stop(audioCtx.currentTime + dur);
}
function startBgMusic() {
  if (beatTimer) return;
  const notes = [130.81, 164.81, 196.00, 261.63, 196.00, 164.81, 146.83, 220.00];
  beatTimer = setInterval(() => {
    if (!musicOn || !audioCtx || audioCtx.state !== "running") return;
    const osc = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(notes[step % notes.length], audioCtx.currentTime);
    g.gain.setValueAtTime(0.22, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.24);
    osc.connect(g); g.connect(masterGain);
    osc.start(); osc.stop(audioCtx.currentTime + 0.25);
    step++;
  }, 280);
}

// --- 4-SLIDE INTRO SPLASH (3 SECONDS EACH) ---
const SLIDES = [
  { src: "/media/double_sage_icon.jpg", label: "DOUBLE SAGE" },
  { src: "/media/double_sage_battle.jpg", label: "1v1 BATTLE OF WITS" },
  { src: "/media/double_sage_banner.jpg", label: "OUTSMART • OUTGUESS • OUTSCORE" },
  { src: "/media/double_sage_tournament.jpg", label: "2 TO 10 PLAYERS • FASTEST WINS" }
];
let splashInterval = null;
function startSplash() {
  const sp = document.getElementById("splash");
  sp.classList.remove("hidden");
  let idx = 0, elapsed = 0;
  const totalPerSlide = 3000;
  function showSlide(i) {
    document.getElementById("splashImg").src = SLIDES[i].src;
    document.getElementById("splashLabel").textContent = SLIDES[i].label;
    for (let d = 0; d < 4; d++) document.getElementById("d" + d).classList.toggle("on", d === i);
  }
  showSlide(0);
  if (splashInterval) clearInterval(splashInterval);
  splashInterval = setInterval(() => {
    elapsed += 100;
    document.getElementById("progFill").style.width = ((elapsed % totalPerSlide) / totalPerSlide * 100) + "%";
    if (elapsed >= totalPerSlide * (idx + 1)) {
      idx++;
      if (idx >= SLIDES.length) { closeSplash(); return; }
      showSlide(idx);
    }
  }, 100);
}
function enableSoundAndSkip(closeAfter) {
  initAudio(); startBgMusic(); playTone(523.25, 0.25);
  if (closeAfter) closeSplash();
}
function closeSplash() {
  if (splashInterval) clearInterval(splashInterval);
  document.getElementById("splash").classList.add("hidden");
  initAudio(); startBgMusic();
}

// --- QB's (SAVED QUESTION BANKS) ---
function getQBs() {
  try { return JSON.parse(localStorage.getItem("ds_qbs") || "[]"); } catch { return []; }
}
function saveQBs(list) {
  localStorage.setItem("ds_qbs", JSON.stringify(list));
  renderQBList(); refreshQBDropdown();
}
function toggleQBModal() {
  document.getElementById("qbCard").classList.toggle("hidden");
  renderQBList();
}
function addQBItem() {
  const q = document.getElementById("qbNewQ").value.trim();
  const a = document.getElementById("qbNewA").value.trim();
  if (!q || !a) return alert("Enter both question and answer.");
  const list = getQBs();
  list.push({ q, a });
  saveQBs(list);
  document.getElementById("qbNewQ").value = "";
  document.getElementById("qbNewA").value = "";
  playTone(659.25, 0.2);
}
function deleteQBItem(i) {
  const list = getQBs(); list.splice(i, 1); saveQBs(list);
}
function renderQBList() {
  const list = getQBs();
  const el = document.getElementById("qbList");
  el.innerHTML = list.length ? "" : "<p style='color:var(--muted);font-size:0.82rem;'>No saved QB's yet.</p>";
  list.forEach((item, i) => {
    el.innerHTML += `<div class="qb-item"><div><b>${item.q}</b><br><span style="color:var(--gold);font-size:0.78rem;">Ans: ${item.a}</span></div><button class="pill" onclick="deleteQBItem(${i})">✕</button></div>`;
  });
}
function refreshQBDropdown() {
  const sel = document.getElementById("qbSelect");
  const curVal = sel.value;
  const list = getQBs();
  sel.innerHTML = `<option value="">-- Load from My QB's (${list.length}) --</option>`;
  list.forEach((item, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = (usedQBs.has(i) ? "✓ " : "") + item.q.slice(0, 48);
    sel.appendChild(opt);
  });
  sel.value = curVal;
}
function loadFromQBSelect() {
  const idx = document.getElementById("qbSelect").value;
  if (idx === "") return;
  const item = getQBs()[idx];
  if (item) {
    document.getElementById("qInput").value = item.q;
    document.getElementById("aInput").value = item.a;
    usedQBs.add(Number(idx));
    playTone(587.33, 0.15);
  }
}
function loadNextUnusedQB() {
  const list = getQBs();
  if (!list.length) return alert("Your QB bank is empty! Add questions under My QB's first.");
  let idx = list.findIndex((_, i) => !usedQBs.has(i));
  if (idx === -1) { usedQBs.clear(); idx = 0; }
  usedQBs.add(idx);
  document.getElementById("qInput").value = list[idx].q;
  document.getElementById("aInput").value = list[idx].a;
  refreshQBDropdown();
  playTone(659.25, 0.15);
}
function saveCurrentToQB() {
  const q = document.getElementById("qInput").value.trim();
  const a = document.getElementById("aInput").value.trim();
  if (!q || !a) return alert("Type a question and answer first.");
  const list = getQBs();
  list.push({ q, a });
  saveQBs(list);
  alert("Saved to My QB's!");
}
function initStarterDropdown() {
  const sel = document.getElementById("starterSelect");
  STARTERS.forEach((s, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = `[${s[0]}] ${s[1].slice(0, 45)}`;
    sel.appendChild(opt);
  });
}
function loadFromStarter() {
  const idx = document.getElementById("starterSelect").value;
  if (idx === "") return;
  const s = STARTERS[idx];
  document.getElementById("qInput").value = s[1];
  document.getElementById("aInput").value = s[2];
  playTone(523.25, 0.15);
}

// --- ROOM & GAMEPLAY ---
function showTab(id) {
  document.getElementById("createTab").classList.toggle("hidden", id !== "createTab");
  document.getElementById("joinTab").classList.toggle("hidden", id !== "joinTab");
}
async function api(url, body) {
  const res = await fetch(url, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
  return res.json();
}
async function createRoom() {
  initAudio(); startBgMusic();
  myName = document.getElementById("hostName").value.trim() || "Host";
  const data = await api("/api/create", {
    name: myName,
    max_players: document.getElementById("maxPlayers").value,
    q_per_player: document.getElementById("qPerPlayer").value,
    time_limit: document.getElementById("timeLimit").value,
    umpire_mode: document.getElementById("umpireMode").checked
  });
  if (data.ok) enterRoom(data.room);
}
async function joinRoom() {
  initAudio(); startBgMusic();
  myName = document.getElementById("joinName").value.trim();
  const code = document.getElementById("joinCode").value.trim().toUpperCase();
  if (!myName || !code) return alert("Enter your name and 4-letter room code.");
  const data = await api("/api/join", { name: myName, code });
  if (!data.ok) return alert(data.error);
  enterRoom(data.room);
}
function enterRoom(room) {
  roomCode = room.code;
  document.getElementById("homeView").classList.add("hidden");
  document.getElementById("roomView").classList.remove("hidden");
  renderRoom(room);
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const r = await fetch(`/api/state?code=${roomCode}`).then(x => x.json());
    if (r.ok) renderRoom(r.room);
  }, 1200);
}
function copyInvite() {
  const link = `${location.origin}/?room=${roomCode}`;
  navigator.clipboard.writeText(link);
  alert("Invite link copied! Share it with friends:\n" + link);
}
async function kickPlayer(target) {
  const data = await api("/api/kick", { code: roomCode, host: myName, target });
  if (data.ok) renderRoom(data.room);
}
async function startGame() {
  const data = await api("/api/start", { code: roomCode, host: myName });
  if (!data.ok) return alert(data.error);
  playTone(659.25, 0.3);
  renderRoom(data.room);
}
async function submitQuestion() {
  const q = document.getElementById("qInput").value.trim();
  const a = document.getElementById("aInput").value.trim();
  if (!q || !a) return alert("Enter both question and answer.");
  const data = await api("/api/ask", { code: roomCode, asker: myName, question: q, answer: a });
  if (!data.ok) return alert(data.error);
  document.getElementById("qInput").value = "";
  document.getElementById("aInput").value = "";
  playTone(783.99, 0.25);
  renderRoom(data.room);
}
async function submitGuess(timedOut) {
  const g = document.getElementById("guessInput").value.trim();
  const data = await api("/api/guess", { code: roomCode, guesser: myName, guess: g, timed_out: timedOut });
  document.getElementById("guessInput").value = "";
  if (data.ok) renderRoom(data.room);
}
async function raiseContest() {
  const reason = document.getElementById("contestReason").value.trim();
  const data = await api("/api/contest", { code: roomCode, guesser: myName, reason });
  if (data.ok) { playTone(330, 0.3, "sawtooth"); renderRoom(data.room); }
}
async function resolveContest(decision) {
  const data = await api("/api/resolve_contest", { code: roomCode, asker: myName, decision });
  if (data.ok) renderRoom(data.room);
}
async function nextTurn() {
  const data = await api("/api/next", { code: roomCode });
  if (data.ok) renderRoom(data.room);
}

let lastBeepSec = -1;
function renderRoom(room) {
  document.getElementById("roomCodeBadge").textContent = room.code;
  document.getElementById("modeBadge").textContent = room.umpire_mode ? `UMPIRE: ${room.host}` : `${room.time_limit}s LIMIT`;

  // Scoreboard sorted by highest points, then shortest time spent
  const sorted = [...room.players].sort((a, b) => (b.score - a.score) || (a.time_spent - b.time_spent));
  document.getElementById("scoreBody").innerHTML = sorted.map((p, i) =>
    `<tr><td>#${i+1}</td><td><b>${p.name}</b></td><td style="color:var(--gold);font-weight:700;">${p.score} pts</td><td>${p.time_spent.toFixed(1)}s</td></tr>`
  ).join("");

  ["lobbySec","askSec","guessSec","resultSec","contestSec","overSec"].forEach(id => document.getElementById(id).classList.add("hidden"));

  const stateKey = `${room.state}_${room.turn_idx}`;
  if (stateKey !== lastState) {
    lastState = stateKey;
    if (room.state === "result" && room.result) {
      room.result.correct ? playTone(880, 0.35) : playTone(196, 0.35, "sawtooth");
    }
    if (room.state === "asking") { refreshQBDropdown(); }
  }

  if (room.state === "lobby") {
    document.getElementById("lobbySec").classList.remove("hidden");
    document.getElementById("lobbyCode").textContent = room.code;
    const isHost = (myName === room.host);
    document.getElementById("lobbyPlayers").innerHTML = room.players.map(p =>
      `<div class="qb-item"><span>👤 <b>${p.name}</b></span>${isHost && p.name !== myName ? `<button class="pill" onclick="kickPlayer('${p.name}')">Kick</button>` : ""}</div>`
    ).join("");
    document.getElementById("startBtn").classList.toggle("hidden", !isHost);
    document.getElementById("waitHostMsg").classList.toggle("hidden", isHost);
  }
  else if (room.state === "asking") {
    document.getElementById("askSec").classList.remove("hidden");
    const turn = room.queue[room.turn_idx];
    document.getElementById("askHeader").textContent = `Round ${room.turn_idx + 1}/${room.queue.length}: ${turn.asker} → ${turn.guesser}`;
    const isAsker = (myName === turn.asker);
    // Do NOT touch inputs while Asker is typing/selecting!
    document.getElementById("askerForm").classList.toggle("hidden", !isAsker);
    document.getElementById("waitAskerMsg").classList.toggle("hidden", isAsker);
    if (!isAsker) document.getElementById("waitAskerMsg").textContent = `Waiting for ${turn.asker} to set a question for ${turn.guesser}...`;
  }
  else if (room.state === "guessing") {
    document.getElementById("guessSec").classList.remove("hidden");
    const cur = room.current;
    const rem = Math.max(0, Math.ceil(room.time_limit - (Date.now()/1000 - cur.start_ts)));
    const tEl = document.getElementById("timerDisplay");
    tEl.textContent = rem + "s";
    tEl.classList.toggle("urgent", rem <= 5);
    if (rem <= 5 && rem > 0 && rem !== lastBeepSec) { lastBeepSec = rem; playTone(987.77, 0.08); }
    document.getElementById("guesserLabel").textContent = cur.guesser;
    document.getElementById("liveQuestion").textContent = cur.question;
    document.getElementById("liveHint").textContent = "MANAGER HINT: " + cur.hint;
    const isGuesser = (myName === cur.guesser);
    document.getElementById("guesserForm").classList.toggle("hidden", !isGuesser);
    document.getElementById("waitGuesserMsg").classList.toggle("hidden", isGuesser);
    if (!isGuesser) document.getElementById("waitGuesserMsg").textContent = `${cur.guesser} is guessing...`;
  }
  else if (room.state === "result") {
    document.getElementById("resultSec").classList.remove("hidden");
    const res = room.result;
    const b = document.getElementById("resBanner");
    b.textContent = res.correct ? `✅ SPOT ON! +5 Pts to ${res.guesser}` : (room.umpire_mode ? `❌ WRONG! Umpire's Ruling is Final` : `❌ WRONG! +5 Pts to ${res.asker}`);
    b.style.color = res.correct ? "var(--ok)" : "var(--danger)";
    document.getElementById("resQ").textContent = res.question;
    document.getElementById("resGuess").textContent = res.guess;
    document.getElementById("resAns").textContent = res.answer;
    document.getElementById("resTime").textContent = `Time taken: ${res.elapsed.toFixed(1)}s`;
    const canContest = (!room.umpire_mode && !res.correct && !res.contested && myName === res.guesser);
    document.getElementById("contestTriggerBox").classList.toggle("hidden", !canContest);
    const canAdvance = (myName === res.asker || myName === room.host);
    document.getElementById("nextBtn").classList.toggle("hidden", !canAdvance);
  }
  else if (room.state === "contest") {
    document.getElementById("contestSec").classList.remove("hidden");
    const c = room.contest;
    document.getElementById("contestDetails").innerHTML = `<b>${c.guesser}</b> contested the result!<br>Reason: <i>"${c.reason}"</i><br>Asker (<b>${c.asker}</b>) must decide:`;
    const isAsker = (myName === c.asker);
    document.getElementById("askerDecisionBox").classList.toggle("hidden", !isAsker);
    document.getElementById("waitDecisionMsg").classList.toggle("hidden", isAsker);
    if (!isAsker) document.getElementById("waitDecisionMsg").textContent = `Waiting for ${c.asker} to accept the guess or send a new question...`;
  }
  else if (room.state === "gameover") {
    document.getElementById("overSec").classList.remove("hidden");
    if (sorted.length) {
      document.getElementById("winnerBanner").textContent = `👑 ${sorted[0].name} wins with ${sorted[0].score} pts (${sorted[0].time_spent.toFixed(1)}s)!`;
    }
  }
}

window.onload = () => {
  initStarterDropdown();
  const params = new URLSearchParams(location.search);
  if (params.get("room")) {
    showTab("joinTab");
    document.getElementById("joinCode").value = params.get("room").toUpperCase();
  }
  startSplash();
};
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE, starters=STARTER_PROMPTS)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

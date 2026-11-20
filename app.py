import os
import random
import string
import time
from flask import Flask, request, jsonify, send_from_directory, abort

app = Flask(__name__)

# In-memory store for active rooms
rooms = {}

STARTER_PROMPTS = [
    {"cat": "General", "q": "What is the capital city of Australia?", "a": "Canberra"},
    {"cat": "General", "q": "Which planet is known as the Red Planet?", "a": "Mars"},
    {"cat": "General", "q": "How many continents are there on Earth?", "a": "7"},
    {"cat": "Numbers", "q": "In what year did humans first land on the Moon?", "a": "1969"},
    {"cat": "Numbers", "q": "How many minutes are in 2 hours?", "a": "120"},
    {"cat": "Numbers", "q": "What is the boiling point of water in Celsius?", "a": "100"},
    {"cat": "Sports", "q": "How many players are on a standard football (soccer) team on the pitch?", "a": "11"},
    {"cat": "Sports", "q": "Which country won the 2022 FIFA World Cup?", "a": "Argentina"},
    {"cat": "Sports", "q": "How many rings are on the Olympic flag?", "a": "5"},
    {"cat": "Movies", "q": "Who directed the movie Inception?", "a": "Christopher Nolan"},
    {"cat": "Movies", "q": "What is the name of Batman's home city?", "a": "Gotham City"},
    {"cat": "Science", "q": "What is the chemical symbol for Gold?", "a": "Au"},
    {"cat": "Science", "q": "How many bones are in an adult human body?", "a": "206"}
]

ALLOWED_IMAGES = {
    "double_sage_icon.png",
    "double_sage_banner.png",
    "double_sage_battle.png",
    "double_sage_tournament.png",
    "double_sage_icon.jpg",
    "double_sage_banner.jpg",
    "double_sage_battle.jpg",
    "double_sage_tournament.jpg"
}


def generate_room_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if code not in rooms:
            return code


def generate_manager_hint(answer):
    words = answer.strip().split()
    word_count = len(words)
    letter_count = sum(1 for ch in answer if ch.isalpha())
    digit_count = sum(1 for ch in answer if ch.isdigit())

    parts = [
        f"{word_count} {'word' if word_count == 1 else 'words'}",
        f"{letter_count} {'letter' if letter_count == 1 else 'letters'}"
    ]
    if digit_count > 0:
        parts.append(f"{digit_count} {'digit' if digit_count == 1 else 'digits'}")
    return ", ".join(parts)


def normalize_text(txt):
    return "".join(ch.lower() for ch in txt.strip() if ch.isalnum() or ch.isspace()).strip()


def build_turn_queue(room):
    players = room["players"]
    q_per_player = room["questions_per_player"]
    umpire_id = room["umpire_id"]
    queue = []

    if umpire_id:
        for _ in range(q_per_player):
            for p in players:
                queue.append({"asker_id": umpire_id, "guesser_id": p["id"]})
    else:
        n = len(players)
        for r in range(q_per_player):
            for i in range(n):
                guesser = players[i]
                asker = players[(i + 1 + (r % (n - 1))) % n]
                queue.append({"asker_id": asker["id"], "guesser_id": guesser["id"]})
    return queue


def get_player_name(room, pid):
    if pid == room["umpire_id"]:
        return room["umpire_name"]
    for p in room["players"]:
        if p["id"] == pid:
            return p["name"]
    return "Unknown"


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    if filename not in ALLOWED_IMAGES:
        abort(404)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(base_dir, filename)):
        return send_from_directory(base_dir, filename)
    static_dir = os.path.join(base_dir, "static")
    if os.path.exists(os.path.join(static_dir, filename)):
        return send_from_directory(static_dir, filename)
    abort(404)


@app.route("/")
def index():
    return HTML_TEMPLATE


@app.route("/api/create_room", methods=["POST"])
def create_room():
    data = request.json or {}
    host_name = (data.get("name") or "Host").strip()[:20]
    max_players = max(2, min(10, int(data.get("max_players", 2))))
    q_per_player = max(1, min(10, int(data.get("questions_per_player", 3))))
    time_limit = max(10, min(60, int(data.get("time_limit", 30))))
    is_umpire = bool(data.get("is_umpire", False))

    code = generate_room_code()
    host_id = "p_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

    room = {
        "code": code,
        "host_id": host_id,
        "max_players": max_players,
        "questions_per_player": q_per_player,
        "time_limit": time_limit,
        "umpire_id": host_id if is_umpire else None,
        "umpire_name": host_name if is_umpire else None,
        "players": [] if is_umpire else [{"id": host_id, "name": host_name, "score": 0, "time": 0.0}],
        "status": "LOBBY",
        "queue": [],
        "turn_idx": 0,
        "current_q": "",
        "current_a": "",
        "current_hint": "",
        "turn_start_ts": 0.0,
        "last_guess": "",
        "last_correct": False,
        "last_elapsed": 0.0,
        "contest_reason": ""
    }
    rooms[code] = room
    return jsonify({"ok": True, "code": code, "player_id": host_id})


@app.route("/api/join_room", methods=["POST"])
def join_room():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "Player").strip()[:20]

    room = rooms.get(code)
    if not room:
        return jsonify({"ok": False, "error": "Room not found."})
    if room["status"] != "LOBBY":
        return jsonify({"ok": False, "error": "Game already started."})
    if len(room["players"]) >= room["max_players"]:
        return jsonify({"ok": False, "error": "Room is full."})

    pid = "p_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    room["players"].append({"id": pid, "name": name, "score": 0, "time": 0.0})
    return jsonify({"ok": True, "code": code, "player_id": pid})


@app.route("/api/kick_player", methods=["POST"])
def kick_player():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    host_id = data.get("host_id")
    target_id = data.get("target_id")

    room = rooms.get(code)
    if not room or room["host_id"] != host_id or room["status"] != "LOBBY":
        return jsonify({"ok": False})

    room["players"] = [p for p in room["players"] if p["id"] != target_id]
    return jsonify({"ok": True})


@app.route("/api/start_game", methods=["POST"])
def start_game():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    host_id = data.get("host_id")

    room = rooms.get(code)
    if not room or room["host_id"] != host_id:
        return jsonify({"ok": False, "error": "Unauthorized."})
    if len(room["players"]) < 2:
        return jsonify({"ok": False, "error": "Need at least 2 competing players."})

    room["queue"] = build_turn_queue(room)
    room["turn_idx"] = 0
    room["status"] = "ASKING"
    return jsonify({"ok": True})


@app.route("/api/submit_question", methods=["POST"])
def submit_question():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    pid = data.get("player_id")
    q = (data.get("question") or "").strip()
    a = (data.get("answer") or "").strip()

    room = rooms.get(code)
    if not room or room["status"] != "ASKING" or not q or not a:
        return jsonify({"ok": False})

    turn = room["queue"][room["turn_idx"]]
    if turn["asker_id"] != pid:
        return jsonify({"ok": False})

    room["current_q"] = q
    room["current_a"] = a
    room["current_hint"] = generate_manager_hint(a)
    room["turn_start_ts"] = time.time()
    room["status"] = "GUESSING"
    return jsonify({"ok": True})


@app.route("/api/submit_guess", methods=["POST"])
def submit_guess():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    pid = data.get("player_id")
    guess = (data.get("guess") or "").strip()

    room = rooms.get(code)
    if not room or room["status"] != "GUESSING":
        return jsonify({"ok": False})

    turn = room["queue"][room["turn_idx"]]
    if turn["guesser_id"] != pid:
        return jsonify({"ok": False})

    elapsed = min(float(room["time_limit"]), round(time.time() - room["turn_start_ts"], 2))
    is_correct = (normalize_text(guess) == normalize_text(room["current_a"])) and len(normalize_text(guess)) > 0

    room["last_guess"] = guess if guess else "(No Answer / Time Up)"
    room["last_correct"] = is_correct
    room["last_elapsed"] = elapsed

    for p in room["players"]:
        if p["id"] == turn["guesser_id"]:
            p["time"] = round(p["time"] + elapsed, 2)
            if is_correct:
                p["score"] += 5
        elif not room["umpire_id"] and p["id"] == turn["asker_id"] and not is_correct:
            p["score"] += 5

    room["status"] = "RESULT"
    return jsonify({"ok": True})


@app.route("/api/raise_contest", methods=["POST"])
def raise_contest():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    pid = data.get("player_id")
    reason = (data.get("reason") or "Answer matches meaning/spelling").strip()[:120]

    room = rooms.get(code)
    if not room or room["status"] != "RESULT" or room["umpire_id"] or room["last_correct"]:
        return jsonify({"ok": False})

    turn = room["queue"][room["turn_idx"]]
    if turn["guesser_id"] != pid:
        return jsonify({"ok": False})

    room["contest_reason"] = reason
    room["status"] = "CONTEST"
    return jsonify({"ok": True})


@app.route("/api/resolve_contest", methods=["POST"])
def resolve_contest():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    pid = data.get("player_id")
    decision = data.get("decision")  # "ACCEPT_GUESS" or "NEW_QUESTION"

    room = rooms.get(code)
    if not room or room["status"] != "CONTEST":
        return jsonify({"ok": False})

    turn = room["queue"][room["turn_idx"]]
    if turn["asker_id"] != pid:
        return jsonify({"ok": False})

    # Undo the temporary +5 awarded to Asker
    for p in room["players"]:
        if p["id"] == turn["asker_id"]:
            p["score"] = max(0, p["score"] - 5)

    if decision == "ACCEPT_GUESS":
        for p in room["players"]:
            if p["id"] == turn["guesser_id"]:
                p["score"] += 5
        room["last_correct"] = True
        room["status"] = "RESULT"
    else:
        # Void round time & send new question
        for p in room["players"]:
            if p["id"] == turn["guesser_id"]:
                p["time"] = max(0.0, round(p["time"] - room["last_elapsed"], 2))
        room["current_q"] = ""
        room["current_a"] = ""
        room["status"] = "ASKING"

    return jsonify({"ok": True})


@app.route("/api/next_turn", methods=["POST"])
def next_turn():
    data = request.json or {}
    code = (data.get("code") or "").upper()
    pid = data.get("player_id")

    room = rooms.get(code)
    if not room or room["status"] != "RESULT":
        return jsonify({"ok": False})

    turn = room["queue"][room["turn_idx"]]
    if pid not in (turn["asker_id"], turn["guesser_id"], room["host_id"]):
        return jsonify({"ok": False})

    room["turn_idx"] += 1
    if room["turn_idx"] >= len(room["queue"]):
        room["status"] = "GAMEOVER"
    else:
        room["current_q"] = ""
        room["current_a"] = ""
        room["status"] = "ASKING"
    return jsonify({"ok": True})


@app.route("/api/state")
def get_state():
    code = (request.args.get("code") or "").upper()
    pid = request.args.get("player_id") or ""
    room = rooms.get(code)
    if not room:
        return jsonify({"ok": False, "error": "Room closed or not found."})

    # Auto-expire guess timer on server if time ran out
    remaining = room["time_limit"]
    if room["status"] == "GUESSING":
        elapsed = time.time() - room["turn_start_ts"]
        remaining = max(0, int(room["time_limit"] - elapsed))
        if elapsed >= room["time_limit"] + 1.0:
            turn = room["queue"][room["turn_idx"]]
            room["last_guess"] = "(Time Expired)"
            room["last_correct"] = False
            room["last_elapsed"] = float(room["time_limit"])
            for p in room["players"]:
                if p["id"] == turn["guesser_id"]:
                    p["time"] = round(p["time"] + room["time_limit"], 2)
                elif not room["umpire_id"] and p["id"] == turn["asker_id"]:
                    p["score"] += 5
            room["status"] = "RESULT"

    turn = room["queue"][room["turn_idx"]] if room["queue"] and room["turn_idx"] < len(room["queue"]) else None
    sorted_players = sorted(room["players"], key=lambda x: (-x["score"], x["time"]))

    return jsonify({
        "ok": True,
        "code": room["code"],
        "status": room["status"],
        "host_id": room["host_id"],
        "umpire_id": room["umpire_id"],
        "umpire_name": room["umpire_name"],
        "max_players": room["max_players"],
        "questions_per_player": room["questions_per_player"],
        "time_limit": room["time_limit"],
        "remaining": remaining,
        "players": sorted_players,
        "turn_num": room["turn_idx"] + 1,
        "total_turns": len(room["queue"]),
        "asker_id": turn["asker_id"] if turn else None,
        "asker_name": get_player_name(room, turn["asker_id"]) if turn else "",
        "guesser_id": turn["guesser_id"] if turn else None,
        "guesser_name": get_player_name(room, turn["guesser_id"]) if turn else "",
        "question": room["current_q"],
        "hint": room["current_hint"],
        "secret_answer": room["current_a"] if room["status"] in ("RESULT", "CONTEST") else "",
        "last_guess": room["last_guess"],
        "last_correct": room["last_correct"],
        "last_elapsed": room["last_elapsed"],
        "contest_reason": room["contest_reason"],
        "starters": STARTER_PROMPTS
    })


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Double Sage — Online Multiplayer</title>
<style>
  :root {
    --bg: #0b1120;
    --card: #131c31;
    --border: #24324d;
    --gold: #f5b942;
    --teal: #2dd4bf;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --danger: #f43f5e;
  }
  * { box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }
  body { margin: 0; background: var(--bg); color: var(--text); padding: 14px; display: flex; justify-content: center; }
  .wrap { width: 100%; max-width: 540px; }
  .topbar { display: flex; align-items: center; justify-content: space-between; background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 10px 14px; margin-bottom: 12px; }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 1.15rem; color: var(--gold); }
  .brand img { width: 34px; height: 34px; border-radius: 8px; object-fit: cover; border: 1px solid var(--gold); }
  .pill { background: #1e293b; color: var(--teal); border: 1px solid var(--border); padding: 6px 11px; border-radius: 999px; font-size: 0.8rem; font-weight: 700; cursor: pointer; }
  .hero { margin-bottom: 14px; }
  .hero-banner { width: 100%; border-radius: 14px; border: 1px solid var(--border); display: block; margin-bottom: 8px; max-height: 190px; object-fit: cover; }
  .hero-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .hero-grid img { width: 100%; height: 110px; object-fit: cover; border-radius: 10px; border: 1px solid var(--border); }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 18px; margin-bottom: 14px; }
  h2, h3 { margin: 0 0 10px 0; color: var(--gold); }
  label { display: block; font-size: 0.85rem; color: var(--muted); margin: 10px 0 4px; }
  input, select, textarea { width: 100%; padding: 11px; border-radius: 10px; border: 1px solid var(--border); background: #0f172a; color: var(--text); font-size: 0.95rem; }
  .btn { width: 100%; padding: 12px; border: none; border-radius: 10px; font-weight: 800; font-size: 0.95rem; cursor: pointer; margin-top: 10px; }
  .btn-gold { background: var(--gold); color: #0b1120; }
  .btn-teal { background: var(--teal); color: #0b1120; }
  .btn-dark { background: #1e293b; color: var(--text); border: 1px solid var(--border); }
  .btn-danger { background: var(--danger); color: #fff; }
  .row { display: flex; gap: 8px; }
  .row > * { flex: 1; }
  .code-box { font-size: 2rem; font-weight: 900; letter-spacing: 6px; text-align: center; color: var(--teal); background: #0f172a; padding: 12px; border-radius: 12px; border: 1px dashed var(--teal); margin: 8px 0; }
  .hint-box { background: rgba(245,185,66,0.12); border: 1px solid var(--gold); color: var(--gold); padding: 10px; border-radius: 10px; font-weight: 700; text-align: center; margin: 10px 0; }
  .timer { font-size: 1.4rem; font-weight: 900; color: var(--teal); text-align: right; }
  .timer.urgent { color: var(--danger); }
  .player-item { display: flex; justify-content: space-between; align-items: center; padding: 9px 12px; background: #0f172a; border-radius: 10px; margin-bottom: 6px; border: 1px solid var(--border); }
  .badge { font-size: 0.75rem; padding: 3px 8px; border-radius: 6px; background: #1e293b; color: var(--gold); font-weight: 700; }
  .hidden { display: none !important; }
  .qb-item { background: #0f172a; border: 1px solid var(--border); border-radius: 10px; padding: 10px; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand">
      <img src="/assets/double_sage_icon.png" onerror="this.style.display='none'" alt="Icon">
      <span>DOUBLE SAGE</span>
    </div>
    <div style="display:flex;gap:6px;">
      <button class="pill" onclick="toggleQBModal()">📚 My QB's</button>
      <button class="pill" id="sfxBtn" onclick="toggleSFX()">🔊 SFX ON</button>
    </div>
  </div>

  <!-- HERO SHOWCASE -->
  <div id="heroSection" class="hero">
    <img class="hero-banner" src="/assets/double_sage_banner.png" onerror="this.style.display='none'" alt="Double Sage Banner">
    <div class="hero-grid">
      <img src="/assets/double_sage_battle.png" onerror="this.style.display='none'" alt="1v1 Battle">
      <img src="/assets/double_sage_tournament.png" onerror="this.style.display='none'" alt="Tournament">
    </div>
  </div>

  <!-- HOME SCREEN -->
  <div id="homeScreen" class="card">
    <h2>Create Multiplayer Room</h2>
    <label>Your Name</label>
    <input id="hostName" placeholder="Enter your name">
    <div class="row">
      <div>
        <label>Players (2-10)</label>
        <input id="maxPlayers" type="number" min="2" max="10" value="2">
      </div>
      <div>
        <label>Questions Each</label>
        <input id="qPerPlayer" type="number" min="1" max="10" value="3">
      </div>
      <div>
        <label>Timer (10-60s)</label>
        <input id="timeLimit" type="number" min="10" max="60" value="30">
      </div>
    </div>
    <label style="display:flex;align-items:center;gap:8px;margin-top:12px;color:var(--text);cursor:pointer;">
      <input id="umpireCheck" type="checkbox" style="width:auto;">
      Play as Umpire (Organizer Mode — sets questions, ruling is final)
    </label>
    <button class="btn btn-gold" onclick="createRoom()">Create Room</button>

    <hr style="border:0;border-top:1px solid var(--border);margin:18px 0;">
    <h2>Join Existing Room</h2>
    <div class="row">
      <input id="joinName" placeholder="Your Name">
      <input id="joinCode" placeholder="4-Letter Code" maxlength="4" style="text-transform:uppercase;">
    </div>
    <button class="btn btn-teal" onclick="joinRoom()">Join Room</button>
  </div>

  <!-- LOBBY SCREEN -->
  <div id="lobbyScreen" class="card hidden">
    <h2>Waiting Lobby</h2>
    <p style="color:var(--muted);font-size:0.9rem;margin:0;">Share this room code with friends:</p>
    <div class="code-box" id="lobbyCode">----</div>
    <button class="btn btn-dark" onclick="copyInvite()">🔗 Copy One-Tap Invite Link</button>
    <div id="lobbyMeta" style="margin:12px 0;font-size:0.85rem;color:var(--muted);"></div>
    <div id="lobbyPlayers"></div>
    <button id="startBtn" class="btn btn-gold hidden" onclick="startGame()">Start Match</button>
  </div>

  <!-- GAME SCREEN -->
  <div id="gameScreen" class="card hidden">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <span class="badge" id="turnBadge">Turn 1</span>
      <div class="timer" id="timerDisplay">30s</div>
    </div>

    <!-- ASKING VIEW -->
    <div id="askingView" class="hidden">
      <h3 style="margin-top:12px;">Your Turn to Set a Trap!</h3>
      <p style="font-size:0.85rem;color:var(--muted);">Target Guesser: <strong id="targetGuesserName" style="color:var(--text);"></strong></p>

      <div class="row" style="margin-bottom:8px;">
        <button class="btn btn-dark" style="margin-top:0;font-size:0.82rem;" onclick="loadNextUnusedQB()">⚡ Next Unused QB</button>
        <button class="btn btn-dark" style="margin-top:0;font-size:0.82rem;" onclick="saveCurrentToQB()">💾 Save to My QB's</button>
      </div>

      <label>Pick from Starter Prompts or Saved QB's (Editable)</label>
      <select id="promptSelect" onchange="applySelectedPrompt()">
        <option value="">-- Choose a prompt to load & edit --</option>
      </select>

      <label>Question</label>
      <textarea id="qInput" rows="2" placeholder="Type your question..."></textarea>
      <label>Secret Answer</label>
      <input id="aInput" placeholder="Type the exact answer...">
      <button class="btn btn-gold" onclick="submitQuestion()">Lock Question & Start Timer</button>
    </div>

    <!-- WAITING FOR ASKER -->
    <div id="waitAskView" class="hidden">
      <h3 style="margin-top:14px;">Manager is Waiting...</h3>
      <p id="waitAskMsg" style="color:var(--muted);"></p>
    </div>

    <!-- GUESSING VIEW -->
    <div id="guessingView" class="hidden">
      <h3 style="margin-top:12px;">Question For You!</h3>
      <div id="qDisplay" style="font-size:1.15rem;font-weight:700;margin:10px 0;"></div>
      <div class="hint-box" id="hintDisplay">MANAGER HINT</div>
      <input id="guessInput" placeholder="Type your guess fast...">
      <button class="btn btn-teal" onclick="submitGuess()">Submit Answer</button>
    </div>

    <!-- SPECTATING GUESS -->
    <div id="spectateGuessView" class="hidden">
      <h3 style="margin-top:12px;">Guesser is on the Clock!</h3>
      <div id="specQDisplay" style="font-size:1.05rem;font-weight:700;margin:10px 0;"></div>
      <div class="hint-box" id="specHintDisplay">MANAGER HINT</div>
      <p id="specGuesserMsg" style="color:var(--muted);"></p>
    </div>

    <!-- RESULT VIEW -->
    <div id="resultView" class="hidden">
      <h3 id="resultHeadline" style="margin-top:12px;">Round Result</h3>
      <p style="margin:6px 0;">Question: <strong id="resQ"></strong></p>
      <p style="margin:6px 0;">Guesser Typed: <strong id="resGuess" style="color:var(--teal);"></strong> (<span id="resTime"></span>s)</p>
      <p style="margin:6px 0;">Secret Answer: <strong id="resAns" style="color:var(--gold);"></strong></p>

      <div id="contestTriggerBox" class="hidden" style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border);">
        <input id="contestReasonInput" placeholder="Optional reason (e.g., valid spelling/alias)">
        <button class="btn btn-danger" onclick="raiseContest()">⚠️ CONTEST ANSWER (Request Asker Review)</button>
      </div>

      <button id="nextTurnBtn" class="btn btn-gold hidden" onclick="nextTurn()">Next Turn ➡️</button>
    </div>

    <!-- CONTEST APPROVAL VIEW -->
    <div id="contestView" class="hidden">
      <h3 style="margin-top:12px;color:var(--danger);">⚠️ Answer Contested!</h3>
      <p>Guesser Typed: <strong id="conGuess"></strong> | Secret Answer: <strong id="conAns"></strong></p>
      <p style="color:var(--muted);font-size:0.9rem;">Reason: <span id="conReason"></span></p>
      <div id="askerDecisionBtns" class="hidden">
        <button class="btn btn-teal" onclick="resolveContest('ACCEPT_GUESS')">✅ Accept Guess (+5 Pts to Guesser)</button>
        <button class="btn btn-gold" onclick="resolveContest('NEW_QUESTION')">🔄 Void & Send New Question (0 Pts)</button>
      </div>
      <p id="waitDecisionMsg" class="hidden" style="color:var(--muted);">Waiting for the Asker to rule on the contest...</p>
    </div>

    <!-- LIVE SCOREBOARD -->
    <div style="margin-top:18px;padding-top:12px;border-top:1px solid var(--border);">
      <div style="font-size:0.85rem;font-weight:700;color:var(--muted);margin-bottom:8px;">LIVE SCOREBOARD (Tie-Breaker: Fastest Time)</div>
      <div id="scoreList"></div>
    </div>
  </div>

  <!-- GAME OVER -->
  <div id="gameoverScreen" class="card hidden">
    <h2>🏆 Final Standings</h2>
    <div id="winnerBanner" style="font-size:1.25rem;font-weight:900;color:var(--teal);margin-bottom:12px;"></div>
    <div id="finalScores"></div>
    <button class="btn btn-gold" onclick="location.href='/'">Play Again</button>
  </div>

  <!-- QB MODAL -->
  <div id="qbModal" class="card hidden">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h2>📚 My QB's (Saved Banks)</h2>
      <button class="pill" onclick="toggleQBModal()">Close ✕</button>
    </div>
    <p style="font-size:0.85rem;color:var(--muted);">Save your own questions & answers on this phone so you don't have to retype them every round.</p>
    <input id="newQbQ" placeholder="New Question">
    <input id="newQbA" placeholder="Secret Answer" style="margin-top:6px;">
    <button class="btn btn-teal" onclick="addQBFromModal()">+ Add to My QB's</button>
    <div id="qbListContainer" style="margin-top:14px;"></div>
  </div>
</div>

<script>
let state = { code: "", playerId: "", sfx: true, lastStatus: "", lastTurn: -1, starters: [], usedQBs: [] };
let audioCtx = null;

function playTone(freq, type, dur, vol=0.12) {
  if (!state.sfx) return;
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.value = vol;
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + dur);
  } catch (e) {}
}

function vibrate(ms) {
  if (state.sfx && navigator.vibrate) navigator.vibrate(ms);
}

function toggleSFX() {
  state.sfx = !state.sfx;
  document.getElementById("sfxBtn").textContent = state.sfx ? "🔊 SFX ON" : "🔇 SFX OFF";
  if (state.sfx) playTone(520, "sine", 0.12);
}

// QB Management in localStorage
function getQBs() {
  try { return JSON.parse(localStorage.getItem("double_sage_qbs") || "[]"); }
  catch (e) { return []; }
}
function saveQBs(list) {
  localStorage.setItem("double_sage_qbs", JSON.stringify(list));
  renderQBList();
  populateDropdown(true);
}
function toggleQBModal() {
  const m = document.getElementById("qbModal");
  m.classList.toggle("hidden");
  renderQBList();
}
function addQBFromModal() {
  const q = document.getElementById("newQbQ").value.trim();
  const a = document.getElementById("newQbA").value.trim();
  if (!q || !a) return alert("Enter both question and answer.");
  const list = getQBs();
  list.push({ q, a });
  saveQBs(list);
  document.getElementById("newQbQ").value = "";
  document.getElementById("newQbA").value = "";
  playTone(660, "triangle", 0.15);
}
function deleteQB(idx) {
  const list = getQBs();
  list.splice(idx, 1);
  saveQBs(list);
}
function renderQBList() {
  const list = getQBs();
  const box = document.getElementById("qbListContainer");
  if (!list.length) {
    box.innerHTML = "<p style='color:var(--muted);font-size:0.85rem;'>No saved QB's yet.</p>";
    return;
  }
  box.innerHTML = list.map((item, i) => `
    <div class="qb-item">
      <div style="font-weight:700;">${escapeHtml(item.q)}</div>
      <div style="font-size:0.82rem;color:var(--teal);margin:4px 0;">Answer: ${escapeHtml(item.a)}</div>
      <button class="pill" style="color:var(--danger);" onclick="deleteQB(${i})">Delete</button>
    </div>
  `).join("");
}
function saveCurrentToQB() {
  const q = document.getElementById("qInput").value.trim();
  const a = document.getElementById("aInput").value.trim();
  if (!q || !a) return alert("Type a question and answer first.");
  const list = getQBs();
  list.push({ q, a });
  saveQBs(list);
  playTone(700, "sine", 0.15);
  alert("Saved to My QB's!");
}
function loadNextUnusedQB() {
  const list = getQBs();
  if (!list.length) return alert("Your QB bank is empty! Add some in 📚 My QB's.");
  let idx = list.findIndex((_, i) => !state.usedQBs.includes(i));
  if (idx === -1) { state.usedQBs = []; idx = 0; }
  state.usedQBs.push(idx);
  document.getElementById("qInput").value = list[idx].q;
  document.getElementById("aInput").value = list[idx].a;
  playTone(580, "triangle", 0.12);
}

let dropdownBuilt = false;
function populateDropdown(force = false) {
  if (dropdownBuilt && !force) return;
  const sel = document.getElementById("promptSelect");
  const prevVal = sel.value;
  let html = '<option value="">-- Choose a prompt to load & edit --</option>';
  const qbs = getQBs();
  if (qbs.length) {
    html += '<optgroup label="📚 My Saved QB\'s">';
    qbs.forEach((item, i) => {
      html += `<option value="qb_${i}">${escapeHtml(item.q)}</option>`;
    });
    html += '</optgroup>';
  }
  if (state.starters.length) {
    html += '<optgroup label="✨ Starter Prompts">';
    state.starters.forEach((item, i) => {
      html += `<option value="st_${i}">[${escapeHtml(item.cat)}] ${escapeHtml(item.q)}</option>`;
    });
    html += '</optgroup>';
  }
  sel.innerHTML = html;
  if (prevVal) sel.value = prevVal;
  dropdownBuilt = true;
}

function applySelectedPrompt() {
  const val = document.getElementById("promptSelect").value;
  if (!val) return;
  if (val.startsWith("qb_")) {
    const item = getQBs()[parseInt(val.slice(3), 10)];
    if (item) {
      document.getElementById("qInput").value = item.q;
      document.getElementById("aInput").value = item.a;
    }
  } else if (val.startsWith("st_")) {
    const item = state.starters[parseInt(val.slice(3), 10)];
    if (item) {
      document.getElementById("qInput").value = item.q;
      document.getElementById("aInput").value = item.a;
    }
  }
  playTone(540, "sine", 0.1);
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

async function createRoom() {
  const payload = {
    name: document.getElementById("hostName").value.trim() || "Host",
    max_players: document.getElementById("maxPlayers").value,
    questions_per_player: document.getElementById("qPerPlayer").value,
    time_limit: document.getElementById("timeLimit").value,
    is_umpire: document.getElementById("umpireCheck").checked
  };
  const res = await fetch("/api/create_room", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
  const data = await res.json();
  if (data.ok) {
    state.code = data.code;
    state.playerId = data.player_id;
    playTone(620, "triangle", 0.18);
    pollState();
  }
}

async function joinRoom() {
  const payload = {
    name: document.getElementById("joinName").value.trim() || "Player",
    code: document.getElementById("joinCode").value.trim().toUpperCase()
  };
  const res = await fetch("/api/join_room", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
  const data = await res.json();
  if (!data.ok) return alert(data.error);
  state.code = data.code;
  state.playerId = data.player_id;
  playTone(620, "triangle", 0.18);
  pollState();
}

function copyInvite() {
  const url = `${location.origin}/?room=${state.code}`;
  navigator.clipboard.writeText(url);
  alert("Invite link copied: " + url);
}

async function kickPlayer(targetId) {
  await fetch("/api/kick_player", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ code: state.code, host_id: state.playerId, target_id: targetId }) });
  pollState();
}

async function startGame() {
  const res = await fetch("/api/start_game", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ code: state.code, host_id: state.playerId }) });
  const data = await res.json();
  if (!data.ok) alert(data.error);
  else { playTone(740, "triangle", 0.22); pollState(); }
}

async function submitQuestion() {
  const q = document.getElementById("qInput").value.trim();
  const a = document.getElementById("aInput").value.trim();
  if (!q || !a) return alert("Enter both question and secret answer.");
  await fetch("/api/submit_question", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ code: state.code, player_id: state.playerId, question: q, answer: a }) });
  document.getElementById("qInput").value = "";
  document.getElementById("aInput").value = "";
  document.getElementById("promptSelect").value = "";
  playTone(680, "sine", 0.15);
  pollState();
}

async function submitGuess() {
  const guess = document.getElementById("guessInput").value.trim();
  await fetch("/api/submit_guess", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ code: state.code, player_id: state.playerId, guess }) });
  document.getElementById("guessInput").value = "";
  pollState();
}

async function raiseContest() {
  const reason = document.getElementById("contestReasonInput").value.trim();
  await fetch("/api/raise_contest", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ code: state.code, player_id: state.playerId, reason }) });
  document.getElementById("contestReasonInput").value = "";
  playTone(320, "sawtooth", 0.2);
  vibrate(150);
  pollState();
}

async function resolveContest(decision) {
  await fetch("/api/resolve_contest", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ code: state.code, player_id: state.playerId, decision }) });
  pollState();
}

async function nextTurn() {
  await fetch("/api/next_turn", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ code: state.code, player_id: state.playerId }) });
  pollState();
}

async function pollState() {
  if (!state.code) return;
  try {
    const res = await fetch(`/api/state?code=${state.code}&player_id=${state.playerId}`);
    const d = await res.json();
    if (!d.ok) return;

    if (d.starters && !state.starters.length) {
      state.starters = d.starters;
      populateDropdown(true);
    }

    document.getElementById("homeScreen").classList.add("hidden");
    document.getElementById("heroSection").classList.add("hidden");

    // Sound triggers on transitions
    if (state.lastStatus !== d.status) {
      if (d.status === "RESULT") {
        if (d.last_correct) { playTone(780, "triangle", 0.25); vibrate(80); }
        else { playTone(220, "sawtooth", 0.25); vibrate(180); }
      } else if (d.status === "GAMEOVER") {
        playTone(880, "triangle", 0.35);
      }
      state.lastStatus = d.status;
    }

    if (d.status === "LOBBY") {
      document.getElementById("lobbyScreen").classList.remove("hidden");
      document.getElementById("lobbyCode").textContent = d.code;
      document.getElementById("lobbyMeta").textContent =
        `Players: ${d.players.length}/${d.max_players} • ${d.questions_per_player} Qs each • ${d.time_limit}s timer` +
        (d.umpire_name ? ` • Umpire: ${d.umpire_name}` : "");
      const isHost = (d.host_id === state.playerId);
      document.getElementById("startBtn").classList.toggle("hidden", !isHost);
      document.getElementById("lobbyPlayers").innerHTML = d.players.map(p => `
        <div class="player-item">
          <span>${escapeHtml(p.name)}</span>
          ${isHost ? `<button class="pill" style="color:var(--danger);" onclick="kickPlayer('${p.id}')">Kick</button>` : `<span class="badge">Ready</span>`}
        </div>
      `).join("");
      return;
    }

    document.getElementById("lobbyScreen").classList.add("hidden");

    if (d.status === "GAMEOVER") {
      document.getElementById("gameScreen").classList.add("hidden");
      document.getElementById("gameoverScreen").classList.remove("hidden");
      const top = d.players[0];
      document.getElementById("winnerBanner").textContent = top ? `Champion: ${top.name} (${top.score} pts • ${top.time}s)` : "Match Complete";
      document.getElementById("finalScores").innerHTML = d.players.map((p, i) => `
        <div class="player-item">
          <span>#${i+1} ${escapeHtml(p.name)}</span>
          <span class="badge">${p.score} pts • ${p.time}s</span>
        </div>
      `).join("");
      return;
    }

    document.getElementById("gameScreen").classList.remove("hidden");
    document.getElementById("turnBadge").textContent = `Turn ${d.turn_num} of ${d.total_turns}`;

    const timerEl = document.getElementById("timerDisplay");
    if (d.status === "GUESSING") {
      timerEl.textContent = `${d.remaining}s`;
      timerEl.classList.toggle("urgent", d.remaining <= 5);
      if (d.remaining <= 5 && d.remaining > 0) playTone(440, "sine", 0.06, 0.06);
    } else {
      timerEl.textContent = `${d.time_limit}s`;
      timerEl.classList.remove("urgent");
    }

    ["askingView", "waitAskView", "guessingView", "spectateGuessView", "resultView", "contestView"].forEach(id => {
      document.getElementById(id).classList.add("hidden");
    });

    const isAsker = (d.asker_id === state.playerId);
    const isGuesser = (d.guesser_id === state.playerId);

    if (d.status === "ASKING") {
      if (isAsker) {
        document.getElementById("askingView").classList.remove("hidden");
        document.getElementById("targetGuesserName").textContent = d.guesser_name;
        populateDropdown(false);
      } else {
        document.getElementById("waitAskView").classList.remove("hidden");
        document.getElementById("waitAskMsg").textContent = `${d.asker_name} is setting a question for ${d.guesser_name}...`;
      }
    } else if (d.status === "GUESSING") {
      if (isGuesser) {
        document.getElementById("guessingView").classList.remove("hidden");
        document.getElementById("qDisplay").textContent = d.question;
        document.getElementById("hintDisplay").textContent = `MANAGER HINT: ${d.hint}`;
      } else {
        document.getElementById("spectateGuessView").classList.remove("hidden");
        document.getElementById("specQDisplay").textContent = d.question;
        document.getElementById("specHintDisplay").textContent = `MANAGER HINT: ${d.hint}`;
        document.getElementById("specGuesserMsg").textContent = `Waiting for ${d.guesser_name} to answer...`;
      }
    } else if (d.status === "RESULT") {
      document.getElementById("resultView").classList.remove("hidden");
      document.getElementById("resultHeadline").textContent = d.last_correct ? "✅ Spot On! (+5 Pts to Guesser)" : "❌ Incorrect!";
      document.getElementById("resQ").textContent = d.question;
      document.getElementById("resGuess").textContent = d.last_guess;
      document.getElementById("resTime").textContent = d.last_elapsed;
      document.getElementById("resAns").textContent = d.secret_answer;

      // Contest only allowed in non-Umpire mode when Guesser was marked wrong
      const canContest = (!d.umpire_id && !d.last_correct && isGuesser);
      document.getElementById("contestTriggerBox").classList.toggle("hidden", !canContest);

      const canAdvance = (isAsker || isGuesser || d.host_id === state.playerId);
      document.getElementById("nextTurnBtn").classList.toggle("hidden", !canAdvance);
    } else if (d.status === "CONTEST") {
      document.getElementById("contestView").classList.remove("hidden");
      document.getElementById("conGuess").textContent = d.last_guess;
      document.getElementById("conAns").textContent = d.secret_answer;
      document.getElementById("conReason").textContent = d.contest_reason;
      document.getElementById("askerDecisionBtns").classList.toggle("hidden", !isAsker);
      document.getElementById("waitDecisionMsg").classList.toggle("hidden", isAsker);
    }

    document.getElementById("scoreList").innerHTML = d.players.map((p, i) => `
      <div class="player-item">
        <span>#${i+1} ${escapeHtml(p.name)}</span>
        <span class="badge">${p.score} pts • ${p.time}s</span>
      </div>
    `).join("");
  } catch (e) {}
}

// Auto-fill invite code if ?room=XXXX is in URL
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get("room")) {
  document.getElementById("joinCode").value = urlParams.get("room").toUpperCase();
}
setInterval(pollState, 1500);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

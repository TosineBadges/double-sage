import os
import random
import string
import time
from flask import Flask, request, jsonify, send_from_directory, abort

app = Flask(__name__)

# In-memory rooms store
rooms = {}

STARTER_PROMPTS = [
    ("General", "What is the hardest natural substance on Earth?", "Diamond"),
    ("General", "Which planet is known as the Red Planet?", "Mars"),
    ("General", "What is the capital city of Japan?", "Tokyo"),
    ("General", "How many continents are there on Earth?", "7"),
    ("Numbers", "In what year did humans first land on the Moon?", "1969"),
    ("Numbers", "How many minutes are in a standard soccer match?", "90"),
    ("Numbers", "What is the boiling point of water in Celsius?", "100"),
    ("Sports", "Which country won the 2022 FIFA World Cup?", "Argentina"),
    ("Sports", "How many players are on a standard basketball team on court?", "5"),
    ("Movies", "Who directed the movie Inception?", "Christopher Nolan"),
    ("Movies", "What is the name of the fictional African nation in Black Panther?", "Wakanda"),
    ("Science", "What chemical element has the symbol Au?", "Gold"),
    ("Science", "How many bones are in the adult human body?", "206"),
]

def generate_room_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if code not in rooms:
            return code

def generate_hint(answer):
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

def build_turn_queue(room):
    players = room["players"]
    q_per_player = room["questions_per_player"]
    queue = []
    if room["umpire_mode"]:
        for _ in range(q_per_player):
            for p in players:
                queue.append({"asker": room["umpire_name"], "guesser": p["name"], "is_umpire": True})
    else:
        n = len(players)
        for r in range(q_per_player):
            for i in range(n):
                guesser = players[i]["name"]
                asker = players[(i + 1 + (r % max(1, n - 1))) % n]["name"]
                queue.append({"asker": asker, "guesser": guesser, "is_umpire": False})
    return queue

def get_sorted_standings(room):
    return sorted(
        room["players"],
        key=lambda p: (-p["score"], p["time_spent"])
    )

# Smart image route checking root and static/ with case-insensitive & multi-extension matching
@app.route("/media/<path:base_name>")
def serve_media(base_name):
    search_dirs = [os.getcwd(), os.path.join(os.getcwd(), "static")]
    exts = ["", ".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG"]
    candidates = []
    stem, ext = os.path.splitext(base_name)
    if ext:
        candidates.extend([base_name, stem + ".jpg", stem + ".jpeg", stem + ".png", stem + ".JPG", stem + ".PNG"])
    else:
        for e in exts[1:]:
            candidates.append(stem + e)
            short = stem.replace("double_sage_", "")
            if short != stem:
                candidates.append(short + e)

    for folder in search_dirs:
        if not os.path.isdir(folder):
            continue
        files_in_dir = {f.lower(): f for f in os.listdir(folder)}
        for cand in candidates:
            actual = files_in_dir.get(cand.lower())
            if actual:
                return send_from_directory(folder, actual)
    abort(404)

@app.route("/api/create", methods=["POST"])
def api_create():
    data = request.json or {}
    host_name = (data.get("name") or "Host").strip() or "Host"
    max_players = max(2, min(10, int(data.get("max_players", 2))))
    q_per_player = max(1, min(15, int(data.get("questions_per_player", 3))))
    time_limit = max(10, min(60, int(data.get("time_limit", 30))))
    umpire_mode = bool(data.get("umpire_mode", False))

    code = generate_room_code()
    players = [] if umpire_mode else [{"name": host_name, "score": 0, "time_spent": 0.0}]

    rooms[code] = {
        "code": code,
        "host": host_name,
        "umpire_mode": umpire_mode,
        "umpire_name": host_name if umpire_mode else None,
        "max_players": max_players,
        "questions_per_player": q_per_player,
        "time_limit": time_limit,
        "players": players,
        "status": "lobby",
        "queue": [],
        "turn_index": 0,
        "phase": "asking",
        "current_question": "",
        "current_answer": "",
        "current_hint": "",
        "turn_start_time": 0.0,
        "last_result": None,
        "contest": None,
    }
    return jsonify({"ok": True, "code": code, "name": host_name})

@app.route("/api/join", methods=["POST"])
def api_join():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if not code or not name:
        return jsonify({"ok": False, "error": "Enter both your name and room code."})
    room = rooms.get(code)
    if not room:
        return jsonify({"ok": False, "error": "Room not found. Check the 4-letter code."})
    if room["status"] != "lobby":
        if any(p["name"].lower() == name.lower() for p in room["players"]) or (
            room["umpire_mode"] and room["umpire_name"].lower() == name.lower()
        ):
            return jsonify({"ok": True, "code": code, "name": name})
        return jsonify({"ok": False, "error": "Match already in progress."})

    if room["umpire_mode"] and room["umpire_name"].lower() == name.lower():
        return jsonify({"ok": True, "code": code, "name": room["umpire_name"]})

    for p in room["players"]:
        if p["name"].lower() == name.lower():
            return jsonify({"ok": True, "code": code, "name": p["name"]})

    if len(room["players"]) >= room["max_players"]:
        return jsonify({"ok": False, "error": "Room is full."})

    room["players"].append({"name": name, "score": 0, "time_spent": 0.0})
    return jsonify({"ok": True, "code": code, "name": name})

@app.route("/api/kick", methods=["POST"])
def api_kick():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    requester = (data.get("requester") or "").strip()
    target = (data.get("target") or "").strip()
    room = rooms.get(code)
    if not room or room["host"] != requester or room["status"] != "lobby":
        return jsonify({"ok": False, "error": "Not authorized."})
    room["players"] = [p for p in room["players"] if p["name"] != target]
    return jsonify({"ok": True})

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    requester = (data.get("requester") or "").strip()
    room = rooms.get(code)
    if not room or room["host"] != requester:
        return jsonify({"ok": False, "error": "Only host can start."})
    min_needed = 2
    if len(room["players"]) < min_needed:
        return jsonify({"ok": False, "error": "Need at least 2 competing players to start."})
    room["queue"] = build_turn_queue(room)
    room["turn_index"] = 0
    room["status"] = "playing"
    room["phase"] = "asking"
    room["last_result"] = None
    room["contest"] = None
    return jsonify({"ok": True})

@app.route("/api/set_question", methods=["POST"])
def api_set_question():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    asker = (data.get("name") or "").strip()
    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    room = rooms.get(code)
    if not room or room["status"] != "playing" or room["phase"] != "asking":
        return jsonify({"ok": False, "error": "Invalid game state."})
    turn = room["queue"][room["turn_index"]]
    if turn["asker"] != asker:
        return jsonify({"ok": False, "error": "Not your turn to ask."})
    if not question or not answer:
        return jsonify({"ok": False, "error": "Enter both a question and secret answer."})

    room["current_question"] = question
    room["current_answer"] = answer
    room["current_hint"] = generate_hint(answer)
    room["turn_start_time"] = time.time()
    room["phase"] = "guessing"
    room["contest"] = None
    return jsonify({"ok": True})

@app.route("/api/submit_guess", methods=["POST"])
def api_submit_guess():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    guesser = (data.get("name") or "").strip()
    guess = (data.get("guess") or "").strip()
    timed_out = bool(data.get("timed_out", False))
    room = rooms.get(code)
    if not room or room["status"] != "playing" or room["phase"] != "guessing":
        return jsonify({"ok": False, "error": "Invalid state."})
    turn = room["queue"][room["turn_index"]]
    if turn["guesser"] != guesser:
        return jsonify({"ok": False, "error": "Not your turn to guess."})

    elapsed = round(min(float(room["time_limit"]), max(0.1, time.time() - room["turn_start_time"])), 2)
    if timed_out:
        elapsed = float(room["time_limit"])

    correct = (not timed_out) and (guess.lower() == room["current_answer"].lower())

    for p in room["players"]:
        if p["name"] == guesser:
            p["time_spent"] = round(p["time_spent"] + elapsed, 2)
            if correct:
                p["score"] += 5
        elif not turn["is_umpire"] and p["name"] == turn["asker"] and not correct:
            p["score"] += 5

    room["last_result"] = {
        "asker": turn["asker"],
        "guesser": guesser,
        "is_umpire": turn["is_umpire"],
        "question": room["current_question"],
        "guess": "(Time Expired)" if timed_out else (guess or "(Blank)"),
        "answer": room["current_answer"],
        "correct": correct,
        "elapsed": elapsed,
        "contested": False,
        "contest_resolved": False,
        "resolution_note": ""
    }
    room["phase"] = "result"
    return jsonify({"ok": True})

@app.route("/api/contest", methods=["POST"])
def api_contest():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    guesser = (data.get("name") or "").strip()
    reason = (data.get("reason") or "Answer should be accepted").strip()
    room = rooms.get(code)
    if not room or room["phase"] != "result" or not room["last_result"]:
        return jsonify({"ok": False, "error": "Cannot contest right now."})
    res = room["last_result"]
    if res["is_umpire"]:
        return jsonify({"ok": False, "error": "Umpire rulings are final."})
    if res["guesser"] != guesser or res["correct"] or res["contested"]:
        return jsonify({"ok": False, "error": "Contest not available."})

    res["contested"] = True
    room["contest"] = {"guesser": guesser, "asker": res["asker"], "reason": reason}
    room["phase"] = "contest_review"
    return jsonify({"ok": True})

@app.route("/api/resolve_contest", methods=["POST"])
def api_resolve_contest():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    asker = (data.get("name") or "").strip()
    decision = data.get("decision")  # "accept_guess" or "new_question"
    room = rooms.get(code)
    if not room or room["phase"] != "contest_review" or not room["last_result"]:
        return jsonify({"ok": False, "error": "No active contest."})
    res = room["last_result"]
    if res["asker"] != asker:
        return jsonify({"ok": False, "error": "Only the Asker can decide."})

    if decision == "accept_guess":
        for p in room["players"]:
            if p["name"] == res["asker"]:
                p["score"] = max(0, p["score"] - 5)
            elif p["name"] == res["guesser"]:
                p["score"] += 5
        res["correct"] = True
        res["contest_resolved"] = True
        res["resolution_note"] = f"{asker} accepted the guess! +5 pts awarded to {res['guesser']}."
        room["contest"] = None
        room["phase"] = "result"
    elif decision == "new_question":
        for p in room["players"]:
            if p["name"] == res["asker"]:
                p["score"] = max(0, p["score"] - 5)
            elif p["name"] == res["guesser"]:
                p["time_spent"] = round(max(0.0, p["time_spent"] - res["elapsed"]), 2)
        room["contest"] = None
        room["last_result"] = None
        room["phase"] = "asking"
    return jsonify({"ok": True})

@app.route("/api/next_turn", methods=["POST"])
def api_next_turn():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    room = rooms.get(code)
    if not room or room["phase"] != "result":
        return jsonify({"ok": False, "error": "Not ready for next turn."})
    room["turn_index"] += 1
    room["last_result"] = None
    room["contest"] = None
    if room["turn_index"] >= len(room["queue"]):
        room["status"] = "gameover"
        room["phase"] = "gameover"
    else:
        room["phase"] = "asking"
    return jsonify({"ok": True})

@app.route("/api/state")
def api_state():
    code = (request.args.get("code") or "").strip().upper()
    name = (request.args.get("name") or "").strip()
    room = rooms.get(code)
    if not room:
        return jsonify({"ok": False, "error": "Room closed or not found."})

    if room["status"] == "lobby":
        in_room = (room["umpire_mode"] and room["umpire_name"] == name) or any(
            p["name"] == name for p in room["players"]
        )
        if not in_room:
            return jsonify({"ok": False, "kicked": True, "error": "You were removed from the lobby."})

    turn = None
    remaining = room["time_limit"]
    if room["status"] == "playing" and room["turn_index"] < len(room["queue"]):
        turn = room["queue"][room["turn_index"]]
        if room["phase"] == "guessing":
            remaining = max(0, round(room["time_limit"] - (time.time() - room["turn_start_time"]), 1))

    return jsonify({
        "ok": True,
        "code": room["code"],
        "host": room["host"],
        "umpire_mode": room["umpire_mode"],
        "umpire_name": room["umpire_name"],
        "max_players": room["max_players"],
        "questions_per_player": room["questions_per_player"],
        "time_limit": room["time_limit"],
        "players": room["players"],
        "standings": get_sorted_standings(room),
        "status": room["status"],
        "phase": room["phase"],
        "turn": turn,
        "turn_number": room["turn_index"] + 1,
        "total_turns": len(room["queue"]),
        "current_question": room["current_question"] if room["phase"] in ("guessing", "result", "contest_review") else "",
        "current_hint": room["current_hint"] if room["phase"] in ("guessing", "result", "contest_review") else "",
        "remaining": remaining,
        "last_result": room["last_result"],
        "contest": room["contest"],
    })

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Double Sage — Online Multiplayer</title>
<style>
  :root {
    --bg: #0b1120;
    --card: #131c31;
    --card2: #1a2642;
    --gold: #f5b942;
    --teal: #2dd4bf;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --danger: #f43f5e;
    --success: #10b981;
  }
  * { box-sizing: border-box; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }
  body { margin: 0; background: var(--bg); color: var(--text); min-height: 100vh; }
  .topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 18px; background: rgba(19, 28, 49, 0.95);
    border-bottom: 1px solid rgba(245, 185, 66, 0.25); position: sticky; top: 0; z-index: 20;
  }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 1.2rem; color: var(--gold); letter-spacing: 0.5px; }
  .brand img { width: 38px; height: 38px; border-radius: 10px; object-fit: cover; border: 1.5px solid var(--gold); }
  .sfx-btn {
    background: var(--card2); color: var(--teal); border: 1px solid rgba(45, 212, 191, 0.4);
    padding: 6px 12px; border-radius: 20px; font-size: 0.82rem; font-weight: 700; cursor: pointer;
  }
  .container { max-width: 680px; margin: 0 auto; padding: 18px 14px 50px; }
  .hero-box { margin-bottom: 18px; }
  .hero-banner {
    width: 100%; border-radius: 14px; overflow: hidden; border: 1px solid rgba(245,185,66,0.3);
    box-shadow: 0 10px 25px rgba(0,0,0,0.45); margin-bottom: 10px; background: var(--card);
  }
  .hero-banner img { width: 100%; max-height: 220px; object-fit: cover; display: block; }
  .hero-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .hero-thumb {
    border-radius: 12px; overflow: hidden; border: 1px solid rgba(45,212,191,0.28);
    background: var(--card); position: relative;
  }
  .hero-thumb img { width: 100%; height: 125px; object-fit: cover; display: block; }
  .hero-cap {
    position: absolute; bottom: 0; left: 0; right: 0; padding: 5px 8px;
    background: linear-gradient(transparent, rgba(11,17,32,0.92));
    font-size: 0.74rem; font-weight: 700; color: var(--gold); text-align: center;
  }
  .card {
    background: var(--card); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; padding: 18px; margin-bottom: 16px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  }
  h2, h3 { margin-top: 0; color: var(--gold); }
  label { display: block; font-size: 0.85rem; color: var(--muted); margin: 10px 0 5px; font-weight: 600; }
  input, select, textarea {
    width: 100%; padding: 11px 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.14);
    background: var(--card2); color: var(--text); font-size: 0.98rem;
  }
  input:focus, select:focus, textarea:focus { outline: none; border-color: var(--gold); }
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .btn {
    width: 100%; padding: 12px; border: none; border-radius: 11px; font-size: 0.98rem;
    font-weight: 800; cursor: pointer; margin-top: 12px; transition: transform 0.08s;
  }
  .btn:active { transform: scale(0.98); }
  .btn-gold { background: linear-gradient(135deg, #f5b942, #d97706); color: #0b1120; }
  .btn-teal { background: linear-gradient(135deg, #2dd4bf, #0d9488); color: #0b1120; }
  .btn-dark { background: var(--card2); color: var(--text); border: 1px solid rgba(255,255,255,0.15); }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-sm { padding: 7px 11px; font-size: 0.82rem; width: auto; margin-top: 0; }
  .pill {
    display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 0.78rem;
    font-weight: 700; background: rgba(245,185,66,0.16); color: var(--gold);
  }
  .room-code-box {
    text-align: center; padding: 14px; background: var(--card2); border-radius: 14px;
    border: 1.5px dashed var(--gold); margin-bottom: 12px;
  }
  .room-code { font-size: 2.2rem; font-weight: 900; letter-spacing: 6px; color: var(--gold); }
  .player-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 12px; background: var(--card2); border-radius: 10px; margin-bottom: 8px;
  }
  .hint-box {
    background: rgba(45, 212, 191, 0.12); border: 1px solid var(--teal);
    color: var(--teal); padding: 12px; border-radius: 12px; font-weight: 800;
    text-align: center; margin: 12px 0; font-size: 1.05rem;
  }
  .timer-bar {
    font-size: 1.4rem; font-weight: 900; text-align: center; padding: 8px;
    border-radius: 10px; background: var(--card2); color: var(--gold); margin-bottom: 10px;
  }
  .timer-urgent { color: var(--danger); border: 1px solid var(--danger); }
  .hidden { display: none !important; }
  .qb-item {
    background: var(--card2); padding: 10px; border-radius: 10px; margin-bottom: 8px;
    display: flex; justify-content: space-between; align-items: center; gap: 8px;
  }
  .chk-row { display: flex; align-items: center; gap: 10px; margin-top: 12px; cursor: pointer; }
  .chk-row input { width: 18px; height: 18px; margin: 0; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  th, td { padding: 9px 8px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.08); font-size: 0.9rem; }
  th { color: var(--muted); font-size: 0.8rem; }
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <img id="navIcon" src="/media/double_sage_icon" alt="Icon" onerror="this.style.display='none'">
    <span>DOUBLE SAGE</span>
  </div>
  <div style="display:flex; gap:8px; align-items:center;">
    <button class="sfx-btn" onclick="openQbModal()">📚 My QB's</button>
    <button id="sfxBtn" class="sfx-btn" onclick="toggleSfx()">🔊 SFX ON</button>
  </div>
</div>

<div class="container">
  <!-- HOME / LANDING VIEW -->
  <div id="viewHome">
    <div class="hero-box" id="heroShowcase">
      <div class="hero-banner" id="bannerWrap">
        <img src="/media/double_sage_banner" alt="Double Sage Banner" onerror="document.getElementById('bannerWrap').style.display='none'">
      </div>
      <div class="hero-grid" id="galleryWrap">
        <div class="hero-thumb" id="battleWrap">
          <img src="/media/double_sage_battle" alt="1v1 Battle" onerror="document.getElementById('battleWrap').style.display='none'">
          <div class="hero-cap">⚔️ 1v1 MIND DUEL</div>
        </div>
        <div class="hero-thumb" id="tourneyWrap">
          <img src="/media/double_sage_tournament" alt="Tournament & Team Clash" onerror="document.getElementById('tourneyWrap').style.display='none'">
          <div class="hero-cap">🏆 TOURNAMENT & CLASH</div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Join an Online Room</h2>
      <label>Your Player Name</label>
      <input id="joinName" placeholder="Enter your name">
      <label>4-Letter Room Code</label>
      <input id="joinCode" placeholder="e.g. A7K2" maxlength="4" style="text-transform:uppercase; font-weight:800; letter-spacing:3px;">
      <button class="btn btn-teal" onclick="joinRoom()">Join Room</button>
    </div>

    <div class="card">
      <h2>Create a New Room</h2>
      <label>Your Name (Host / Umpire)</label>
      <input id="hostName" placeholder="Enter your name">
      <div class="row2">
        <div>
          <label>Competing Players (2–10)</label>
          <select id="maxPlayers">
            <option value="2" selected>2 Players</option>
            <option value="3">3 Players</option>
            <option value="4">4 Players</option>
            <option value="5">5 Players</option>
            <option value="6">6 Players</option>
            <option value="8">8 Players</option>
            <option value="10">10 Players</option>
          </select>
        </div>
        <div>
          <label>Questions Per Player</label>
          <select id="qPerPlayer">
            <option value="1">1 Question</option>
            <option value="2">2 Questions</option>
            <option value="3" selected>3 Questions</option>
            <option value="5">5 Questions</option>
            <option value="7">7 Questions</option>
            <option value="10">10 Questions</option>
          </select>
        </div>
      </div>
      <label>Answer Time Limit (Same for All Players)</label>
      <select id="timeLimit">
        <option value="10">10 Seconds</option>
        <option value="15">15 Seconds</option>
        <option value="20">20 Seconds</option>
        <option value="30" selected>30 Seconds</option>
        <option value="45">45 Seconds</option>
        <option value="60">60 Seconds</option>
      </select>
      <label class="chk-row">
        <input type="checkbox" id="umpireMode">
        <span><b>Umpire (Organizer) Mode</b> — You organize & set all questions without playing (Umpire rulings are final)</span>
      </label>
      <button class="btn btn-gold" onclick="createRoom()">Create Room & Get Code</button>
    </div>
  </div>

  <!-- LOBBY VIEW -->
  <div id="viewLobby" class="hidden">
    <div class="card">
      <div class="room-code-box">
        <div style="font-size:0.8rem; color:var(--muted);">SHARE THIS ROOM CODE</div>
        <div class="room-code" id="lobbyCode">----</div>
        <button class="btn btn-dark btn-sm" onclick="copyInviteLink()">🔗 Copy One-Tap Invite Link</button>
      </div>
      <div id="lobbyMeta" style="margin-bottom:12px; font-size:0.9rem; color:var(--muted);"></div>
      <h3>Joined Players</h3>
      <div id="lobbyPlayers"></div>
      <button id="startMatchBtn" class="btn btn-gold hidden" onclick="startMatch()">🚀 Start Match</button>
      <div id="waitingHostMsg" style="text-align:center; color:var(--muted); margin-top:10px;">Waiting for host to start the match...</div>
    </div>
  </div>

  <!-- GAME VIEW -->
  <div id="viewGame" class="hidden">
    <div class="card" style="padding:12px 16px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span class="pill" id="turnBadge">Turn 1</span>
        <span style="font-size:0.85rem; color:var(--muted);" id="roleInfo"></span>
      </div>
    </div>

    <!-- ASKING PHASE -->
    <div id="phaseAsking" class="card hidden">
      <h3 id="askHeader">Set Your Question</h3>

      <!-- Starter Prompt & QB Picker (Protected from polling reset) -->
      <div style="background:var(--card2); padding:12px; border-radius:12px; margin-bottom:12px; border:1px solid rgba(245,185,66,0.22);">
        <div style="font-size:0.82rem; font-weight:700; color:var(--gold); margin-bottom:6px;">⚡ Quick Fill (Editable Before Locking)</div>
        <div class="row2">
          <select id="starterSelect" onchange="loadStarterPrompt()">
            <option value="">-- Pick Starter Prompt --</option>
          </select>
          <select id="qbSelect" onchange="loadSavedQb()">
            <option value="">-- Pick From My QB's --</option>
          </select>
        </div>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button type="button" class="btn btn-dark btn-sm" onclick="loadNextUnusedQb()">⏭️ Next Unused QB</button>
          <button type="button" class="btn btn-dark btn-sm" onclick="saveCurrentToQb()">💾 Save to My QB's</button>
        </div>
      </div>

      <label>Question for Guesser</label>
      <textarea id="inputQuestion" rows="2" placeholder="Type your question here..."></textarea>
      <label>Secret Answer (Hidden from Guesser)</label>
      <input id="inputAnswer" placeholder="Type exact secret answer...">
      <button class="btn btn-gold" onclick="submitQuestion()">🔒 Lock Question & Start Timer</button>
    </div>

    <div id="phaseWaitAsker" class="card hidden" style="text-align:center;">
      <h3 id="waitAskerTitle">Waiting for Question...</h3>
      <p style="color:var(--muted);">The Manager is waiting for the question to be locked in.</p>
    </div>

    <!-- GUESSING PHASE -->
    <div id="phaseGuessing" class="card hidden">
      <div class="timer-bar" id="timerDisplay">30s</div>
      <div style="font-size:0.85rem; color:var(--muted);">QUESTION:</div>
      <div style="font-size:1.25rem; font-weight:800; margin:6px 0;" id="displayQuestion"></div>
      <div class="hint-box" id="displayHint">MANAGER HINT: ...</div>

      <div id="guesserControls" class="hidden">
        <label>Your Answer</label>
        <input id="inputGuess" placeholder="Type your guess fast..." onkeydown="if(event.key==='Enter') submitGuess(false)">
        <button class="btn btn-teal" onclick="submitGuess(false)">✅ Submit Answer</button>
      </div>
      <div id="spectatorGuessMsg" class="hidden" style="text-align:center; color:var(--muted); margin-top:10px;">
        Watching active guesser...
      </div>
    </div>

    <!-- RESULT PHASE -->
    <div id="phaseResult" class="card hidden">
      <h3 id="resultHeadline">Round Result</h3>
      <p id="resultDetails" style="line-height:1.5;"></p>
      <div id="resolutionBanner" class="hint-box hidden"></div>

      <!-- Contest Box (Only for Guesser in Standard Mode when marked wrong) -->
      <div id="contestBox" class="hidden" style="margin-top:12px; padding:12px; background:var(--card2); border-radius:12px; border:1px solid var(--danger);">
        <div style="font-size:0.85rem; color:var(--danger); font-weight:700; margin-bottom:6px;">Think your answer was actually right?</div>
        <input id="contestReason" placeholder="Optional note (e.g., minor spelling typo)">
        <button class="btn btn-danger" onclick="raiseContest()">⚖️ CONTEST ANSWER (Ask Asker to Review)</button>
      </div>

      <button id="nextTurnBtn" class="btn btn-gold hidden" onclick="nextTurn()">➡️ Next Turn</button>
    </div>

    <!-- CONTEST APPROVAL PHASE -->
    <div id="phaseContest" class="card hidden">
      <h3 style="color:var(--danger);">⚖️ Answer Contested!</h3>
      <p id="contestDetails" style="line-height:1.5;"></p>
      <div id="askerContestControls" class="hidden">
        <button class="btn btn-teal" onclick="resolveContest('accept_guess')">✅ Accept Guess (+5 Pts to Guesser)</button>
        <button class="btn btn-gold" onclick="resolveContest('new_question')">🔄 Void & Send New Question (0 Pts)</button>
      </div>
      <div id="waitContestMsg" class="hidden" style="color:var(--muted); text-align:center;">
        Waiting for the Asker to accept the guess or send a new question...
      </div>
    </div>

    <!-- LIVE SCOREBOARD -->
    <div class="card">
      <h3>📊 Live Standings (Tie-Breaker: Shortest Time)</h3>
      <table>
        <thead><tr><th>#</th><th>Player</th><th>Points</th><th>Time Spent</th></tr></thead>
        <tbody id="liveScoreBody"></tbody>
      </table>
    </div>
  </div>

  <!-- GAME OVER VIEW -->
  <div id="viewGameOver" class="hidden">
    <div class="card" style="text-align:center;">
      <div style="font-size:2.4rem;">🏆</div>
      <h2 id="winnerBanner">Champion!</h2>
      <p style="color:var(--muted);">Ties are broken automatically by shortest total answering time.</p>
      <table>
        <thead><tr><th>Rank</th><th>Player</th><th>Points</th><th>Total Time</th></tr></thead>
        <tbody id="finalScoreBody"></tbody>
      </table>
      <button class="btn btn-gold" onclick="location.href='/'">🏠 Back to Home</button>
    </div>
  </div>
</div>

<!-- MY QB'S MODAL -->
<div id="qbModal" class="hidden" style="position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:50; overflow-y:auto; padding:16px;">
  <div class="card" style="max-width:560px; margin:20px auto;">
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <h3>📚 My QB's (Saved Question Banks)</h3>
      <button class="btn btn-dark btn-sm" onclick="closeQbModal()">✕ Close</button>
    </div>
    <p style="font-size:0.85rem; color:var(--muted);">Save questions and answers on your phone so you can pick them in one tap during any round.</p>
    <label>New Question</label>
    <input id="newQbQ" placeholder="e.g. Who scored the fastest Premier League hat-trick?">
    <label>Secret Answer</label>
    <input id="newQbA" placeholder="e.g. Sadio Mane">
    <button class="btn btn-teal" onclick="addQbFromModal()">➕ Save to My QB's</button>
    <hr style="border-color:rgba(255,255,255,0.1); margin:16px 0;">
    <div id="qbListContainer"></div>
  </div>
</div>

<script>
const STARTERS = """ + repr([{"cat": c, "q": q, "a": a} for c, q, a in STARTER_PROMPTS]) + """;
let myName = "";
let roomCode = "";
let sfxEnabled = true;
let audioCtx = null;
let lastPhaseKey = "";
let lastTickSec = -1;
let autoSubmittedTimeout = false;
let usedQbIndices = new Set();

function initAudio() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audioCtx = new AC();
  }
}

function playTone(freq, duration, type="sine", delay=0) {
  if (!sfxEnabled) return;
  try {
    initAudio();
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime + delay);
    gain.gain.setValueAtTime(0.14, audioCtx.currentTime + delay);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + delay + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start(audioCtx.currentTime + delay);
    osc.stop(audioCtx.currentTime + delay + duration);
  } catch (e) {}
}

function vibe(ms) {
  if (sfxEnabled && navigator.vibrate) {
    try { navigator.vibrate(ms); } catch (e) {}
  }
}

function sfxLock() { playTone(520, 0.12, "triangle", 0); playTone(780, 0.18, "triangle", 0.1); vibe(40); }
function sfxTick(urgent) { playTone(urgent ? 880 : 440, 0.06, "sine", 0); if (urgent) vibe(30); }
function sfxWin() { playTone(523, 0.14, "triangle", 0); playTone(659, 0.14, "triangle", 0.12); playTone(784, 0.25, "triangle", 0.24); vibe([50,40,80]); }
function sfxWrong() { playTone(220, 0.25, "sawtooth", 0); playTone(165, 0.3, "sawtooth", 0.18); vibe(120); }
function sfxContest() { playTone(600, 0.12, "square", 0); playTone(450, 0.18, "square", 0.12); vibe([60,50,60]); }

function toggleSfx() {
  sfxEnabled = !sfxEnabled;
  document.getElementById("sfxBtn").textContent = sfxEnabled ? "🔊 SFX ON" : "🔇 SFX OFF";
  if (sfxEnabled) playTone(660, 0.1);
}

// QB's LocalStorage Helpers
function getQbs() {
  try { return JSON.parse(localStorage.getItem("double_sage_qbs") || "[]"); }
  catch (e) { return []; }
}
function saveQbs(list) {
  localStorage.setItem("double_sage_qbs", JSON.stringify(list));
  refreshQbDropdown();
}

function populateStarterDropdown() {
  const sel = document.getElementById("starterSelect");
  sel.innerHTML = '<option value="">-- Pick Starter Prompt --</option>';
  STARTERS.forEach((item, idx) => {
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = `[${item.cat}] ${item.q}`;
    sel.appendChild(opt);
  });
}

function refreshQbDropdown() {
  const sel = document.getElementById("qbSelect");
  if (!sel) return;
  const currentVal = sel.value;
  const qbs = getQbs();
  sel.innerHTML = `<option value="">-- Pick From My QB's (${qbs.length}) --</option>`;
  qbs.forEach((item, idx) => {
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = `${usedQbIndices.has(idx) ? '✓ ' : ''}${item.q}`;
    sel.appendChild(opt);
  });
  sel.value = currentVal;
}

function loadStarterPrompt() {
  const idx = document.getElementById("starterSelect").value;
  if (idx === "") return;
  const item = STARTERS[parseInt(idx, 10)];
  document.getElementById("inputQuestion").value = item.q;
  document.getElementById("inputAnswer").value = item.a;
  playTone(540, 0.08);
}

function loadSavedQb() {
  const idx = document.getElementById("qbSelect").value;
  if (idx === "") return;
  const i = parseInt(idx, 10);
  const qbs = getQbs();
  if (qbs[i]) {
    document.getElementById("inputQuestion").value = qbs[i].q;
    document.getElementById("inputAnswer").value = qbs[i].a;
    usedQbIndices.add(i);
    refreshQbDropdown();
    playTone(620, 0.08);
  }
}

function loadNextUnusedQb() {
  const qbs = getQbs();
  if (!qbs.length) { alert("Your QB's bank is empty! Add questions in My QB's first."); return; }
  let found = -1;
  for (let i = 0; i < qbs.length; i++) {
    if (!usedQbIndices.has(i)) { found = i; break; }
  }
  if (found === -1) { usedQbIndices.clear(); found = 0; }
  document.getElementById("inputQuestion").value = qbs[found].q;
  document.getElementById("inputAnswer").value = qbs[found].a;
  usedQbIndices.add(found);
  refreshQbDropdown();
  playTone(660, 0.1);
}

function saveCurrentToQb() {
  const q = document.getElementById("inputQuestion").value.trim();
  const a = document.getElementById("inputAnswer").value.trim();
  if (!q || !a) { alert("Type both a question and answer first."); return; }
  const qbs = getQbs();
  qbs.push({ q, a });
  saveQbs(qbs);
  playTone(740, 0.12);
  alert("Saved to My QB's!");
}

function openQbModal() {
  renderQbModalList();
  document.getElementById("qbModal").classList.remove("hidden");
}
function closeQbModal() {
  document.getElementById("qbModal").classList.add("hidden");
}
function addQbFromModal() {
  const q = document.getElementById("newQbQ").value.trim();
  const a = document.getElementById("newQbA").value.trim();
  if (!q || !a) { alert("Enter both a question and secret answer."); return; }
  const qbs = getQbs();
  qbs.push({ q, a });
  saveQbs(qbs);
  document.getElementById("newQbQ").value = "";
  document.getElementById("newQbA").value = "";
  renderQbModalList();
  playTone(720, 0.1);
}
function deleteQb(idx) {
  const qbs = getQbs();
  qbs.splice(idx, 1);
  usedQbIndices.clear();
  saveQbs(qbs);
  renderQbModalList();
}
function renderQbModalList() {
  const box = document.getElementById("qbListContainer");
  const qbs = getQbs();
  if (!qbs.length) {
    box.innerHTML = '<div style="color:var(--muted); text-align:center;">No saved questions yet.</div>';
    return;
  }
  box.innerHTML = qbs.map((item, i) => `
    <div class="qb-item">
      <div>
        <div style="font-weight:700; font-size:0.92rem;">${escapeHtml(item.q)}</div>
        <div style="font-size:0.8rem; color:var(--teal);">Answer: ${escapeHtml(item.a)}</div>
      </div>
      <button class="btn btn-danger btn-sm" onclick="deleteQb(${i})">🗑️</button>
    </div>
  `).join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

async function createRoom() {
  initAudio();
  const name = document.getElementById("hostName").value.trim();
  if (!name) { alert("Enter your name first."); return; }
  const res = await fetch("/api/create", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      name,
      max_players: document.getElementById("maxPlayers").value,
      questions_per_player: document.getElementById("qPerPlayer").value,
      time_limit: document.getElementById("timeLimit").value,
      umpire_mode: document.getElementById("umpireMode").checked
    })
  });
  const data = await res.json();
  if (!data.ok) { alert(data.error); return; }
  myName = data.name;
  roomCode = data.code;
  sfxLock();
  startPolling();
}

async function joinRoom() {
  initAudio();
  const name = document.getElementById("joinName").value.trim();
  const code = document.getElementById("joinCode").value.trim().toUpperCase();
  if (!name || !code) { alert("Enter both your name and the 4-letter room code."); return; }
  const res = await fetch("/api/join", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ name, code })
  });
  const data = await res.json();
  if (!data.ok) { alert(data.error); return; }
  myName = data.name;
  roomCode = data.code;
  sfxLock();
  startPolling();
}

function copyInviteLink() {
  const url = `${location.origin}/?room=${roomCode}`;
  navigator.clipboard.writeText(url).then(() => alert("Invite link copied: " + url));
}

async function kickPlayer(target) {
  await fetch("/api/kick", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ code: roomCode, requester: myName, target })
  });
}

async function startMatch() {
  const res = await fetch("/api/start", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ code: roomCode, requester: myName })
  });
  const data = await res.json();
  if (!data.ok) alert(data.error);
}

async function submitQuestion() {
  const question = document.getElementById("inputQuestion").value.trim();
  const answer = document.getElementById("inputAnswer").value.trim();
  if (!question || !answer) { alert("Enter both a question and secret answer."); return; }
  const res = await fetch("/api/set_question", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ code: roomCode, name: myName, question, answer })
  });
  const data = await res.json();
  if (!data.ok) { alert(data.error); return; }
  document.getElementById("inputQuestion").value = "";
  document.getElementById("inputAnswer").value = "";
  document.getElementById("starterSelect").value = "";
  document.getElementById("qbSelect").value = "";
  sfxLock();
}

async function submitGuess(timedOut) {
  const guess = document.getElementById("inputGuess").value.trim();
  await fetch("/api/submit_guess", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ code: roomCode, name: myName, guess, timed_out: timedOut })
  });
  document.getElementById("inputGuess").value = "";
}

async function raiseContest() {
  const reason = document.getElementById("contestReason").value.trim();
  await fetch("/api/contest", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ code: roomCode, name: myName, reason })
  });
  sfxContest();
}

async function resolveContest(decision) {
  await fetch("/api/resolve_contest", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ code: roomCode, name: myName, decision })
  });
}

async function nextTurn() {
  await fetch("/api/next_turn", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ code: roomCode })
  });
}

let pollTimer = null;
function startPolling() {
  document.getElementById("viewHome").classList.add("hidden");
  if (pollTimer) clearInterval(pollTimer);
  fetchState();
  pollTimer = setInterval(fetchState, 1200);
}

async function fetchState() {
  if (!roomCode) return;
  const res = await fetch(`/api/state?code=${encodeURIComponent(roomCode)}&name=${encodeURIComponent(myName)}`);
  const st = await res.json();
  if (!st.ok) {
    if (st.kicked) {
      clearInterval(pollTimer);
      alert(st.error);
      location.href = "/";
    }
    return;
  }

  document.getElementById("viewLobby").classList.toggle("hidden", st.status !== "lobby");
  document.getElementById("viewGame").classList.toggle("hidden", st.status !== "playing");
  document.getElementById("viewGameOver").classList.toggle("hidden", st.status !== "gameover");

  if (st.status === "lobby") {
    document.getElementById("lobbyCode").textContent = st.code;
    document.getElementById("lobbyMeta").textContent =
      `${st.umpire_mode ? '⚖️ Umpire Mode (' + st.umpire_name + ') • ' : ''}Up to ${st.max_players} players • ${st.questions_per_player} Qs each • ${st.time_limit}s timer`;

    const isHost = (st.host === myName);
    document.getElementById("lobbyPlayers").innerHTML = st.players.map(p => `
      <div class="player-item">
        <span><b>${escapeHtml(p.name)}</b> ${p.name === st.host ? '<span class="pill">HOST</span>' : ''}</span>
        ${isHost && p.name !== myName ? `<button class="btn btn-danger btn-sm" onclick="kickPlayer('${escapeHtml(p.name)}')">Kick</button>` : ''}
      </div>
    `).join("") || '<div style="color:var(--muted);">Waiting for competing players to join...</div>';

    document.getElementById("startMatchBtn").classList.toggle("hidden", !isHost);
    document.getElementById("waitingHostMsg").classList.toggle("hidden", isHost);
  }

  if (st.status === "playing" && st.turn) {
    const phaseKey = `${st.turn_number}-${st.phase}`;
    const phaseChanged = (phaseKey !== lastPhaseKey);
    lastPhaseKey = phaseKey;

    document.getElementById("turnBadge").textContent = `Turn ${st.turn_number} of ${st.total_turns}`;
    document.getElementById("roleInfo").textContent = `Asker: ${st.turn.asker} → Guesser: ${st.turn.guesser}`;

    const isAsker = (st.turn.asker === myName);
    const isGuesser = (st.turn.guesser === myName);

    document.getElementById("phaseAsking").classList.toggle("hidden", !(st.phase === "asking" && isAsker));
    document.getElementById("phaseWaitAsker").classList.toggle("hidden", !(st.phase === "asking" && !isAsker));
    document.getElementById("phaseGuessing").classList.toggle("hidden", st.phase !== "guessing");
    document.getElementById("phaseResult").classList.toggle("hidden", st.phase !== "result");
    document.getElementById("phaseContest").classList.toggle("hidden", st.phase !== "contest_review");

    if (st.phase === "asking") {
      autoSubmittedTimeout = false;
      if (isAsker && phaseChanged) {
        document.getElementById("askHeader").textContent = `Set Question for ${st.turn.guesser}`;
        refreshQbDropdown();
      } else if (!isAsker) {
        document.getElementById("waitAskerTitle").textContent = `${st.turn.asker} is preparing a question for ${st.turn.guesser}...`;
      }
    }

    if (st.phase === "guessing") {
      const rem = Math.ceil(st.remaining);
      const tEl = document.getElementById("timerDisplay");
      tEl.textContent = `⏱️ ${rem}s`;
      tEl.classList.toggle("timer-urgent", rem <= 5);
      if (rem !== lastTickSec && rem > 0) {
        lastTickSec = rem;
        sfxTick(rem <= 5);
      }
      document.getElementById("displayQuestion").textContent = st.current_question;
      document.getElementById("displayHint").textContent = `MANAGER HINT: ${st.current_hint}`;
      document.getElementById("guesserControls").classList.toggle("hidden", !isGuesser);
      document.getElementById("spectatorGuessMsg").classList.toggle("hidden", isGuesser);

      if (isGuesser && st.remaining <= 0 && !autoSubmittedTimeout) {
        autoSubmittedTimeout = true;
        submitGuess(true);
      }
    }

    if (st.phase === "result" && st.last_result) {
      const r = st.last_result;
      if (phaseChanged) { r.correct ? sfxWin() : sfxWrong(); }
      document.getElementById("resultHeadline").textContent = r.correct
        ? `✅ Spot On! +5 Pts to ${r.guesser}`
        : (r.is_umpire ? `❌ Incorrect! (Umpire Ruling Final)` : `❌ Missed! +5 Pts to ${r.asker}`);
      document.getElementById("resultDetails").innerHTML =
        `<b>Question:</b> ${escapeHtml(r.question)}<br>` +
        `<b>${escapeHtml(r.guesser)}'s Guess:</b> ${escapeHtml(r.guess)} (${r.elapsed}s)<br>` +
        `<b>Secret Answer:</b> <span style="color:var(--gold); font-weight:800;">${escapeHtml(r.answer)}</span>`;

      const resBan = document.getElementById("resolutionBanner");
      if (r.resolution_note) {
        resBan.textContent = r.resolution_note;
        resBan.classList.remove("hidden");
      } else {
        resBan.classList.add("hidden");
      }

      const canContest = (!r.is_umpire && isGuesser && !r.correct && !r.contested);
      document.getElementById("contestBox").classList.toggle("hidden", !canContest);
      const canAdvance = (isAsker || st.host === myName);
      document.getElementById("nextTurnBtn").classList.toggle("hidden", !canAdvance);
    }

    if (st.phase === "contest_review" && st.contest && st.last_result) {
      if (phaseChanged) sfxContest();
      const c = st.contest;
      const r = st.last_result;
      document.getElementById("contestDetails").innerHTML =
        `<b>${escapeHtml(c.guesser)}</b> contested the result!<br>` +
        `<b>Typed Guess:</b> ${escapeHtml(r.guess)}<br>` +
        `<b>Secret Answer:</b> ${escapeHtml(r.answer)}<br>` +
        `<b>Reason:</b> ${escapeHtml(c.reason)}`;
      document.getElementById("askerContestControls").classList.toggle("hidden", !isAsker);
      document.getElementById("waitContestMsg").classList.toggle("hidden", isAsker);
    }

    document.getElementById("liveScoreBody").innerHTML = st.standings.map((p, idx) => `
      <tr>
        <td><b>#${idx + 1}</b></td>
        <td>${escapeHtml(p.name)}</td>
        <td style="color:var(--gold); font-weight:800;">${p.score} pts</td>
        <td>${p.time_spent.toFixed(1)}s</td>
      </tr>
    `).join("");
  }

  if (st.status === "gameover") {
    if (lastPhaseKey !== "gameover") { lastPhaseKey = "gameover"; sfxWin(); }
    const champ = st.standings[0];
    document.getElementById("winnerBanner").textContent = champ
      ? `Champion: ${champ.name} (${champ.score} pts • ${champ.time_spent.toFixed(1)}s)`
      : "Match Complete!";
    document.getElementById("finalScoreBody").innerHTML = st.standings.map((p, idx) => `
      <tr>
        <td><b>#${idx + 1}</b></td>
        <td>${escapeHtml(p.name)}</td>
        <td style="color:var(--gold); font-weight:800;">${p.score} pts</td>
        <td>${p.time_spent.toFixed(1)}s</td>
      </tr>
    `).join("");
  }
}

// Init on load
populateStarterDropdown();
refreshQbDropdown();
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get("room")) {
  document.getElementById("joinCode").value = urlParams.get("room").toUpperCase();
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return HTML_PAGE

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

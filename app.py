import os
import random
import string
import time
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

ROOMS = {}

STARTER_PROMPTS = [
    {"cat": "General", "q": "What is the largest ocean on Earth?", "a": "Pacific Ocean"},
    {"cat": "General", "q": "How many days are in a leap year?", "a": "366"},
    {"cat": "General", "q": "What is the capital city of Nigeria?", "a": "Abuja"},
    {"cat": "General", "q": "Which planet is known as the Red Planet?", "a": "Mars"},
    {"cat": "General", "q": "How many continents are there on Earth?", "a": "7"},
    {"cat": "General", "q": "What is the fastest land animal?", "a": "Cheetah"},
    {"cat": "General", "q": "Which gas do plants absorb from the air?", "a": "Carbon dioxide"},
    {"cat": "Science", "q": "What is the chemical symbol for gold?", "a": "Au"},
    {"cat": "Science", "q": "At what temperature in Celsius does water boil?", "a": "100"},
    {"cat": "Science", "q": "How many bones are in an adult human body?", "a": "206"},
    {"cat": "Science", "q": "What is the center of an atom called?", "a": "Nucleus"},
    {"cat": "Science", "q": "Which organ pumps blood through the human body?", "a": "Heart"},
    {"cat": "History", "q": "In what year did Nigeria gain independence?", "a": "1960"},
    {"cat": "History", "q": "Who was the first person to walk on the Moon?", "a": "Neil Armstrong"},
    {"cat": "History", "q": "In which country are the Great Pyramids of Giza located?", "a": "Egypt"},
    {"cat": "History", "q": "Which ancient ship sank in 1912 after hitting an iceberg?", "a": "Titanic"},
    {"cat": "Sports", "q": "How many players are on a standard football pitch per team?", "a": "11"},
    {"cat": "Sports", "q": "Which country won the 2022 FIFA World Cup?", "a": "Argentina"},
    {"cat": "Sports", "q": "How many rings are on the Olympic flag?", "a": "5"},
    {"cat": "Sports", "q": "In basketball, how many points is a shot beyond the arc worth?", "a": "3"},
    {"cat": "Pop Culture", "q": "Who is known as the King of Pop?", "a": "Michael Jackson"},
    {"cat": "Pop Culture", "q": "What is the name of Batman's home city?", "a": "Gotham City"},
    {"cat": "Pop Culture", "q": "How many strings does a standard guitar have?", "a": "6"},
    {"cat": "Pop Culture", "q": "Which superhero is also known as Clark Kent?", "a": "Superman"}
]


def gen_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase, k=4))
        if code not in ROOMS:
            return code


def build_hint(ans):
    clean = ans.strip()
    words = len([w for w in clean.split() if w])
    letters = sum(1 for c in clean if c.isalpha())
    digits = sum(1 for c in clean if c.isdigit())
    parts = [f"{words} word{'s' if words != 1 else ''}", f"{letters} letter{'s' if letters != 1 else ''}"]
    if digits > 0:
        parts.append(f"{digits} digit{'s' if digits != 1 else ''}")
    return " | ".join(parts)


def norm(s):
    return "".join(c.lower() for c in (s or "").strip() if c.isalnum())


def check_time_expired(room):
    if room["phase"] == "guessing" and room["turn_start"]:
        elapsed = time.time() - room["turn_start"]
        if elapsed >= room["time_limit"]:
            guesser = room["players"][room["guesser_idx"]]
            asker_name = room["umpire"]["name"] if room["umpire"] else room["players"][room["asker_idx"]]["name"]
            guesser["time"] += room["time_limit"]
            if not room["umpire"]:
                room["players"][room["asker_idx"]]["score"] += 5
            room["last_result"] = {
                "correct": False,
                "reason": "Time expired!",
                "guess": "(No answer in time)",
                "answer": room["current_a"],
                "question": room["current_q"],
                "guesser_id": guesser["id"],
                "guesser_name": guesser["name"],
                "asker_name": asker_name,
                "contested": False,
                "resolved": False
            }
            room["phase"] = "result"


@app.route("/media/<path:filename>")
def serve_media(filename):
    base_name = os.path.splitext(filename)[0].lower()
    short_name = base_name.replace("double_sage_", "")
    candidates = [
        filename,
        base_name + ".jpg",
        base_name + ".jpeg",
        base_name + ".png",
        short_name + ".jpg",
        short_name + ".jpeg",
        short_name + ".png",
    ]
    for folder in [".", "static"]:
        if os.path.isdir(folder):
            files_map = {f.lower(): f for f in os.listdir(folder)}
            for cand in candidates:
                if cand.lower() in files_map:
                    return send_from_directory(folder, files_map[cand.lower()])
    return ("Not Found", 404)


@app.route("/api/create", methods=["POST"])
def api_create():
    data = request.json or {}
    name = (data.get("name") or "Host").strip()[:18]
    pid = data.get("pid") or "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    max_players = max(2, min(10, int(data.get("max_players", 4))))
    q_per_player = max(1, min(10, int(data.get("q_per_player", 2))))
    time_limit = max(10, min(60, int(data.get("time_limit", 25))))
    umpire_mode = bool(data.get("umpire_mode", False))

    code = gen_code()
    room = {
        "code": code,
        "host_id": pid,
        "max_players": max_players,
        "q_per_player": q_per_player,
        "time_limit": time_limit,
        "umpire": {"id": pid, "name": name} if umpire_mode else None,
        "players": [] if umpire_mode else [{"id": pid, "name": name, "score": 0, "time": 0.0, "asked": 0}],
        "phase": "lobby",
        "asker_idx": 0,
        "guesser_idx": 0,
        "umpire_q_count": 0,
        "current_q": "",
        "current_a": "",
        "current_hint": "",
        "turn_start": 0.0,
        "last_result": None
    }
    ROOMS[code] = room
    return jsonify({"ok": True, "code": code, "pid": pid})


@app.route("/api/join", methods=["POST"])
def api_join():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "Player").strip()[:18]
    pid = data.get("pid") or "".join(random.choices(string.ascii_lowercase + string.digits, k=10))

    room = ROOMS.get(code)
    if not room:
        return jsonify({"ok": False, "error": "Room code not found."})
    if room["umpire"] and room["umpire"]["id"] == pid:
        return jsonify({"ok": True, "code": code, "pid": pid})
    for p in room["players"]:
        if p["id"] == pid:
            return jsonify({"ok": True, "code": code, "pid": pid})
    if room["phase"] != "lobby":
        return jsonify({"ok": False, "error": "Match already in progress."})
    if len(room["players"]) >= room["max_players"]:
        return jsonify({"ok": False, "error": "Room is full."})

    room["players"].append({"id": pid, "name": name, "score": 0, "time": 0.0, "asked": 0})
    return jsonify({"ok": True, "code": code, "pid": pid})


@app.route("/api/kick", methods=["POST"])
def api_kick():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "lobby":
        return jsonify({"ok": False})
    if data.get("pid") != room["host_id"]:
        return jsonify({"ok": False})
    target_id = data.get("target_id")
    room["players"] = [p for p in room["players"] if p["id"] != target_id]
    return jsonify({"ok": True})


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or data.get("pid") != room["host_id"]:
        return jsonify({"ok": False, "error": "Only host can start."})
    if len(room["players"]) < 2:
        return jsonify({"ok": False, "error": "Need at least 2 competing players."})

    room["phase"] = "asking"
    room["asker_idx"] = 0
    room["guesser_idx"] = 0 if room["umpire"] else 1
    return jsonify({"ok": True})


@app.route("/api/ask", methods=["POST"])
def api_ask():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "asking":
        return jsonify({"ok": False})
    pid = data.get("pid")
    expected_id = room["umpire"]["id"] if room["umpire"] else room["players"][room["asker_idx"]]["id"]
    if pid != expected_id:
        return jsonify({"ok": False, "error": "Not your turn to ask."})

    q = (data.get("q") or "").strip()
    a = (data.get("a") or "").strip()
    if not q or not a:
        return jsonify({"ok": False, "error": "Enter both a question and answer."})

    room["current_q"] = q
    room["current_a"] = a
    room["current_hint"] = build_hint(a)
    room["turn_start"] = time.time()
    room["phase"] = "guessing"
    return jsonify({"ok": True})


@app.route("/api/guess", methods=["POST"])
def api_guess():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "guessing":
        return jsonify({"ok": False})
    guesser = room["players"][room["guesser_idx"]]
    if data.get("pid") != guesser["id"]:
        return jsonify({"ok": False, "error": "Not your turn to guess."})

    elapsed = min(room["time_limit"], round(time.time() - room["turn_start"], 2))
    guess = (data.get("guess") or "").strip()
    correct = norm(guess) == norm(room["current_a"]) and len(norm(guess)) > 0

    guesser["time"] = round(guesser["time"] + elapsed, 2)
    asker_name = room["umpire"]["name"] if room["umpire"] else room["players"][room["asker_idx"]]["name"]

    if correct:
        guesser["score"] += 5
    else:
        if not room["umpire"]:
            room["players"][room["asker_idx"]]["score"] += 5

    room["last_result"] = {
        "correct": correct,
        "reason": "Spot on!" if correct else "Incorrect answer.",
        "guess": guess or "(Blank)",
        "answer": room["current_a"],
        "question": room["current_q"],
        "guesser_id": guesser["id"],
        "guesser_name": guesser["name"],
        "asker_name": asker_name,
        "contested": False,
        "resolved": False
    }
    room["phase"] = "result"
    return jsonify({"ok": True})


@app.route("/api/contest", methods=["POST"])
def api_contest():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "result" or room["umpire"]:
        return jsonify({"ok": False})
    res = room["last_result"]
    if not res or res["correct"] or res["contested"] or data.get("pid") != res["guesser_id"]:
        return jsonify({"ok": False})
    res["contested"] = True
    res["contest_note"] = (data.get("note") or "My answer is valid!").strip()[:100]
    return jsonify({"ok": True})


@app.route("/api/resolve_contest", methods=["POST"])
def api_resolve_contest():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "result" or room["umpire"]:
        return jsonify({"ok": False})
    asker = room["players"][room["asker_idx"]]
    if data.get("pid") != asker["id"]:
        return jsonify({"ok": False})
    res = room["last_result"]
    if not res or not res["contested"] or res["resolved"]:
        return jsonify({"ok": False})

    decision = data.get("decision")
    guesser = room["players"][room["guesser_idx"]]
    asker["score"] = max(0, asker["score"] - 5)

    if decision == "accept":
        guesser["score"] += 5
        res["correct"] = True
        res["resolved"] = True
        res["reason"] = "Contest Accepted! +5 Pts awarded to Guesser."
        return jsonify({"ok": True})
    else:
        room["current_q"] = ""
        room["current_a"] = ""
        room["last_result"] = None
        room["phase"] = "asking"
        return jsonify({"ok": True})


@app.route("/api/next", methods=["POST"])
def api_next():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "result":
        return jsonify({"ok": False})
    res = room["last_result"]
    if res and res.get("contested") and not res.get("resolved"):
        return jsonify({"ok": False, "error": "Waiting for Asker to resolve contest."})

    n = len(room["players"])
    if room["umpire"]:
        room["umpire_q_count"] += 1
        total_needed = n * room["q_per_player"]
        if room["umpire_q_count"] >= total_needed:
            room["phase"] = "gameover"
        else:
            room["guesser_idx"] = (room["guesser_idx"] + 1) % n
            room["phase"] = "asking"
    else:
        room["players"][room["asker_idx"]]["asked"] += 1
        if all(p["asked"] >= room["q_per_player"] for p in room["players"]):
            room["phase"] = "gameover"
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
        return jsonify({"ok": False, "error": "Room closed or not found."})

    check_time_expired(room)

    kicked = True
    if room["umpire"] and room["umpire"]["id"] == pid:
        kicked = False
    elif any(p["id"] == pid for p in room["players"]):
        kicked = False
    if kicked:
        return jsonify({"ok": False, "kicked": True, "error": "You were removed from the room."})

    remaining = 0
    if room["phase"] == "guessing":
        remaining = max(0, round(room["time_limit"] - (time.time() - room["turn_start"]), 1))

    asker_id = room["umpire"]["id"] if room["umpire"] else (room["players"][room["asker_idx"]]["id"] if room["players"] else "")
    asker_name = room["umpire"]["name"] if room["umpire"] else (room["players"][room["asker_idx"]]["name"] if room["players"] else "")
    guesser_id = room["players"][room["guesser_idx"]]["id"] if room["players"] else ""
    guesser_name = room["players"][room["guesser_idx"]]["name"] if room["players"] else ""

    sorted_players = sorted(room["players"], key=lambda x: (-x["score"], x["time"]))

    return jsonify({
        "ok": True,
        "code": room["code"],
        "host_id": room["host_id"],
        "max_players": room["max_players"],
        "q_per_player": room["q_per_player"],
        "time_limit": room["time_limit"],
        "umpire": room["umpire"],
        "players": room["players"],
        "leaderboard": sorted_players,
        "phase": room["phase"],
        "asker_id": asker_id,
        "asker_name": asker_name,
        "guesser_id": guesser_id,
        "guesser_name": guesser_name,
        "current_q": room["current_q"] if room["phase"] in ("guessing", "result") else "",
        "current_hint": room["current_hint"] if room["phase"] in ("guessing", "result") else "",
        "remaining": remaining,
        "last_result": room["last_result"],
        "prompts": STARTER_PROMPTS
    })


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Double Sage — Online Multiplayer</title>
<style>
  :root {
    --bg: #070b14;
    --card: #111827;
    --card2: #1e293b;
    --accent: #f59e0b;
    --accent2: #3b82f6;
    --green: #10b981;
    --red: #ef4444;
    --text: #f8fafc;
    --muted: #94a3b8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }
  body { background: var(--bg); color: var(--text); min-height: 100vh; padding-bottom: 40px; }

  #introOverlay {
    position: fixed;
    inset: 0;
    z-index: 99990;
    background: #070b14;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
    text-align: center;
  }
  #introOverlay img {
    max-width: 92%;
    max-height: 56vh;
    border-radius: 18px;
    border: 2px solid var(--accent);
    box-shadow: 0 12px 40px rgba(245, 158, 11, 0.35);
    object-fit: contain;
    background: #0f172a;
  }
  #introCaption { font-size: 1.25rem; font-weight: 800; color: var(--accent); margin-top: 14px; }
  .intro-bar-wrap { width: 80%; max-width: 360px; height: 8px; background: #1e293b; border-radius: 99px; overflow: hidden; margin: 12px auto; }
  #introBar { height: 100%; width: 0%; background: linear-gradient(90deg, var(--accent), #fbbf24); transition: width 0.1s linear; }
  .intro-actions { display: flex; gap: 12px; margin-top: 14px; flex-wrap: wrap; justify-content: center; position: relative; z-index: 99999; }
  #introOverlay button {
    position: relative;
    z-index: 99999 !important;
    pointer-events: auto !important;
    cursor: pointer;
    padding: 12px 20px;
    border-radius: 12px;
    font-weight: 800;
    font-size: 1rem;
    border: none;
  }
  .btn-sound-start { background: var(--green); color: #052e16; }
  .btn-skip-intro { background: var(--accent); color: #1e1b04; }

  header {
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid #1e293b;
    padding: 10px 14px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 900; font-size: 1.15rem; color: var(--accent); }
  .brand img { width: 34px; height: 34px; border-radius: 8px; object-fit: cover; border: 1px solid var(--accent); }
  .audio-bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .pill-btn {
    background: var(--card2);
    color: var(--text);
    border: 1px solid #334155;
    padding: 6px 10px;
    border-radius: 99px;
    font-size: 0.8rem;
    font-weight: 700;
    cursor: pointer;
  }
  .pill-btn.active { border-color: var(--accent); color: var(--accent); }
  input[type="range"] { width: 72px; accent-color: var(--accent); }

  .container { max-width: 680px; margin: 16px auto; padding: 0 14px; }
  .card { background: var(--card); border: 1px solid #1e293b; border-radius: 16px; padding: 18px; margin-bottom: 16px; }
  h2 { font-size: 1.2rem; margin-bottom: 12px; color: var(--accent); }
  label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 5px; font-weight: 600; }
  input[type="text"], input[type="number"], select, textarea {
    width: 100%;
    padding: 12px;
    border-radius: 10px;
    border: 1px solid #334155;
    background: #0f172a;
    color: var(--text);
    font-size: 1rem;
    margin-bottom: 12px;
  }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .btn {
    width: 100%;
    padding: 13px;
    border-radius: 12px;
    border: none;
    font-weight: 800;
    font-size: 1rem;
    cursor: pointer;
    margin-bottom: 8px;
  }
  .btn-primary { background: var(--accent); color: #1c1917; }
  .btn-blue { background: var(--accent2); color: #fff; }
  .btn-green { background: var(--green); color: #052e16; }
  .btn-red { background: var(--red); color: #fff; }
  .btn-dark { background: var(--card2); color: var(--text); border: 1px solid #334155; }

  .hero-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px; }
  .hero-strip img { width: 100%; height: 82px; object-fit: cover; border-radius: 10px; border: 1px solid #334155; }

  .code-box {
    background: #0f172a;
    border: 2px dashed var(--accent);
    border-radius: 14px;
    padding: 14px;
    text-align: center;
    margin-bottom: 12px;
  }
  .code-big { font-size: 2.2rem; font-weight: 900; letter-spacing: 6px; color: var(--accent); }
  .player-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--card2);
    padding: 10px 12px;
    border-radius: 10px;
    margin-bottom: 8px;
  }
  .badge { background: rgba(245, 158, 11, 0.2); color: var(--accent); padding: 4px 10px; border-radius: 99px; font-size: 0.8rem; font-weight: 800; }
  .timer-box { font-size: 2rem; font-weight: 900; text-align: center; color: var(--accent); margin: 10px 0; }
  .timer-urgent { color: var(--red); animation: pulse 0.5s infinite alternate; }
  @keyframes pulse { from { transform: scale(1); } to { transform: scale(1.08); } }
  .hint-box { background: rgba(59, 130, 246, 0.15); border: 1px solid var(--accent2); padding: 10px; border-radius: 10px; text-align: center; font-weight: 700; color: #93c5fd; margin-bottom: 12px; }
  .hidden { display: none !important; }
  .qb-item { background: #0f172a; border: 1px solid #334155; padding: 10px; border-radius: 10px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
</style>
</head>
<body>

<div id="introOverlay">
  <img id="introImg" src="/media/double_sage_icon.jpg" alt="Double Sage">
  <div id="introCaption">DOUBLE SAGE — MIND DUEL</div>
  <div class="intro-bar-wrap"><div id="introBar"></div></div>
  <div class="intro-actions">
    <button type="button" class="btn-sound-start" onclick="enableSoundFromIntro()">🔊 Enable Loud Sound</button>
    <button type="button" class="btn-skip-intro" onclick="skipIntro()">Skip Intro ⏭</button>
  </div>
</div>

<header>
  <div class="brand">
    <img src="/media/double_sage_icon.jpg" alt="Icon" onerror="this.style.display='none'">
    <span>DOUBLE SAGE</span>
  </div>
  <div class="audio-bar">
    <button type="button" class="pill-btn" onclick="replayIntro()">🎬 Intro</button>
    <button type="button" class="pill-btn" onclick="toggleQbModal()">📚 My QB's</button>
    <button type="button" id="btnMusic" class="pill-btn active" onclick="toggleMusic()">🎵 Music: ON</button>
    <button type="button" id="btnSfx" class="pill-btn active" onclick="toggleSfx()">🔊 SFX: ON</button>
    <input type="range" id="volSlider" min="0" max="100" value="90" oninput="setVolume(this.value)">
  </div>
</header>

<div class="container">

  <div id="qbModal" class="card hidden">
    <h2>📚 My QB's (Saved Question Banks)</h2>
    <p style="font-size:0.85rem;color:var(--muted);margin-bottom:10px;">Save your favorite questions & answers on this phone so you never have to re-type them during a match.</p>
    <input type="text" id="newQbQ" placeholder="New Question...">
    <input type="text" id="newQbA" placeholder="Secret Answer...">
    <button type="button" class="btn btn-green" onclick="addQbItem()">💾 Save to My QB's</button>
    <div id="qbList" style="margin-top:10px;"></div>
    <button type="button" class="btn btn-dark" onclick="toggleQbModal()">Close QB Manager</button>
  </div>

  <div id="homeView">
    <div class="hero-strip">
      <img src="/media/double_sage_battle.jpg" alt="Battle" onerror="this.style.display='none'">
      <img src="/media/double_sage_banner.jpg" alt="Banner" onerror="this.style.display='none'">
      <img src="/media/double_sage_tournament.jpg" alt="Tournament" onerror="this.style.display='none'">
    </div>

    <div class="card">
      <h2>🎮 Create Online Room</h2>
      <label>Your Name</label>
      <input type="text" id="hostName" placeholder="Enter your name">
      <div class="row">
        <div>
          <label>Players (2–10)</label>
          <input type="number" id="maxPlayers" min="2" max="10" value="4">
        </div>
        <div>
          <label>Questions / Player</label>
          <input type="number" id="qPerPlayer" min="1" max="10" value="2">
        </div>
      </div>
      <label>Answer Time Limit (Seconds: 10–60)</label>
      <input type="number" id="timeLimit" min="10" max="60" value="25">
      <label style="display:flex;align-items:center;gap:8px;margin-bottom:14px;color:var(--text);">
        <input type="checkbox" id="umpireMode" style="width:auto;margin:0;">
        <span>⚖️ Play as Umpire (Organizer only — ruling is always final)</span>
      </label>
      <button type="button" class="btn btn-primary" onclick="createRoom()">Create Room & Generate Code</button>
    </div>

    <div class="card">
      <h2>🔑 Join Existing Room</h2>
      <label>Your Name</label>
      <input type="text" id="joinName" placeholder="Enter your name">
      <label>4-Letter Room Code</label>
      <input type="text" id="joinCode" maxlength="4" placeholder="e.g. SAGE" style="text-transform:uppercase;">
      <button type="button" class="btn btn-blue" onclick="joinRoom()">Join Match</button>
    </div>
  </div>

  <div id="gameView" class="hidden">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <span class="badge">ROOM: <strong id="dispCode">----</strong></span>
        <button type="button" class="pill-btn" onclick="copyInvite()">🔗 Copy Invite Link</button>
      </div>
      <div id="phaseContent"></div>
    </div>

    <div class="card">
      <h2>🏆 Live Leaderboard</h2>
      <div id="scoreboardList"></div>
    </div>
  </div>

</div>

<script>
const SLIDES = [
  { src: "/media/double_sage_icon.jpg", text: "DOUBLE SAGE — MIND DUEL" },
  { src: "/media/double_sage_battle.jpg", text: "1v1 PSYCHOLOGICAL CLASH" },
  { src: "/media/double_sage_banner.jpg", text: "OUTSMART YOUR RIVALS" },
  { src: "/media/double_sage_tournament.jpg", text: "MULTIPLAYER & UMPIRE ARENA" }
];
let slideIdx = 0;
let slideElapsed = 0;
window.introTimer = null;

function startIntroSequence() {
  const ov = document.getElementById("introOverlay");
  const img = document.getElementById("introImg");
  const cap = document.getElementById("introCaption");
  const bar = document.getElementById("introBar");
  if (!ov) return;
  slideIdx = 0;
  slideElapsed = 0;
  ov.style.display = "flex";
  img.src = SLIDES[0].src;
  cap.textContent = SLIDES[0].text;
  bar.style.width = "0%";

  if (window.introTimer) clearInterval(window.introTimer);
  window.introTimer = setInterval(() => {
    slideElapsed += 100;
    bar.style.width = Math.min(100, (slideElapsed / 3000) * 100) + "%";
    if (slideElapsed >= 3000) {
      slideElapsed = 0;
      slideIdx++;
      if (slideIdx >= SLIDES.length) {
        window.skipIntro();
      } else {
        img.src = SLIDES[slideIdx].src;
        cap.textContent = SLIDES[slideIdx].text;
        bar.style.width = "0%";
      }
    }
  }, 100);
}

window.skipIntro = function() {
  if (window.introTimer) clearInterval(window.introTimer);
  const ov = document.getElementById("introOverlay");
  if (ov) ov.style.display = "none";
  window.unlockAudio();
};

window.replayIntro = function() {
  window.unlockAudio();
  startIntroSequence();
};

window.enableSoundFromIntro = function() {
  window.unlockAudio();
  playSfx("lock");
};

let audioCtx = null, masterGain = null, audioOut = null, bgmInterval = null;
let musicOn = true, sfxOn = true, masterVol = 0.9;

window.unlockAudio = function() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    audioCtx = new AC();
    const comp = audioCtx.createDynamicsCompressor();
    comp.threshold.value = -10;
    comp.ratio.value = 10;
    masterGain = audioCtx.createGain();
    masterGain.gain.value = masterVol;
    comp.connect(masterGain);
    masterGain.connect(audioCtx.destination);
    audioOut = comp;
  }
  if (audioCtx.state === "suspended") audioCtx.resume();
  if (musicOn && !bgmInterval) startBgm();
};

function startBgm() {
  const melody = [130.81, 164.81, 196.00, 261.63, 196.00, 164.81, 146.83, 220.00];
  let step = 0;
  bgmInterval = setInterval(() => {
    if (!musicOn || !audioCtx || audioCtx.state !== "running") return;
    const osc = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    osc.type = "sawtooth";
    osc.frequency.value = melody[step % melody.length];
    g.gain.setValueAtTime(0.32, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.22);
    osc.connect(g);
    g.connect(audioOut);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.24);
    step++;
  }, 250);
}

function playSfx(type) {
  if (!sfxOn) return;
  window.unlockAudio();
  if (!audioCtx) return;
  const osc = audioCtx.createOscillator();
  const g = audioCtx.createGain();
  osc.connect(g);
  g.connect(audioOut);
  const now = audioCtx.currentTime;
  if (type === "win") {
    osc.type = "triangle";
    osc.frequency.setValueAtTime(523.25, now);
    osc.frequency.setValueAtTime(659.25, now + 0.1);
    osc.frequency.setValueAtTime(783.99, now + 0.2);
    g.gain.setValueAtTime(0.5, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
    osc.start(now); osc.stop(now + 0.46);
  } else if (type === "wrong") {
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(160, now);
    osc.frequency.linearRampToValueAtTime(95, now + 0.35);
    g.gain.setValueAtTime(0.5, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.36);
    osc.start(now); osc.stop(now + 0.38);
  } else {
    osc.type = "sine";
    osc.frequency.setValueAtTime(660, now);
    g.gain.setValueAtTime(0.4, now);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
    osc.start(now); osc.stop(now + 0.16);
  }
}

function toggleMusic() {
  window.unlockAudio();
  musicOn = !musicOn;
  document.getElementById("btnMusic").textContent = musicOn ? "🎵 Music: ON" : "🎵 Music: OFF";
  document.getElementById("btnMusic").classList.toggle("active", musicOn);
}

function toggleSfx() {
  window.unlockAudio();
  sfxOn = !sfxOn;
  document.getElementById("btnSfx").textContent = sfxOn ? "🔊 SFX: ON" : "🔊 SFX: OFF";
  document.getElementById("btnSfx").classList.toggle("active", sfxOn);
}

function setVolume(val) {
  window.unlockAudio();
  masterVol = val / 100;
  if (masterGain) masterGain.gain.value = masterVol;
}

document.addEventListener("pointerdown", window.unlockAudio, { once: true });

function getQbs() {
  try { return JSON.parse(localStorage.getItem("ds_qbs") || "[]"); } catch (e) { return []; }
}
function saveQbs(list) {
  localStorage.setItem("ds_qbs", JSON.stringify(list));
  renderQbList();
}
function toggleQbModal() {
  const m = document.getElementById("qbModal");
  m.classList.toggle("hidden");
  renderQbList();
}
function addQbItem() {
  const q = document.getElementById("newQbQ").value.trim();
  const a = document.getElementById("newQbA").value.trim();
  if (!q || !a) return alert("Enter both question and answer.");
  const list = getQbs();
  list.push({ q, a });
  saveQbs(list);
  document.getElementById("newQbQ").value = "";
  document.getElementById("newQbA").value = "";
  playSfx("lock");
}
function deleteQbItem(idx) {
  const list = getQbs();
  list.splice(idx, 1);
  saveQbs(list);
}
function renderQbList() {
  const box = document.getElementById("qbList");
  const list = getQbs();
  if (!list.length) {
    box.innerHTML = "<p style='color:var(--muted);font-size:0.85rem;'>No saved QB's yet. Add one above!</p>";
    return;
  }
  box.innerHTML = list.map((item, i) => `
    <div class="qb-item">
      <div><strong>${item.q}</strong><br><small style="color:var(--accent);">Ans: ${item.a}</small></div>
      <button type="button" class="pill-btn" onclick="deleteQbItem(${i})">🗑️</button>
    </div>
  `).join("");
}

let myPid = localStorage.getItem("ds_pid") || ("p_" + Math.random().toString(36).slice(2, 10));
localStorage.setItem("ds_pid", myPid);
let currentCode = "";
let pollTimer = null;
let lastRenderedSignature = "";
let cachedPrompts = [];
let usedQbIndices = [];

const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get("room")) {
  document.getElementById("joinCode").value = urlParams.get("room").toUpperCase();
}

async function createRoom() {
  window.unlockAudio();
  const name = document.getElementById("hostName").value.trim() || "Host";
  const res = await fetch("/api/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      pid: myPid,
      max_players: document.getElementById("maxPlayers").value,
      q_per_player: document.getElementById("qPerPlayer").value,
      time_limit: document.getElementById("timeLimit").value,
      umpire_mode: document.getElementById("umpireMode").checked
    })
  });
  const data = await res.json();
  if (data.ok) enterRoom(data.code);
}

async function joinRoom() {
  window.unlockAudio();
  const name = document.getElementById("joinName").value.trim() || "Player";
  const code = document.getElementById("joinCode").value.trim().toUpperCase();
  if (!code) return alert("Enter a 4-letter room code.");
  const res = await fetch("/api/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, code, pid: myPid })
  });
  const data = await res.json();
  if (data.ok) enterRoom(data.code);
  else alert(data.error || "Unable to join.");
}

function enterRoom(code) {
  currentCode = code;
  document.getElementById("homeView").classList.add("hidden");
  document.getElementById("gameView").classList.remove("hidden");
  document.getElementById("dispCode").textContent = code;
  playSfx("lock");
  fetchState();
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(fetchState, 1200);
}

function copyInvite() {
  const link = window.location.origin + "/?room=" + currentCode;
  navigator.clipboard.writeText(link).then(() => alert("Invite link copied: " + link));
}

async function fetchState() {
  if (!currentCode) return;
  const res = await fetch(`/api/state?code=${currentCode}&pid=${myPid}`);
  const st = await res.json();
  if (!st.ok) {
    if (st.kicked) {
      alert("You were removed from the lobby.");
      location.reload();
    }
    return;
  }
  cachedPrompts = st.prompts || [];
  renderLeaderboard(st);
  renderPhase(st);
}

function renderLeaderboard(st) {
  const box = document.getElementById("scoreboardList");
  let html = "";
  if (st.umpire) {
    html += `<div class="player-item"><span>⚖️ <strong>${st.umpire.name}</strong> (Umpire)</span><span class="badge">ORGANIZER</span></div>`;
  }
  html += st.leaderboard.map((p, idx) => `
    <div class="player-item">
      <span>#${idx + 1} <strong>${p.name}</strong></span>
      <span><strong>${p.score} pts</strong> <small style="color:var(--muted);">(${p.time.toFixed(1)}s)</small></span>
    </div>
  `).join("");
  box.innerHTML = html;
}

function renderPhase(st) {
  const container = document.getElementById("phaseContent");

  if (st.phase === "guessing") {
    const tEl = document.getElementById("liveTimer");
    if (tEl) {
      tEl.textContent = st.remaining.toFixed(1) + "s";
      tEl.className = "timer-box" + (st.remaining <= 5 ? " timer-urgent" : "");
    }
  }

  const sig = JSON.stringify({
    phase: st.phase,
    players: st.players.map(p => p.id),
    asker: st.asker_id,
    guesser: st.guesser_id,
    q: st.current_q,
    res: st.last_result
  });
  if (sig === lastRenderedSignature) return;
  lastRenderedSignature = sig;

  if (st.phase === "lobby") {
    const isHost = myPid === st.host_id;
    let listHtml = st.players.map(p => `
      <div class="player-item">
        <span>👤 ${p.name}</span>
        ${isHost && p.id !== myPid ? `<button type="button" class="pill-btn" onclick="kickPlayer('${p.id}')">Kick</button>` : `<span class="badge">READY</span>`}
      </div>
    `).join("");
    container.innerHTML = `
      <div class="code-box">
        <div style="font-size:0.85rem;color:var(--muted);">SHARE THIS ROOM CODE</div>
        <div class="code-big">${st.code}</div>
        <div style="font-size:0.85rem;color:var(--muted);">${st.players.length} / ${st.max_players} Players Joined</div>
      </div>
      ${listHtml}
      ${isHost ? `<button type="button" class="btn btn-green" onclick="startMatch()">🚀 Start Match</button>` : `<p style="text-align:center;color:var(--muted);">Waiting for host to start...</p>`}
    `;
  } else if (st.phase === "asking") {
    if (myPid === st.asker_id) {
      const qbs = getQbs();
      const qbOpts = qbs.map((item, i) => `<option value="qb_${i}">[My QB] ${item.q}</option>`).join("");
      const stOpts = cachedPrompts.map((item, i) => `<option value="st_${i}">[${item.cat}] ${item.q}</option>`).join("");
      container.innerHTML = `
        <h2>✍️ Your Turn to Set Question for ${st.guesser_name}</h2>
        <label>Pick from My QB's or Editable Starter Prompts</label>
        <select id="promptPicker" onchange="applyPickedPrompt(this.value)">
          <option value="">-- Choose a saved QB or starter prompt --</option>
          ${qbOpts}
          ${stOpts}
        </select>
        <div class="row">
          <button type="button" class="btn btn-dark" onclick="loadNextUnusedQb()">⚡ Next Unused QB</button>
          <button type="button" class="btn btn-dark" onclick="saveCurrentToQb()">💾 Save to My QB's</button>
        </div>
        <label>Question</label>
        <input type="text" id="askQ" placeholder="Type or edit question...">
        <label>Secret Answer</label>
        <input type="text" id="askA" placeholder="Type exact secret answer...">
        <button type="button" class="btn btn-primary" onclick="submitQuestion()">Lock Question & Start Timer</button>
      `;
    } else {
      container.innerHTML = `<h2>⏳ Waiting for ${st.asker_name}</h2><p style="color:var(--muted);">${st.asker_name} is preparing a question for <strong>${st.guesser_name}</strong>...</p>`;
    }
  } else if (st.phase === "guessing") {
    if (myPid === st.guesser_id) {
      container.innerHTML = `
        <h2>🎯 Your Turn to Answer!</h2>
        <div id="liveTimer" class="timer-box">${st.remaining.toFixed(1)}s</div>
        <p style="font-size:1.15rem;font-weight:700;margin-bottom:10px;">${st.current_q}</p>
        <div class="hint-box">Manager Hint: ${st.current_hint}</div>
        <input type="text" id="guessInput" placeholder="Type your answer fast..." autofocus>
        <button type="button" class="btn btn-green" onclick="submitGuess()">Submit Answer</button>
      `;
    } else {
      container.innerHTML = `
        <h2>👀 ${st.guesser_name} is Answering...</h2>
        <div id="liveTimer" class="timer-box">${st.remaining.toFixed(1)}s</div>
        <p style="font-size:1.1rem;font-weight:700;margin-bottom:10px;">${st.current_q}</p>
        <div class="hint-box">Manager Hint: ${st.current_hint}</div>
      `;
    }
  } else if (st.phase === "result") {
    const r = st.last_result;
    playSfx(r.correct ? "win" : "wrong");
    let extraHtml = "";
    if (!st.umpire && !r.correct && !r.contested && myPid === r.guesser_id) {
      extraHtml = `
        <div style="margin-top:12px;padding-top:12px;border-top:1px solid #334155;">
          <input type="text" id="contestNote" placeholder="Why is your answer right? (e.g. spelling variation)">
          <button type="button" class="btn btn-red" onclick="raiseContest()">🚩 CONTEST ANSWER (Dispute Result)</button>
        </div>
      `;
    } else if (!st.umpire && r.contested && !r.resolved) {
      if (myPid === st.asker_id) {
        extraHtml = `
          <div style="background:rgba(239,68,68,0.15);border:1px solid var(--red);padding:12px;border-radius:12px;margin-top:12px;">
            <strong>🚩 ${r.guesser_name} Contested!</strong>
            <p style="margin:6px 0;">Reason: "${r.contest_note}"</p>
            <button type="button" class="btn btn-green" onclick="resolveContest('accept')">✅ Accept Guess (+5 Pts to ${r.guesser_name})</button>
            <button type="button" class="btn btn-primary" onclick="resolveContest('new_q')">🔄 Send New Question (0 Pts & Re-Ask)</button>
          </div>
        `;
      } else {
        extraHtml = `<p style="color:var(--accent);margin-top:10px;font-weight:700;">🚩 Contest raised! Waiting for ${r.asker_name} to decide...</p>`;
      }
    } else {
      extraHtml = `<button type="button" class="btn btn-primary" style="margin-top:12px;" onclick="nextTurn()">Next Turn ➡️</button>`;
    }

    container.innerHTML = `
      <h2>${r.correct ? "✅ Correct!" : "❌ Round Result"}</h2>
      <p style="margin-bottom:6px;"><strong>Question:</strong> ${r.question}</p>
      <p style="margin-bottom:6px;"><strong>${r.guesser_name}'s Guess:</strong> ${r.guess}</p>
      <p style="margin-bottom:6px;color:var(--accent);"><strong>Secret Answer:</strong> ${r.answer}</p>
      <p style="color:var(--muted);">${r.reason}</p>
      ${extraHtml}
    `;
  } else if (st.phase === "gameover") {
    const win = st.leaderboard[0];
    playSfx("win");
    container.innerHTML = `
      <h2>🏆 Match Complete!</h2>
      <p style="font-size:1.2rem;margin-bottom:12px;">Champion: <strong style="color:var(--accent);">${win ? win.name : "Winner"}</strong> (${win ? win.score : 0} pts in ${win ? win.time.toFixed(1) : 0}s)</p>
      <button type="button" class="btn btn-primary" onclick="location.href='/'">Play Another Match</button>
    `;
  }
}

function applyPickedPrompt(val) {
  if (!val) return;
  if (val.startsWith("qb_")) {
    const idx = parseInt(val.slice(3), 10);
    const item = getQbs()[idx];
    if (item) {
      document.getElementById("askQ").value = item.q;
      document.getElementById("askA").value = item.a;
    }
  } else if (val.startsWith("st_")) {
    const idx = parseInt(val.slice(3), 10);
    const item = cachedPrompts[idx];
    if (item) {
      document.getElementById("askQ").value = item.q;
      document.getElementById("askA").value = item.a;
    }
  }
}

function loadNextUnusedQb() {
  const qbs = getQbs();
  if (!qbs.length) return alert("No saved QB's yet! Tap '📚 My QB's' in the top bar to add some.");
  let idx = qbs.findIndex((_, i) => !usedQbIndices.includes(i));
  if (idx === -1) {
    usedQbIndices = [];
    idx = 0;
  }
  usedQbIndices.push(idx);
  document.getElementById("askQ").value = qbs[idx].q;
  document.getElementById("askA").value = qbs[idx].a;
  playSfx("lock");
}

function saveCurrentToQb() {
  const q = document.getElementById("askQ").value.trim();
  const a = document.getElementById("askA").value.trim();
  if (!q || !a) return alert("Enter both a question and answer first.");
  const list = getQbs();
  list.push({ q, a });
  saveQbs(list);
  alert("Saved to My QB's!");
}

async function kickPlayer(targetId) {
  await fetch("/api/kick", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: currentCode, pid: myPid, target_id: targetId })
  });
  fetchState();
}

async function startMatch() {
  const res = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: currentCode, pid: myPid })
  });
  const d = await res.json();
  if (!d.ok) alert(d.error);
  fetchState();
}

async function submitQuestion() {
  const q = document.getElementById("askQ").value.trim();
  const a = document.getElementById("askA").value.trim();
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: currentCode, pid: myPid, q, a })
  });
  const d = await res.json();
  if (!d.ok) alert(d.error);
  else playSfx("lock");
  fetchState();
}

async function submitGuess() {
  const guess = document.getElementById("guessInput").value.trim();
  await fetch("/api/guess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: currentCode, pid: myPid, guess })
  });
  fetchState();
}

async function raiseContest() {
  const note = document.getElementById("contestNote").value.trim();
  await fetch("/api/contest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: currentCode, pid: myPid, note })
  });
  fetchState();
}

async function resolveContest(decision) {
  await fetch("/api/resolve_contest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: currentCode, pid: myPid, decision })
  });
  fetchState();
}

async function nextTurn() {
  const res = await fetch("/api/next", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: currentCode, pid: myPid })
  });
  const d = await res.json();
  if (!d.ok && d.error) alert(d.error);
  fetchState();
}

startIntroSequence();
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

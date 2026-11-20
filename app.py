import os
import random
import string
import time
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

ROOMS = {}

PROMPTS = [
    {"cat": "General", "q": "What is the capital city of Australia?", "a": "Canberra"},
    {"cat": "General", "q": "Which planet is known as the Red Planet?", "a": "Mars"},
    {"cat": "Numbers", "q": "How many minutes are in a full day?", "a": "1440"},
    {"cat": "Numbers", "q": "In what year did humans first land on the Moon?", "a": "1969"},
    {"cat": "Sports", "q": "How many players are on a standard soccer team on the pitch?", "a": "11"},
    {"cat": "Science", "q": "What is the chemical symbol for gold?", "a": "Au"},
    {"cat": "Pop Culture", "q": "Who directed the movie Inception?", "a": "Christopher Nolan"}
]

def gen_code():
    while True:
        c = ''.join(random.choices(string.ascii_uppercase, k=4))
        if c not in ROOMS:
            return c

def gen_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

def make_hint(ans):
    words = [w for w in ans.strip().split() if w]
    letters = sum(1 for ch in ans if ch.isalpha())
    digits = sum(1 for ch in ans if ch.isdigit())
    parts = [
        f"{len(words)} {'word' if len(words) == 1 else 'words'}",
        f"{letters} {'letter' if letters == 1 else 'letters'}"
    ]
    if digits > 0:
        parts.append(f"{digits} {'digit' if digits == 1 else 'digits'}")
    return ", ".join(parts)

def build_schedule(room):
    players = [p for p in room["players"] if not p["is_umpire"]]
    qpp = room["q_per_player"]
    sched = []
    if room["umpire_mode"]:
        ump = next((p for p in room["players"] if p["is_umpire"]), None)
        if not ump:
            return sched
        for r in range(qpp):
            for g in players:
                sched.append({"asker": ump["id"], "guesser": g["id"]})
    else:
        n = len(players)
        for r in range(qpp):
            for i in range(n):
                asker = players[i]["id"]
                guesser = players[(i + 1 + (r % max(1, n - 1))) % n]["id"]
                if asker == guesser and n > 1:
                    guesser = players[(i + 1) % n]["id"]
                sched.append({"asker": asker, "guesser": guesser})
    return sched

def public_state(room, pid):
    me = next((p for p in room["players"] if p["id"] == pid), None)
    turn = None
    if room["phase"] != "lobby" and room["turn_idx"] < len(room["schedule"]):
        t = room["schedule"][room["turn_idx"]]
        a_obj = next((p for p in room["players"] if p["id"] == t["asker"]), None)
        g_obj = next((p for p in room["players"] if p["id"] == t["guesser"]), None)
        turn = {
            "asker_id": t["asker"],
            "asker_name": a_obj["name"] if a_obj else "Asker",
            "guesser_id": t["guesser"],
            "guesser_name": g_obj["name"] if g_obj else "Guesser",
            "question": room["current_q"],
            "hint": room["current_hint"],
            "guess": room["current_guess"],
            "correct": room["current_correct"],
            "reason": room["contest_reason"],
            "answer": room["current_a"] if room["phase"] in ("result", "contest") or pid == t["asker"] else None,
            "time_left": max(0, round(room["time_limit"] - (time.time() - room["turn_start"]), 1)) if room["phase"] == "guessing" else room["time_limit"]
        }
    return {
        "code": room["code"],
        "phase": room["phase"],
        "host_id": room["host_id"],
        "umpire_mode": room["umpire_mode"],
        "time_limit": room["time_limit"],
        "q_per_player": room["q_per_player"],
        "players": room["players"],
        "turn_num": room["turn_idx"] + 1,
        "total_turns": len(room["schedule"]),
        "turn": turn,
        "me": me,
        "prompts": PROMPTS
    }

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/create", methods=["POST"])
def create_room():
    data = request.json or {}
    name = (data.get("name") or "Host").strip()[:18]
    umpire = bool(data.get("umpire_mode"))
    qpp = max(1, min(10, int(data.get("q_per_player", 3))))
    tlim = max(10, min(60, int(data.get("time_limit", 30))))
    code = gen_code()
    pid = gen_id()
    ROOMS[code] = {
        "code": code,
        "host_id": pid,
        "umpire_mode": umpire,
        "q_per_player": qpp,
        "time_limit": tlim,
        "phase": "lobby",
        "players": [{"id": pid, "name": name, "score": 0, "time": 0.0, "is_umpire": umpire}],
        "schedule": [],
        "turn_idx": 0,
        "current_q": "",
        "current_a": "",
        "current_hint": "",
        "current_guess": "",
        "current_correct": False,
        "contest_reason": "",
        "turn_start": 0.0
    }
    return jsonify({"ok": True, "code": code, "pid": pid})

@app.route("/api/join", methods=["POST"])
def join_room():
    data = request.json or {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "Player").strip()[:18]
    room = ROOMS.get(code)
    if not room:
        return jsonify({"ok": False, "err": "Room not found."})
    if room["phase"] != "lobby":
        return jsonify({"ok": False, "err": "Game already started."})
    if len(room["players"]) >= 11:
        return jsonify({"ok": False, "err": "Room is full."})
    pid = gen_id()
    room["players"].append({"id": pid, "name": name, "score": 0, "time": 0.0, "is_umpire": False})
    return jsonify({"ok": True, "code": code, "pid": pid})

@app.route("/api/state")
def get_state():
    code = (request.args.get("code") or "").upper()
    pid = request.args.get("pid") or ""
    room = ROOMS.get(code)
    if not room:
        return jsonify({"ok": False, "err": "Room expired."})
    if room["phase"] == "guessing":
        elapsed = time.time() - room["turn_start"]
        if elapsed >= room["time_limit"]:
            finalize_guess(room, "", room["time_limit"])
    return jsonify({"ok": True, "state": public_state(room, pid)})

@app.route("/api/kick", methods=["POST"])
def kick_player():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or data.get("pid") != room["host_id"] or room["phase"] != "lobby":
        return jsonify({"ok": False})
    target = data.get("target_id")
    if target != room["host_id"]:
        room["players"] = [p for p in room["players"] if p["id"] != target]
    return jsonify({"ok": True})

@app.route("/api/start", methods=["POST"])
def start_game():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or data.get("pid") != room["host_id"]:
        return jsonify({"ok": False})
    active = [p for p in room["players"] if not p["is_umpire"]]
    min_needed = 1 if room["umpire_mode"] else 2
    if len(active) < min_needed:
        return jsonify({"ok": False, "err": f"Need at least {min_needed} competing player(s)."})
    room["schedule"] = build_schedule(room)
    room["turn_idx"] = 0
    room["phase"] = "asking"
    return jsonify({"ok": True})

@app.route("/api/ask", methods=["POST"])
def submit_question():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "asking":
        return jsonify({"ok": False})
    t = room["schedule"][room["turn_idx"]]
    if data.get("pid") != t["asker"]:
        return jsonify({"ok": False})
    q = (data.get("question") or "").strip()
    a = (data.get("answer") or "").strip()
    if not q or not a:
        return jsonify({"ok": False, "err": "Enter both question and answer."})
    room["current_q"] = q
    room["current_a"] = a
    room["current_hint"] = make_hint(a)
    room["current_guess"] = ""
    room["contest_reason"] = ""
    room["turn_start"] = time.time()
    room["phase"] = "guessing"
    return jsonify({"ok": True})

def finalize_guess(room, guess, spent):
    t = room["schedule"][room["turn_idx"]]
    asker = next(p for p in room["players"] if p["id"] == t["asker"])
    guesser = next(p for p in room["players"] if p["id"] == t["guesser"])
    clean_g = "".join(c.lower() for c in guess if c.isalnum())
    clean_a = "".join(c.lower() for c in room["current_a"] if c.isalnum())
    is_right = bool(clean_g) and (clean_g == clean_a)
    room["current_guess"] = guess if guess else "(Time Expired)"
    room["current_correct"] = is_right
    room["last_spent"] = round(min(room["time_limit"], max(0.1, spent)), 2)
    guesser["time"] = round(guesser["time"] + room["last_spent"], 2)
    if is_right:
        guesser["score"] += 5
    else:
        if not asker["is_umpire"]:
            asker["score"] += 5
    room["phase"] = "result"

@app.route("/api/guess", methods=["POST"])
def submit_guess():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "guessing":
        return jsonify({"ok": False})
    t = room["schedule"][room["turn_idx"]]
    if data.get("pid") != t["guesser"]:
        return jsonify({"ok": False})
    spent = time.time() - room["turn_start"]
    finalize_guess(room, (data.get("guess") or "").strip(), spent)
    return jsonify({"ok": True})

@app.route("/api/contest", methods=["POST"])
def raise_contest():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "result" or room["umpire_mode"] or room["current_correct"]:
        return jsonify({"ok": False})
    t = room["schedule"][room["turn_idx"]]
    if data.get("pid") != t["guesser"]:
        return jsonify({"ok": False})
    room["contest_reason"] = (data.get("reason") or "Answer should count as valid.").strip()[:120]
    room["phase"] = "contest"
    return jsonify({"ok": True})

@app.route("/api/resolve_contest", methods=["POST"])
def resolve_contest():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "contest":
        return jsonify({"ok": False})
    t = room["schedule"][room["turn_idx"]]
    if data.get("pid") != t["asker"]:
        return jsonify({"ok": False})
    decision = data.get("decision")
    asker = next(p for p in room["players"] if p["id"] == t["asker"])
    guesser = next(p for p in room["players"] if p["id"] == t["guesser"])
    if decision == "accept":
        asker["score"] = max(0, asker["score"] - 5)
        guesser["score"] += 5
        room["current_correct"] = True
        room["phase"] = "result"
    elif decision == "reask":
        asker["score"] = max(0, asker["score"] - 5)
        guesser["time"] = round(max(0.0, guesser["time"] - room.get("last_spent", 0)), 2)
        room["current_q"] = ""
        room["current_a"] = ""
        room["current_hint"] = ""
        room["current_guess"] = ""
        room["contest_reason"] = ""
        room["phase"] = "asking"
    return jsonify({"ok": True})

@app.route("/api/next", methods=["POST"])
def next_turn():
    data = request.json or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or room["phase"] != "result":
        return jsonify({"ok": False})
    t = room["schedule"][room["turn_idx"]]
    if data.get("pid") not in (t["asker"], room["host_id"]):
        return jsonify({"ok": False})
    room["turn_idx"] += 1
    if room["turn_idx"] >= len(room["schedule"]):
        room["phase"] = "gameover"
    else:
        room["current_q"] = ""
        room["current_a"] = ""
        room["current_hint"] = ""
        room["current_guess"] = ""
        room["contest_reason"] = ""
        room["phase"] = "asking"
    return jsonify({"ok": True})

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Double Sage — Online Multiplayer</title>
<style>
  :root{--bg:#0b1120;--card:#151f32;--gold:#f5b041;--teal:#2dd4bf;--red:#f87171;--text:#f8fafc;--muted:#94a3b8}
  *{box-sizing:border-box;font-family:system-ui,-apple-system,sans-serif}
  body{margin:0;background:var(--bg);color:var(--text);display:flex;justify-content:center;padding:16px}
  .wrap{width:100%;max-width:480px}
  .card{background:var(--card);border:1px solid #26334d;border-radius:16px;padding:20px;margin-bottom:14px}
  h1{margin:0 0 6px;color:var(--gold);font-size:26px;text-align:center}
  .sub{text-align:center;color:var(--teal);font-size:13px;margin-bottom:18px}
  label{display:block;font-size:13px;color:var(--muted);margin:10px 0 4px}
  input,select,textarea{width:100%;padding:11px;border-radius:10px;border:1px solid #334155;background:#0f172a;color:#fff;font-size:15px}
  button{width:100%;padding:13px;border:none;border-radius:10px;font-weight:700;font-size:15px;cursor:pointer;margin-top:12px}
  .btn-gold{background:var(--gold);color:#0b1120}
  .btn-teal{background:var(--teal);color:#0b1120}
  .btn-red{background:var(--red);color:#0b1120}
  .btn-sm{padding:6px 10px;font-size:12px;width:auto;margin:0}
  .row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #243047}
  .badge{background:#1e293b;color:var(--gold);padding:4px 10px;border-radius:99px;font-weight:700;font-size:13px}
  .hint{background:#0f172a;border:1px dashed var(--teal);color:var(--teal);padding:10px;border-radius:10px;text-align:center;font-weight:700;margin:10px 0}
  .timer{font-size:24px;font-weight:800;text-align:center;color:var(--gold)}
  .hidden{display:none}
</style>
</head>
<body>
<div class="wrap">
  <h1>DOUBLE SAGE</h1>
  <div class="sub">OUTSMART • OUTGUESS • OUTSCORE</div>

  <div id="homeView" class="card">
    <label>Your Name</label>
    <input id="pName" placeholder="Enter your name">
    <label>Join Existing Room Code</label>
    <input id="joinCode" placeholder="4-Letter Code (e.g. SAGE)" maxlength="4" style="text-transform:uppercase">
    <button class="btn-teal" onclick="joinRoom()">Join Room</button>
    <hr style="border-color:#26334d;margin:18px 0">
    <label>Or Host a New Room — Questions Per Player</label>
    <select id="qpp"><option value="2">2 Questions</option><option value="3" selected>3 Questions</option><option value="5">5 Questions</option></select>
    <label>Time Limit Per Turn</label>
    <select id="tlim"><option value="15">15 Seconds</option><option value="30" selected>30 Seconds</option><option value="45">45 Seconds</option><option value="60">60 Seconds</option></select>
    <label><input type="checkbox" id="umpMode" style="width:auto;margin-right:8px">Play as Umpire (Organizer sets all questions, ruling is final)</label>
    <button class="btn-gold" onclick="createRoom()">Create Room</button>
  </div>

  <div id="gameView" class="hidden"></div>
</div>

<script>
let CODE = "", PID = "", pollTimer = null;
const urlCode = new URLSearchParams(location.search).get("room");
if (urlCode) document.getElementById("joinCode").value = urlCode.toUpperCase();

async function api(path, body) {
  const res = await fetch(path, body ? {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)} : {});
  return res.json();
}

async function createRoom() {
  const name = document.getElementById("pName").value.trim() || "Host";
  const r = await api("/api/create", {
    name,
    q_per_player: document.getElementById("qpp").value,
    time_limit: document.getElementById("tlim").value,
    umpire_mode: document.getElementById("umpMode").checked
  });
  if (r.ok) { CODE = r.code; PID = r.pid; startPolling(); }
}

async function joinRoom() {
  const name = document.getElementById("pName").value.trim() || "Player";
  const code = document.getElementById("joinCode").value.trim().toUpperCase();
  const r = await api("/api/join", {name, code});
  if (!r.ok) return alert(r.err);
  CODE = r.code; PID = r.pid; startPolling();
}

function startPolling() {
  document.getElementById("homeView").classList.add("hidden");
  document.getElementById("gameView").classList.remove("hidden");
  fetchState();
  pollTimer = setInterval(fetchState, 1200);
}

function copyInvite() {
  const link = `${location.origin}/?room=${CODE}`;
  navigator.clipboard.writeText(link);
  alert("Invite link copied: " + link);
}

function loadPrompt(idx, prompts) {
  document.getElementById("qBox").value = prompts[idx].q;
  document.getElementById("aBox").value = prompts[idx].a;
}

async function fetchState() {
  const r = await api(`/api/state?code=${CODE}&pid=${PID}`);
  if (!r.ok) return;
  const s = r.state;
  const gv = document.getElementById("gameView");
  const isHost = s.host_id === PID;

  if (s.phase === "lobby") {
    let list = s.players.map(p => `
      <div class="row">
        <span>${p.name} ${p.is_umpire ? '<span class="badge">UMPIRE</span>' : ''}</span>
        ${isHost && p.id !== PID ? `<button class="btn-red btn-sm" onclick="api('/api/kick',{code:CODE,pid:PID,target_id:'${p.id}'})">Kick</button>` : ''}
      </div>`).join("");
    gv.innerHTML = `
      <div class="card">
        <div style="text-align:center">Room Code: <span class="badge" style="font-size:20px">${s.code}</span></div>
        <button class="btn-teal" onclick="copyInvite()">Copy One-Tap Invite Link</button>
        <p style="color:var(--muted);font-size:13px">${s.umpire_mode ? 'Umpire Mode Active (Umpire ruling is final)' : 'Standard Mode (Contest & Approval enabled)'} • ${s.q_per_player} Qs • ${s.time_limit}s</p>
        ${list}
        ${isHost ? `<button class="btn-gold" onclick="startMatch()">Start Match</button>` : `<p style="text-align:center;color:var(--muted)">Waiting for host to start...</p>`}
      </div>`;
    return;
  }

  if (s.phase === "gameover") {
    const ranked = s.players.filter(p => !p.is_umpire).sort((a,b) => b.score - a.score || a.time - b.time);
    gv.innerHTML = `
      <div class="card">
        <h2 style="text-align:center;color:var(--gold)">FINAL STANDINGS</h2>
        ${ranked.map((p,i) => `<div class="row"><span>#${i+1} ${p.name}</span><span><b>${p.score} pts</b> (${p.time}s)</span></div>`).join("")}
        <button class="btn-gold" onclick="location.href='/'">Play Again</button>
      </div>`;
    return;
  }

  const t = s.turn;
  const activeEl = document.activeElement ? document.activeElement.id : "";
  if (["qBox","aBox","gBox","rBox"].includes(activeEl)) return;

  if (s.phase === "asking") {
    if (PID === t.asker_id) {
      let opts = s.prompts.map((pr, i) => `<option value="${i}">[${pr.cat}] ${pr.q}</option>`).join("");
      gv.innerHTML = `
        <div class="card">
          <div class="badge">Turn ${s.turn_num}/${s.total_turns} • Target: ${t.guesser_name}</div>
          <label>Quick Starter Prompts (Editable)</label>
          <select onchange="loadPrompt(this.value, ${JSON.stringify(s.prompts).replace(/"/g,'&quot;')})"><option value="">-- Pick a starter prompt --</option>${opts}</select>
          <label>Question</label>
          <textarea id="qBox" rows="2" placeholder="Type your question..."></textarea>
          <label>Secret Answer</label>
          <input id="aBox" placeholder="Type the exact secret answer...">
          <button class="btn-gold" onclick="sendQ()">Lock In Question</button>
        </div>`;
    } else {
      gv.innerHTML = `<div class="card" style="text-align:center"><h3>Turn ${s.turn_num}/${s.total_turns}</h3><p><b>${t.asker_name}</b> is crafting a question for <b>${t.guesser_name}</b>...</p></div>`;
    }
    return;
  }

  if (s.phase === "guessing") {
    if (PID === t.guesser_id) {
      gv.innerHTML = `
        <div class="card">
          <div class="timer">${t.time_left}s</div>
          <p style="font-size:18px;font-weight:700">${t.question}</p>
          <div class="hint">MANAGER HINT: ${t.hint}</div>
          <input id="gBox" placeholder="Type your answer fast...">
          <button class="btn-teal" onclick="sendGuess()">Submit Answer</button>
        </div>`;
    } else {
      gv.innerHTML = `<div class="card" style="text-align:center"><div class="timer">${t.time_left}s</div><p><b>${t.guesser_name}</b> is answering:</p><p>"${t.question}"</p><div class="hint">${t.hint}</div></div>`;
    }
    return;
  }

  if (s.phase === "result") {
    const canContest = !s.umpire_mode && !t.correct && PID === t.guesser_id;
    const canNext = PID === t.asker_id || isHost;
    gv.innerHTML = `
      <div class="card">
        <h3 style="text-align:center;color:${t.correct ? 'var(--teal)' : 'var(--red)'}">${t.correct ? 'CORRECT! +5 PTS to ' + t.guesser_name : 'WRONG! ' + (s.umpire_mode ? '0 Pts' : '+5 Pts to ' + t.asker_name)}</h3>
        <p><b>Question:</b> ${t.question}</p>
        <p><b>${t.guesser_name} guessed:</b> ${t.guess}</p>
        <p><b>Secret Answer:</b> ${t.answer}</p>
        ${canContest ? `<input id="rBox" placeholder="Why should this count?"><button class="btn-red" onclick="contestAns()">CONTEST ANSWER (Dispute Result)</button>` : ''}
        ${canNext ? `<button class="btn-gold" onclick="api('/api/next',{code:CODE,pid:PID})">Next Turn</button>` : `<p style="text-align:center;color:var(--muted)">Waiting for next turn...</p>`}
      </div>`;
    return;
  }

  if (s.phase === "contest") {
    if (PID === t.asker_id) {
      gv.innerHTML = `
        <div class="card">
          <h3 style="color:var(--gold)">ANSWER CONTESTED!</h3>
          <p><b>${t.guesser_name}</b> disputed the call: <i>"${t.reason}"</i></p>
          <p><b>Their Guess:</b> ${t.guess} | <b>Your Answer:</b> ${t.answer}</p>
          <button class="btn-teal" onclick="resolveContest('accept')">Accept Guess (+5 Pts to ${t.guesser_name})</button>
          <button class="btn-red" onclick="resolveContest('reask')">Send New Question (0 Pts & Re-Ask)</button>
        </div>`;
    } else {
      gv.innerHTML = `<div class="card" style="text-align:center"><h3 style="color:var(--gold)">CONTEST UNDER REVIEW</h3><p><b>${t.guesser_name}</b> contested the result. Waiting for <b>${t.asker_name}</b> to accept the guess or send a new question...</p></div>`;
    }
  }
}

async function startMatch() {
  const r = await api("/api/start", {code: CODE, pid: PID});
  if (!r.ok && r.err) alert(r.err);
}
async function sendQ() {
  const r = await api("/api/ask", {code: CODE, pid: PID, question: document.getElementById("qBox").value, answer: document.getElementById("aBox").value});
  if (!r.ok && r.err) alert(r.err);
}
async function sendGuess() {
  await api("/api/guess", {code: CODE, pid: PID, guess: document.getElementById("gBox").value});
}
async function contestAns() {
  await api("/api/contest", {code: CODE, pid: PID, reason: document.getElementById("rBox").value});
}
async function resolveContest(decision) {
  await api("/api/resolve_contest", {code: CODE, pid: PID, decision});
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

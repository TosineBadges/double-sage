import os
import re
import time
import random
import string
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".", static_url_path="")

ROOMS = {}
MAX_ROOMS = 250
ROOM_TTL_SECONDS = 7200  # 2 hours Render free-tier memory guard


def cleanup_rooms():
    now = time.time()
    expired = [
        code for code, r in list(ROOMS.items())
        if now - r.get("updated_at", r.get("created_at", now)) > ROOM_TTL_SECONDS
    ]
    for code in expired:
        ROOMS.pop(code, None)
    if len(ROOMS) > MAX_ROOMS:
        oldest = sorted(ROOMS.items(), key=lambda kv: kv[1].get("updated_at", 0))
        for code, _ in oldest[: len(ROOMS) - MAX_ROOMS]:
            ROOMS.pop(code, None)


def generate_room_code():
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    for _ in range(100):
        code = "".join(random.choices(chars, k=4))
        if code not in ROOMS:
            return code
    return "".join(random.choices(chars, k=5))


def build_hint(answer):
    ans = (answer or "").strip()
    if not ans:
        return "0 words"
    words = [w for w in ans.split() if w]
    letters = len(re.findall(r"[A-Za-z]", ans))
    digits = len(re.findall(r"[0-9]", ans))
    parts = []
    if letters > 0:
        parts.append(f"{len(words)} {'word' if len(words) == 1 else 'words'}")
        parts.append(f"{letters} {'letter' if letters == 1 else 'letters'}")
    if digits > 0:
        parts.append(f"{digits} {'digit' if digits == 1 else 'digits'}")
    return ", ".join(parts) if parts else f"{len(words)} words"


def normalize_answer(text):
    t = (text or "").strip().lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def serialize_room(room, viewer_id=""):
    players_out = []
    for p in room["players"]:
        players_out.append({
            "id": p["id"],
            "name": p["name"],
            "score": p["score"],
            "total_time": round(p.get("total_time", 0.0), 2),
            "is_host": p["id"] == room["host_id"],
        })

    rnd = room.get("current_round") or {}
    public_round = None
    if rnd:
        is_umpire = room["mode"] == "umpire"
        is_host = viewer_id == room["host_id"]
        is_setter = viewer_id == rnd.get("setter_id")
        reveal_answer = rnd.get("phase") == "result" or is_setter or (is_umpire and is_host)
        public_round = {
            "round_num": rnd.get("round_num", 1),
            "setter_id": rnd.get("setter_id"),
            "setter_name": rnd.get("setter_name"),
            "guesser_id": rnd.get("guesser_id"),
            "guesser_name": rnd.get("guesser_name"),
            "question": rnd.get("question", ""),
            "hint": rnd.get("hint", ""),
            "answer": rnd.get("answer", "") if reveal_answer else "",
            "phase": rnd.get("phase", "ask"),
            "started_at": rnd.get("started_at", 0),
            "time_limit": room.get("time_limit", 30),
            "submissions": rnd.get("submissions", {}),
            "contested": rnd.get("contested", False),
            "winner_note": rnd.get("winner_note", ""),
        }

    return {
        "code": room["code"],
        "mode": room["mode"],
        "rounds": room["rounds"],
        "time_limit": room["time_limit"],
        "host_id": room["host_id"],
        "status": room["status"],
        "round_index": room["round_index"],
        "players": players_out,
        "current_round": public_round,
    }


def setup_next_round(room):
    room["round_index"] += 1
    if room["round_index"] > room["rounds"]:
        room["status"] = "finished"
        room["current_round"] = None
        return

    if room["mode"] == "umpire":
        host = next((p for p in room["players"] if p["id"] == room["host_id"]), room["players"][0])
        room["current_round"] = {
            "round_num": room["round_index"],
            "setter_id": host["id"],
            "setter_name": host["name"] + " (Umpire)",
            "guesser_id": "ALL",
            "guesser_name": "All Players",
            "question": "",
            "answer": "",
            "hint": "",
            "phase": "ask",
            "started_at": 0,
            "submissions": {},
            "contested": False,
            "winner_note": "",
        }
    else:
        n = len(room["players"])
        s_idx = (room["round_index"] - 1) % n
        g_idx = (s_idx + 1) % n
        setter = room["players"][s_idx]
        guesser = room["players"][g_idx]
        room["current_round"] = {
            "round_num": room["round_index"],
            "setter_id": setter["id"],
            "setter_name": setter["name"],
            "guesser_id": guesser["id"],
            "guesser_name": guesser["name"],
            "question": "",
            "answer": "",
            "hint": "",
            "phase": "ask",
            "started_at": 0,
            "submissions": {},
            "contested": False,
            "winner_note": "",
        }


@app.route("/")
def serve_home():
    return send_from_directory(".", "index.html")


@app.route("/health")
def health():
    cleanup_rooms()
    return jsonify({"status": "COMPILED_OK", "active_rooms": len(ROOMS)})


@app.route("/api/create", methods=["POST"])
def api_create():
    cleanup_rooms()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "Host").strip()[:24] or "Host"
    mode = data.get("mode") if data.get("mode") in ("standard", "umpire") else "standard"
    rounds = max(1, min(30, int(data.get("rounds") or 5)))
    time_limit = max(10, min(120, int(data.get("time_limit") or 30)))

    code = generate_room_code()
    player_id = "p_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    now = time.time()
    ROOMS[code] = {
        "code": code,
        "mode": mode,
        "rounds": rounds,
        "time_limit": time_limit,
        "host_id": player_id,
        "status": "lobby",
        "round_index": 0,
        "created_at": now,
        "updated_at": now,
        "players": [{"id": player_id, "name": name, "score": 0, "total_time": 0.0}],
        "current_round": None,
    }
    return jsonify({"ok": True, "player_id": player_id, "room": serialize_room(ROOMS[code], player_id)})


@app.route("/api/join", methods=["POST"])
def api_join():
    cleanup_rooms()
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "Player").strip()[:24] or "Player"
    room = ROOMS.get(code)
    if not room:
        return jsonify({"ok": False, "error": "Room not found."}), 404
    max_cap = 11 if room["mode"] == "umpire" else 10
    if len(room["players"]) >= max_cap:
        return jsonify({"ok": False, "error": "Room is full."}), 400

    player_id = "p_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    room["players"].append({"id": player_id, "name": name, "score": 0, "total_time": 0.0})
    room["updated_at"] = time.time()
    return jsonify({"ok": True, "player_id": player_id, "room": serialize_room(room, player_id)})


@app.route("/api/state/<code>")
def api_state(code):
    room = ROOMS.get((code or "").strip().upper())
    if not room:
        return jsonify({"ok": False, "error": "Room expired or not found."}), 404
    viewer_id = request.args.get("pid", "")
    return jsonify({"ok": True, "room": serialize_room(room, viewer_id)})


@app.route("/api/kick", methods=["POST"])
def api_kick():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or data.get("player_id") != room["host_id"]:
        return jsonify({"ok": False, "error": "Unauthorized."}), 403
    target_id = data.get("target_id")
    if target_id and target_id != room["host_id"]:
        room["players"] = [p for p in room["players"] if p["id"] != target_id]
        room["updated_at"] = time.time()
    return jsonify({"ok": True, "room": serialize_room(room, data.get("player_id", ""))})


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or data.get("player_id") != room["host_id"]:
        return jsonify({"ok": False, "error": "Only host can start."}), 403
    if len(room["players"]) < 2:
        return jsonify({"ok": False, "error": "Need at least 2 people in the room."}), 400
    for p in room["players"]:
        p["score"] = 0
        p["total_time"] = 0.0
    room["status"] = "playing"
    room["round_index"] = 0
    setup_next_round(room)
    room["updated_at"] = time.time()
    return jsonify({"ok": True, "room": serialize_room(room, data.get("player_id", ""))})


@app.route("/api/ask", methods=["POST"])
def api_ask():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or not room.get("current_round"):
        return jsonify({"ok": False, "error": "No active round."}), 400
    rnd = room["current_round"]
    if data.get("player_id") != rnd["setter_id"]:
        return jsonify({"ok": False, "error": "Not your turn to ask."}), 403
    q = (data.get("question") or "").strip()
    a = (data.get("answer") or "").strip()
    if not q or not a:
        return jsonify({"ok": False, "error": "Question and answer required."}), 400
    rnd["question"] = q
    rnd["answer"] = a
    rnd["hint"] = build_hint(a)
    rnd["phase"] = "guess"
    rnd["started_at"] = time.time()
    rnd["submissions"] = {}
    rnd["contested"] = False
    rnd["winner_note"] = ""
    room["updated_at"] = time.time()
    return jsonify({"ok": True, "room": serialize_room(room, data.get("player_id", ""))})


@app.route("/api/guess", methods=["POST"])
def api_guess():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or not room.get("current_round"):
        return jsonify({"ok": False, "error": "No active round."}), 400
    rnd = room["current_round"]
    pid = data.get("player_id")
    if rnd["phase"] != "guess":
        return jsonify({"ok": False, "error": "Round not accepting guesses."}), 400

    elapsed = round(max(0.1, time.time() - rnd.get("started_at", time.time())), 2)
    guess_text = (data.get("guess") or "").strip()
    is_correct = normalize_answer(guess_text) == normalize_answer(rnd["answer"])

    if room["mode"] == "umpire":
        if pid == room["host_id"]:
            return jsonify({"ok": False, "error": "Umpire organizes and does not answer."}), 403
        player = next((p for p in room["players"] if p["id"] == pid), None)
        if not player or pid in rnd["submissions"]:
            return jsonify({"ok": False, "error": "Already submitted."}), 400
        pts = 5 if is_correct else 0
        if is_correct:
            player["score"] += 5
            player["total_time"] = round(player.get("total_time", 0.0) + elapsed, 2)
        rnd["submissions"][pid] = {
            "name": player["name"],
            "guess": guess_text,
            "correct": is_correct,
            "time": elapsed,
            "points": pts,
        }
        competitors = [p for p in room["players"] if p["id"] != room["host_id"]]
        if len(rnd["submissions"]) >= len(competitors):
            rnd["phase"] = "result"
            winners = [s["name"] for s in rnd["submissions"].values() if s["correct"]]
            rnd["winner_note"] = (
                f"Winners (+5 pts): {', '.join(winners)}" if winners else "No one got it right — 0 points awarded."
            )
    else:
        if pid != rnd["guesser_id"]:
            return jsonify({"ok": False, "error": "Not your turn to guess."}), 403
        guesser = next((p for p in room["players"] if p["id"] == pid), None)
        setter = next((p for p in room["players"] if p["id"] == rnd["setter_id"]), None)
        if is_correct and guesser:
            guesser["score"] += 5
            guesser["total_time"] = round(guesser.get("total_time", 0.0) + elapsed, 2)
            rnd["winner_note"] = f"{guesser['name']} answered correctly in {elapsed}s (+5 pts)!"
        elif setter:
            setter["score"] += 5
            rnd["winner_note"] = f"Missed! {setter['name']} earns +5 pts."
        rnd["submissions"][pid] = {
            "name": guesser["name"] if guesser else "Guesser",
            "guess": guess_text,
            "correct": is_correct,
            "time": elapsed,
            "points": 5 if is_correct else 0,
        }
        rnd["phase"] = "result"

    room["updated_at"] = time.time()
    return jsonify({"ok": True, "room": serialize_room(room, pid)})


@app.route("/api/contest", methods=["POST"])
def api_contest():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or not room.get("current_round") or room["mode"] != "standard":
        return jsonify({"ok": False, "error": "Contest unavailable."}), 400
    rnd = room["current_round"]
    if data.get("player_id") != rnd["guesser_id"]:
        return jsonify({"ok": False, "error": "Only guesser can contest."}), 403
    rnd["contested"] = True
    rnd["phase"] = "contest"
    room["updated_at"] = time.time()
    return jsonify({"ok": True, "room": serialize_room(room, data.get("player_id", ""))})


@app.route("/api/resolve_contest", methods=["POST"])
def api_resolve_contest():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or not room.get("current_round"):
        return jsonify({"ok": False, "error": "No active round."}), 400
    rnd = room["current_round"]
    if data.get("player_id") != rnd["setter_id"]:
        return jsonify({"ok": False, "error": "Only setter can rule on contest."}), 403
    accept = bool(data.get("accept"))
    guesser = next((p for p in room["players"] if p["id"] == rnd["guesser_id"]), None)
    setter = next((p for p in room["players"] if p["id"] == rnd["setter_id"]), None)
    sub = rnd["submissions"].get(rnd["guesser_id"], {})
    was_correct = bool(sub.get("correct"))

    if accept and not was_correct and guesser and setter:
        setter["score"] = max(0, setter["score"] - 5)
        guesser["score"] += 5
        guesser["total_time"] = round(guesser.get("total_time", 0.0) + sub.get("time", 5.0), 2)
        sub["correct"] = True
        sub["points"] = 5
        rnd["winner_note"] = f"Contest accepted! {guesser['name']} gets +5 pts."
    else:
        rnd["winner_note"] = f"Contest rejected! {setter['name'] if setter else 'Setter'} keeps +5 pts."

    rnd["contested"] = False
    rnd["phase"] = "result"
    room["updated_at"] = time.time()
    return jsonify({"ok": True, "room": serialize_room(room, data.get("player_id", ""))})


@app.route("/api/next", methods=["POST"])
def api_next():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get((data.get("code") or "").upper())
    if not room or not room.get("current_round"):
        return jsonify({"ok": False, "error": "No active round."}), 400
    rnd = room["current_round"]
    pid = data.get("player_id")
    if pid not in (room["host_id"], rnd["setter_id"]):
        return jsonify({"ok": False, "error": "Only host or setter can advance."}), 403
    setup_next_round(room)
    room["updated_at"] = time.time()
    return jsonify({"ok": True, "room": serialize_room(room, pid)})


@app.route("/<path:filename>")
def serve_media(filename):
    if filename.endswith((".jpg", ".jpeg", ".png", ".webp", ".mp3", ".m4a", ".ogg", ".wav", ".css", ".js")):
        return send_from_directory(".", filename)
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

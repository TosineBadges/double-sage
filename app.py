import os
import re
import time
import random
import string
from flask import Flask, request, jsonify, send_from_directory, render_template_string

app = Flask(__name__, static_folder='.', static_url_path='')

ROOMS = {}
ROOM_TTL = 7200  # 2-hour Render Free-Tier memory guard
MAX_ROOMS = 250


def cleanup_rooms():
    now = time.time()
    expired = [k for k, v in ROOMS.items() if now - v.get('updated_at', now) > ROOM_TTL]
    for k in expired:
        ROOMS.pop(k, None)
    if len(ROOMS) > MAX_ROOMS:
        oldest = sorted(ROOMS.items(), key=lambda x: x.get('updated_at', 0))
        for k, _ in oldest[:len(ROOMS) - MAX_ROOMS]:
            ROOMS.pop(k, None)


def make_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase, k=4))
        if code not in ROOMS:
            return code


def normalize(text):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', str(text or '').strip().lower())).strip()


def build_hint(answer):
    raw = str(answer or '').strip()
    if not raw:
        return ''
    words = [w for w in raw.split() if w]
    word_count = len(words)
    letters = sum(1 for ch in raw if ch.isalpha())
    digits = sum(1 for ch in raw if ch.isdigit())

    parts = []
    if letters > 0:
        parts.append(f"{word_count} {'word' if word_count == 1 else 'words'}")
        parts.append(f"{letters} {'letter' if letters == 1 else 'letters'}")
    if digits > 0:
        parts.append(f"{digits} {'digit' if digits == 1 else 'digits'}")
    return ', '.join(parts) if parts else f"{word_count} {'word' if word_count == 1 else 'words'}"


def find_asset_file(filename):
    if not filename or filename.endswith('.py'):
        return None
    base_name = os.path.basename(filename)
    stem, ext = os.path.splitext(base_name)
    alt_exts = [ext] if ext else []
    if ext.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
        alt_exts = ['.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG']

    search_dirs = ['.', 'static', 'media', 'images', 'assets', 'public']
    for folder in search_dirs:
        if not os.path.isdir(folder):
            continue
        try:
            entries = os.listdir(folder)
        except Exception:
            continue
        lower_map = {e.lower(): e for e in entries}
        if base_name.lower() in lower_map:
            return folder, lower_map[base_name.lower()]
        for e_ext in alt_exts:
            cand = (stem + e_ext).lower()
            if cand in lower_map:
                return folder, lower_map[cand]
    return None


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/<path:filename>')
def serve_files(filename):
    if filename.endswith('.py'):
        return jsonify({'error': 'Forbidden'}), 403
    found = find_asset_file(filename)
    if found:
        return send_from_directory(found[0], found[1])
    return jsonify({'error': 'Not found'}), 404


@app.route('/media/<path:filename>')
def serve_media(filename):
    found = find_asset_file(filename)
    if found:
        return send_from_directory(found[0], found[1])
    return jsonify({'error': 'Media not found'}), 404


@app.route('/health')
def health():
    cleanup_rooms()
    return jsonify({'status': 'ok', 'rooms': len(ROOMS)})


@app.route('/api/create', methods=['POST'])
def create_room():
    cleanup_rooms()
    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or 'Host').strip()[:24]
    mode = data.get('mode', 'standard')
    rounds = max(1, min(30, int(data.get('rounds', 5))))
    timer = max(10, min(120, int(data.get('timer', 30))))

    code = make_code()
    pid = 'p_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    ROOMS[code] = {
        'code': code,
        'host_id': pid,
        'mode': mode,
        'total_rounds': rounds,
        'current_round': 1,
        'timer': timer,
        'phase': 'lobby',
        'players': [{
            'id': pid,
            'name': name,
            'score': 0,
            'total_time': 0.0,
            'is_umpire': (mode == 'umpire')
        }],
        'setter_idx': 0,
        'question': '',
        'answer': '',
        'hint': '',
        'question_sent_at': 0,
        'submissions': {},
        'contest_pending': False,
        'last_awarded_to': None,
        'updated_at': time.time()
    }
    return jsonify({'ok': True, 'room': ROOMS[code], 'player_id': pid})


@app.route('/api/join', methods=['POST'])
def join_room():
    cleanup_rooms()
    data = request.get_json(silent=True) or {}
    code = str(data.get('code') or '').strip().upper()
    name = str(data.get('name') or 'Player').strip()[:24]
    room = ROOMS.get(code)
    if not room:
        return jsonify({'ok': False, 'error': 'Room not found'}), 404
    competing = [p for p in room['players'] if not p.get('is_umpire')]
    if len(competing) >= 10:
        return jsonify({'ok': False, 'error': 'Room full (max 10 players)'}), 400
    pid = 'p_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    room['players'].append({
        'id': pid, 'name': name, 'score': 0, 'total_time': 0.0, 'is_umpire': False
    })
    room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room, 'player_id': pid})


@app.route('/api/state/<code>')
def get_state(code):
    room = ROOMS.get(code.upper())
    if not room:
        return jsonify({'ok': False, 'error': 'Room expired or not found'}), 404
    return jsonify({'ok': True, 'room': room})


@app.route('/api/kick', methods=['POST'])
def kick():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get(str(data.get('code') or '').upper())
    if not room or data.get('host_id') != room['host_id']:
        return jsonify({'ok': False}), 403
    room['players'] = [p for p in room['players'] if p['id'] != data.get('target_id')]
    room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room})


@app.route('/api/start', methods=['POST'])
def start():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get(str(data.get('code') or '').upper())
    if not room or data.get('player_id') != room['host_id']:
        return jsonify({'ok': False}), 403
    room['phase'] = 'asking'
    room['current_round'] = 1
    room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room})


@app.route('/api/ask', methods=['POST'])
def ask():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get(str(data.get('code') or '').upper())
    if not room:
        return jsonify({'ok': False}), 404
    q = str(data.get('question') or '').strip()
    a = str(data.get('answer') or '').strip()
    if not q or not a:
        return jsonify({'ok': False, 'error': 'Question & answer required'}), 400
    room['question'] = q
    room['answer'] = a
    room['hint'] = build_hint(a)
    room['submissions'] = {}
    room['contest_pending'] = False
    room['last_awarded_to'] = None
    room['question_sent_at'] = time.time()
    room['phase'] = 'answering'
    room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room})


@app.route('/api/guess', methods=['POST'])
def guess():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get(str(data.get('code') or '').upper())
    if not room or room['phase'] != 'answering':
        return jsonify({'ok': False}), 400
    pid = data.get('player_id')
    ans = str(data.get('guess') or '').strip()
    elapsed = round(max(0.1, time.time() - room['question_sent_at']), 2)
    player = next((p for p in room['players'] if p['id'] == pid), None)
    if not player or player.get('is_umpire') or pid in room['submissions']:
        return jsonify({'ok': True, 'room': room})

    correct = (normalize(ans) == normalize(room['answer'])) and bool(ans)
    room['submissions'][pid] = {
        'name': player['name'], 'guess': ans, 'correct': correct, 'time': elapsed
    }

    if room['mode'] == 'umpire':
        if correct:
            player['score'] += 5
            player['total_time'] = round(player['total_time'] + elapsed, 2)
        competing = [p for p in room['players'] if not p.get('is_umpire')]
        if len(room['submissions']) >= len(competing):
            room['phase'] = 'review'
    else:
        setter = room['players'][room['setter_idx'] % len(room['players'])]
        if correct:
            player['score'] += 5
            player['total_time'] = round(player['total_time'] + elapsed, 2)
            room['last_awarded_to'] = player['id']
        else:
            setter['score'] += 5
            room['last_awarded_to'] = setter['id']
        room['phase'] = 'review'

    room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room})


@app.route('/api/timeout', methods=['POST'])
def timeout():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get(str(data.get('code') or '').upper())
    if not room or room['phase'] != 'answering':
        return jsonify({'ok': True, 'room': room})
    if room['mode'] == 'standard':
        setter = room['players'][room['setter_idx'] % len(room['players'])]
        setter['score'] += 5
        room['last_awarded_to'] = setter['id']
    room['phase'] = 'review'
    room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room})


@app.route('/api/contest', methods=['POST'])
def contest():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get(str(data.get('code') or '').upper())
    if room and room['mode'] == 'standard':
        room['contest_pending'] = True
        room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room})


@app.route('/api/resolve_contest', methods=['POST'])
def resolve_contest():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get(str(data.get('code') or '').upper())
    if not room or not room.get('contest_pending'):
        return jsonify({'ok': False}), 400
    accept = bool(data.get('accept_guesser'))
    setter = room['players'][room['setter_idx'] % len(room['players'])]
    gid = next(iter(room['submissions'].keys()), None)
    guesser = next((p for p in room['players'] if p['id'] == gid), None)
    if accept and guesser and room['last_awarded_to'] == setter['id']:
        setter['score'] = max(0, setter['score'] - 5)
        guesser['score'] += 5
        room['last_awarded_to'] = guesser['id']
    elif (not accept) and guesser and room['last_awarded_to'] == guesser['id']:
        guesser['score'] = max(0, guesser['score'] - 5)
        setter['score'] += 5
        room['last_awarded_to'] = setter['id']
    room['contest_pending'] = False
    room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room})


@app.route('/api/next_round', methods=['POST'])
def next_round():
    data = request.get_json(silent=True) or {}
    room = ROOMS.get(str(data.get('code') or '').upper())
    if not room:
        return jsonify({'ok': False}), 404
    if room['current_round'] >= room['total_rounds']:
        room['phase'] = 'gameover'
    else:
        room['current_round'] += 1
        if room['mode'] == 'standard' and room['players']:
            room['setter_idx'] = (room['setter_idx'] + 1) % len(room['players'])
        room['question'] = ''
        room['answer'] = ''
        room['hint'] = ''
        room['submissions'] = {}
        room['contest_pending'] = False
        room['phase'] = 'asking'
    room['updated_at'] = time.time()
    return jsonify({'ok': True, 'room': room})


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Double Sage — Online Multiplayer</title>
<style>
  :root {
    --bg: #090d16;
    --card: #121826;
    --card2: #1a2234;
    --accent: #38bdf8;
    --gold: #facc15;
    --green: #22c55e;
    --red: #ef4444;
    --text: #f8fafc;
    --muted: #94a3b8;
  }
  * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { margin: 0; background: var(--bg); color: var(--text); min-height: 100vh; padding-bottom: 40px; }
  header {
    background: #0f172a; border-bottom: 1px solid #1e293b; padding: 10px 14px;
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px;
    position: sticky; top: 0; z-index: 50;
  }
  .brand { font-weight: 900; font-size: 18px; color: var(--gold); letter-spacing: 0.5px; }
  .controls { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .pill {
    background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
    padding: 6px 11px; border-radius: 999px; font-size: 12px; cursor: pointer; font-weight: 700;
  }
  .pill:active { transform: scale(0.96); }
  .container { max-width: 640px; margin: 14px auto; padding: 0 12px; }
  .card {
    background: var(--card); border: 1px solid #1e293b; border-radius: 16px;
    padding: 16px; margin-bottom: 14px; box-shadow: 0 10px 25px rgba(0,0,0,0.35);
  }
  h2, h3 { margin: 0 0 10px 0; }
  label { display: block; font-size: 12px; color: var(--muted); margin: 10px 0 4px; font-weight: 600; }
  input, select, textarea {
    width: 100%; background: #0b1120; border: 1px solid #334155; color: var(--text);
    padding: 10px 12px; border-radius: 10px; font-size: 15px; outline: none;
  }
  input:focus, select:focus, textarea:focus { border-color: var(--accent); }
  .btn {
    width: 100%; padding: 12px; border: none; border-radius: 12px; font-size: 15px;
    font-weight: 800; cursor: pointer; margin-top: 10px; transition: 0.15s;
  }
  .btn-primary { background: linear-gradient(135deg, #0284c7, #38bdf8); color: #04101d; }
  .btn-gold { background: linear-gradient(135deg, #eab308, #facc15); color: #1a1200; }
  .btn-green { background: var(--green); color: #041f0e; }
  .btn-red { background: var(--red); color: #fff; }
  .btn-dark { background: #1e293b; color: #e2e8f0; border: 1px solid #334155; }
  .btn-sm { width: auto; padding: 8px 12px; font-size: 12px; margin-top: 0; border-radius: 8px; }
  .row { display: flex; gap: 8px; align-items: center; }
  .row > * { flex: 1; }
  .badge {
    display: inline-block; background: #1e293b; color: var(--accent); padding: 4px 10px;
    border-radius: 999px; font-size: 12px; font-weight: 700;
  }
  .hint-box {
    background: #0f172a; border: 1px dashed var(--gold); color: var(--gold);
    padding: 10px 12px; border-radius: 10px; font-weight: 700; font-size: 14px; margin: 10px 0;
  }
  .player-item {
    display: flex; justify-content: space-between; align-items: center;
    background: var(--card2); padding: 10px 12px; border-radius: 10px; margin-bottom: 8px;
  }
  .timer-bar {
    font-size: 22px; font-weight: 900; color: var(--gold); text-align: center;
    background: #0f172a; padding: 8px; border-radius: 10px; margin-bottom: 10px;
  }
  .hidden { display: none !important; }
  #introOverlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(circle at center, #0f172a 0%, #050811 100%);
    z-index: 99999; display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 20px; text-align: center; cursor: pointer;
  }
  #introSlideImg {
    max-width: 90%; max-height: 56vh; border-radius: 18px; pointer-events: none;
    box-shadow: 0 12px 40px rgba(56,189,248,0.4); object-fit: contain;
  }
  #introFallbackCrest {
    width: 140px; height: 140px; border-radius: 28px; pointer-events: none;
    background: linear-gradient(135deg, #0284c7, #facc15); color: #050811;
    display: flex; align-items: center; justify-content: center; font-size: 56px; font-weight: 900;
    box-shadow: 0 12px 35px rgba(250,204,21,0.35);
  }
  #introTitle { margin-top: 16px; font-size: 22px; font-weight: 900; color: var(--gold); pointer-events: none; }
  #introSub { color: #94a3b8; font-size: 13px; margin-top: 6px; pointer-events: none; }
  #skipIntroBtn {
    position: fixed; top: 18px; right: 18px; z-index: 2147483647;
    pointer-events: auto; cursor: pointer; background: var(--gold); color: #000;
    border: 2px solid #fff; padding: 11px 20px; border-radius: 999px; font-weight: 900; font-size: 14px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.75);
  }
  .modal-bg {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.82); z-index: 10000;
    display: flex; align-items: center; justify-content: center; padding: 16px;
  }
  .modal-box {
    background: var(--card); border: 1px solid #334155; border-radius: 16px;
    max-width: 520px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 18px;
  }
</style>
</head>
<body>

<div id="introOverlay" onclick="dismissIntroNow(event)">
  <button id="skipIntroBtn" type="button" onclick="dismissIntroNow(event)">Skip Intro ⏭</button>
  <img id="introSlideImg" src="/double_sage_icon.jpg" alt="Double Sage" onerror="this.classList.add('hidden');document.getElementById('introFallbackCrest').classList.remove('hidden');">
  <div id="introFallbackCrest" class="hidden">⚔️</div>
  <div id="introTitle">DOUBLE SAGE — BATTLE OF MINDS</div>
  <div id="introSub">Tap anywhere or press Skip Intro to enter immediately</div>
</div>

<audio id="bgMusic" src="/theme.mp3" loop preload="auto"></audio>

<header>
  <div class="brand">⚔️ DOUBLE SAGE</div>
  <div class="controls">
    <button class="pill" type="button" onclick="openHowToPlay()">📖 How to Play</button>
    <button class="pill" type="button" onclick="openQBModal()">📚 My QBs</button>
    <button class="pill" id="musicToggleBtn" type="button" onclick="toggleMusic()">🎵 Music: ON</button>
    <label class="pill" style="margin:0;display:inline-block;">
      📂 Load Song
      <input type="file" id="songUploadInput" accept="audio/*" style="display:none" onchange="handleSongUpload(this)">
    </label>
    <button class="pill hidden" id="resetThemeBtn" type="button" style="border-color:#38bdf8;color:#38bdf8;" onclick="resetDefaultTheme()">🔄 Default Theme</button>
    <input type="range" id="volSlider" min="0" max="1" step="0.05" value="0.8" style="width:70px;padding:0;" oninput="setMasterVol(this.value)">
  </div>
</header>

<div class="container">

  <div id="homeView">
    <div class="card">
      <h2>🎮 Create Online Room</h2>
      <label>Your Name</label>
      <input id="hostNameInput" placeholder="Enter your name" maxlength="24">
      <div class="row">
        <div>
          <label>Game Mode</label>
          <select id="gameModeSelect">
            <option value="standard">Standard (Setter vs. Guesser)</option>
            <option value="umpire">Umpire Mode (Ask All Players — Up to 10)</option>
          </select>
        </div>
        <div>
          <label>Rounds / Questions</label>
          <input id="roundsInput" type="number" value="5" min="1" max="30">
        </div>
        <div>
          <label>Timer (sec)</label>
          <input id="timerInput" type="number" value="30" min="10" max="120">
        </div>
      </div>
      <button class="btn btn-primary" type="button" onclick="createRoom()">🚀 Create Room</button>
    </div>

    <div class="card">
      <h2>🔗 Join Existing Room</h2>
      <div class="row">
        <div>
          <label>Your Name</label>
          <input id="joinNameInput" placeholder="Enter your name" maxlength="24">
        </div>
        <div>
          <label>4-Letter Code</label>
          <input id="joinCodeInput" placeholder="ABCD" maxlength="4" style="text-transform:uppercase;">
        </div>
      </div>
      <button class="btn btn-gold" type="button" onclick="joinRoom()">⚡ Join Room</button>
    </div>

    <div class="card">
      <h3>🏆 Live Tournaments & Creator Hub</h3>
      <p style="font-size:13px;color:var(--muted);margin:0 0 10px;">Buy official Pro QB Packs, enter paid weekend tournaments, or support Double Sage.</p>
      <div id="creatorLinkDisplay" style="margin-bottom:8px;"></div>
      <div class="row">
        <input id="creatorUrlInput" placeholder="Paste Paystack / Selar / Flutterwave URL">
        <button class="btn btn-dark btn-sm" type="button" onclick="saveCreatorUrl()">Save Link</button>
      </div>
    </div>
  </div>

  <div id="roomView" class="hidden">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <div>
          <span class="badge" id="roomCodeBadge">ROOM: ----</span>
          <span class="badge" id="roomModeBadge">MODE</span>
          <span class="badge" id="roundBadge">Round 1/5</span>
        </div>
        <button class="pill" type="button" onclick="copyInviteLink()">📋 Copy Invite Link</button>
      </div>
      <div id="scoreboardArea" style="margin-top:12px;"></div>
    </div>

    <div id="lobbyPhase" class="card hidden">
      <h3>⏳ Waiting for Players (Up to 10)</h3>
      <p style="font-size:13px;color:var(--muted);">Share the room code or invite link. The host starts the match once everyone is in.</p>
      <button id="startMatchBtn" class="btn btn-green hidden" type="button" onclick="startMatch()">🔥 Start Match Now</button>
    </div>

    <div id="askingPhase" class="card hidden">
      <div id="askerControls" class="hidden">
        <h3 id="askerTitle">✍️ Set Your Question & Secret Answer</h3>
        <div class="row" style="margin-bottom:6px;">
          <select id="qbQuickSelect"><option value="">-- Load from My QBs --</option></select>
          <button class="btn btn-dark btn-sm" type="button" onclick="pickFromQB()">Load QB</button>
        </div>
        <label>Question</label>
        <input id="liveQuestionInput" placeholder="e.g. Who is the president of Nigeria? or 20 * 5">
        <label>Secret Answer</label>
        <div class="row">
          <input id="liveAnswerInput" placeholder="Type secret answer">
          <button class="btn btn-gold btn-sm" type="button" onclick="suggestAnswer('liveQuestionInput','liveAnswerInput','liveAiStatus')">✨ Suggest</button>
        </div>
        <div id="liveAiStatus" style="font-size:12px;color:var(--accent);margin-top:4px;"></div>
        <button class="btn btn-primary" type="button" onclick="sendQuestion()">📤 Send Question to Players</button>
      </div>
      <div id="waitingAskerBox" class="hidden">
        <h3>⏳ Waiting for Question...</h3>
        <p style="color:var(--muted);font-size:14px;">The Setter/Umpire is preparing the question for this round.</p>
      </div>
    </div>

    <div id="answeringPhase" class="card hidden">
      <div class="timer-bar" id="countdownDisplay">⏱ 30s</div>
      <div style="font-size:18px;font-weight:800;margin-bottom:8px;" id="activeQuestionText"></div>
      <div class="hint-box" id="activeHintText"></div>
      <div id="guesserInputBox">
        <label>Your Guess</label>
        <input id="playerGuessInput" placeholder="Type your answer quickly...">
        <button class="btn btn-green" type="button" onclick="submitGuess()">✅ Submit Answer</button>
      </div>
      <div id="submittedWaitBox" class="hidden">
        <p style="color:var(--green);font-weight:700;">✔ Answer submitted! Waiting for remaining players...</p>
      </div>
    </div>

    <div id="reviewPhase" class="card hidden">
      <h3>📊 Round Results</h3>
      <div style="background:#0f172a;padding:10px;border-radius:10px;margin-bottom:10px;">
        <div style="font-size:12px;color:var(--muted);">Correct Answer:</div>
        <div style="font-size:18px;font-weight:900;color:var(--green);" id="revealAnswerText"></div>
      </div>
      <div id="submissionsList"></div>

      <div id="contestArea" class="hidden" style="margin-top:10px;">
        <button id="contestBtn" class="btn btn-red hidden" type="button" onclick="contestRuling()">⚖️ Contest Ruling (I Was Right!)</button>
        <div id="setterApprovalBox" class="hidden" style="background:#1e293b;padding:12px;border-radius:12px;margin-top:8px;">
          <div style="font-weight:800;color:var(--gold);margin-bottom:8px;">⚖️ Guesser Contested! Was their answer right?</div>
          <div class="row">
            <button class="btn btn-green btn-sm" type="button" onclick="resolveContest(true)">✅ Accept Guesser (+5 Pts)</button>
            <button class="btn btn-red btn-sm" type="button" onclick="resolveContest(false)">❌ Reject (Setter Keeps +5)</button>
          </div>
        </div>
      </div>

      <button id="nextRoundBtn" class="btn btn-primary hidden" type="button" onclick="nextRound()">➡️ Next Round</button>
    </div>

    <div id="gameoverPhase" class="card hidden">
      <h2 style="color:var(--gold);text-align:center;">🏆 MATCH COMPLETE!</h2>
      <div id="finalPodium"></div>
      <button class="btn btn-primary" type="button" onclick="location.href='/'">🏠 Back to Home</button>
    </div>
  </div>
</div>

<div id="howToPlayModal" class="modal-bg hidden" onclick="if(event.target===this)this.classList.add('hidden')">
  <div class="modal-box">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h2 style="color:var(--gold);">📖 How to Play Double Sage</h2>
      <button class="pill" type="button" onclick="document.getElementById('howToPlayModal').classList.add('hidden')">✕</button>
    </div>
    <p style="font-size:14px;line-height:1.5;"><b>1. Standard Mode (Setter vs. Guesser):</b> Players take turns setting a secret question and answer. You get a smart hint showing word count, letter count, and digits (only when numbers are present). Match the answer before time runs out for <b>+5 pts</b>; miss and the Setter gets <b>+5 pts</b>. Think you were judged unfairly? Tap <b>⚖️ Contest</b> for Setter review!</p>
    <p style="font-size:14px;line-height:1.5;"><b>2. Simultaneous Umpire Mode (1–10 Players):</b> The Umpire is the organizer (<b>0 points</b>) who sets the total rounds and asks <b>all players the exact same question at once</b>. Everyone who gets it right earns <b>+5 pts</b> with their speed recorded; if nobody gets it, <b>0 points</b> are awarded.</p>
    <p style="font-size:14px;line-height:1.5;"><b>3. Smart AI Helper & My QBs:</b> Tap <b>✨ Suggest</b> when writing questions to auto-solve math (like <code>20 * 5</code>) or pull factual answers (personal questions like <i>"What is my nickname?"</i> stay private). Save question sets in <b>📚 My QBs</b> or unlock Pro Packs!</p>
  </div>
</div>

<div id="qbModal" class="modal-bg hidden" onclick="if(event.target===this)this.classList.add('hidden')">
  <div class="modal-box">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h2 style="color:var(--accent);">📚 My QBs & Pro Packs</h2>
      <button class="pill" type="button" onclick="document.getElementById('qbModal').classList.add('hidden')">✕</button>
    </div>

    <label>Add Question to My QB</label>
    <input id="qbQInput" placeholder="Enter question">
    <div class="row" style="margin-top:6px;">
      <input id="qbAInput" placeholder="Enter answer">
      <button class="btn btn-gold btn-sm" type="button" onclick="suggestAnswer('qbQInput','qbAInput','qbAiStatus')">✨ Suggest</button>
    </div>
    <div id="qbAiStatus" style="font-size:12px;color:var(--accent);margin-top:4px;"></div>
    <button class="btn btn-primary btn-sm" type="button" style="margin-top:8px;" onclick="addQBItem()">➕ Save to My QB</button>

    <label>🎟️ Unlock Pro QB Pack (e.g., NAIJA2026, FOOTYPRO, PARTYVIP, or DSPACK:...)</label>
    <div class="row">
      <input id="packCodeInput" placeholder="Enter pack code">
      <button class="btn btn-green btn-sm" type="button" onclick="redeemPack()">Unlock</button>
    </div>
    <div style="margin-top:8px;">
      <button class="btn btn-dark btn-sm" type="button" onclick="exportSellablePack()">📤 Export My QB as Sellable DSPACK Code</button>
      <textarea id="exportedPackBox" class="hidden" rows="2" style="margin-top:6px;font-size:11px;" readonly></textarea>
    </div>

    <div id="qbListContainer" style="margin-top:12px;"></div>
  </div>
</div>

<script>
const INTRO_SLIDES = [
  { img: '/double_sage_icon.jpg', title: 'DOUBLE SAGE — BATTLE OF MINDS' },
  { img: '/double_sage_battle.jpg', title: 'OUTSMART RIVALS & BEAT THE CLOCK' },
  { img: '/double_sage_banner.jpg', title: 'SIMULTANEOUS UMPIRE & DUEL MODES' },
  { img: '/double_sage_tournament.jpg', title: 'CLIMB THE LEADERBOARD TO VICTORY' }
];
let slideIdx = 0;
let slideInterval = null;

function dismissIntroNow(e) {
  if (e && e.stopPropagation) e.stopPropagation();
  if (slideInterval) {
    clearInterval(slideInterval);
    slideInterval = null;
  }
  const ov = document.getElementById('introOverlay');
  if (ov) {
    ov.style.display = 'none';
    ov.remove();
  }
  try { startThemeAudio(); } catch (err) {}
}

slideInterval = setInterval(() => {
  const ov = document.getElementById('introOverlay');
  if (!ov) {
    clearInterval(slideInterval);
    return;
  }
  slideIdx++;
  if (slideIdx >= INTRO_SLIDES.length) {
    dismissIntroNow();
    return;
  }
  const imgEl = document.getElementById('introSlideImg');
  const crestEl = document.getElementById('introFallbackCrest');
  const titleEl = document.getElementById('introTitle');
  if (imgEl) {
    if (crestEl) crestEl.classList.add('hidden');
    imgEl.classList.remove('hidden');
    imgEl.src = INTRO_SLIDES[slideIdx].img;
  }
  if (titleEl) titleEl.textContent = INTRO_SLIDES[slideIdx].title;
}, 3000);

let musicEnabled = true;
let audioCtx = null;
let synthTimer = null;

function startThemeAudio() {
  if (!musicEnabled) return;
  const bg = document.getElementById('bgMusic');
  if (bg) {
    bg.volume = parseFloat(document.getElementById('volSlider').value || 0.8);
    bg.play().catch(() => startSynthFallback());
  }
}

function startSynthFallback() {
  if (synthTimer || !musicEnabled) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const notes = [261.63, 329.63, 392.00, 523.25, 392.00, 329.63];
    let step = 0;
    synthTimer = setInterval(() => {
      if (!musicEnabled) return;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'triangle';
      osc.frequency.value = notes[step % notes.length];
      gain.gain.value = 0.04 * parseFloat(document.getElementById('volSlider').value || 0.8);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.22);
      step++;
    }, 450);
  } catch (e) {}
}

function toggleMusic() {
  musicEnabled = !musicEnabled;
  const btn = document.getElementById('musicToggleBtn');
  const bg = document.getElementById('bgMusic');
  btn.textContent = musicEnabled ? '🎵 Music: ON' : '🎵 Music: OFF';
  if (musicEnabled) {
    startThemeAudio();
  } else {
    if (bg) bg.pause();
    if (synthTimer) { clearInterval(synthTimer); synthTimer = null; }
  }
}

function setMasterVol(v) {
  const bg = document.getElementById('bgMusic');
  if (bg) bg.volume = parseFloat(v);
}

function handleSongUpload(inp) {
  if (!inp.files || !inp.files[0]) return;
  if (synthTimer) { clearInterval(synthTimer); synthTimer = null; }
  const bg = document.getElementById('bgMusic');
  bg.src = URL.createObjectURL(inp.files[0]);
  bg.loop = true;
  if (musicEnabled) bg.play().catch(() => {});
  document.getElementById('resetThemeBtn').classList.remove('hidden');
}

function resetDefaultTheme() {
  const inp = document.getElementById('songUploadInput');
  if (inp) inp.value = '';
  const bg = document.getElementById('bgMusic');
  bg.pause();
  bg.src = '/theme.mp3';
  bg.loop = true;
  bg.load();
  if (musicEnabled) bg.play().catch(() => startSynthFallback());
  document.getElementById('resetThemeBtn').classList.add('hidden');
}

const FACT_BANK = {
  'president of nigeria': 'Bola Ahmed Tinubu',
  'capital of nigeria': 'Abuja',
  'capital of france': 'Paris',
  'capital of japan': 'Tokyo',
  'capital of uk': 'London',
  'capital of united kingdom': 'London',
  'capital of usa': 'Washington DC',
  'capital of united states': 'Washington DC',
  'president of usa': 'Donald Trump',
  'president of the united states': 'Donald Trump',
  'tallest mountain': 'Mount Everest',
  'largest ocean': 'Pacific Ocean',
  'fastest land animal': 'Cheetah',
  'red planet': 'Mars'
};

async function suggestAnswer(qId, aId, statusId) {
  const qRaw = document.getElementById(qId).value.trim();
  const statusEl = document.getElementById(statusId);
  const ansEl = document.getElementById(aId);
  if (!qRaw) { statusEl.textContent = 'Type a question first.'; return; }

  const lower = qRaw.toLowerCase();
  if (/\b(my|me|i|mine|our|we|us|nickname|favorite|favourite|birthday|girlfriend|boyfriend|crush)\b/i.test(lower)) {
    statusEl.textContent = '🔒 Personal question detected — enter your own secret answer!';
    return;
  }

  const cleanedMath = lower.replace(/what is|calculate|solve|=|\?/g, '').replace(/x/g, '*').replace(/÷/g, '/').trim();
  if (/^[0-9+\-*/().\s]+$/.test(cleanedMath) && /[0-9]/.test(cleanedMath)) {
    try {
      const val = Function('"use strict";return (' + cleanedMath + ')')();
      if (typeof val === 'number' && isFinite(val)) {
        ansEl.value = String(Number.isInteger(val) ? val : Math.round(val * 100) / 100);
        statusEl.textContent = '✅ Solved math expression!';
        return;
      }
    } catch (e) {}
  }

  for (const [k, v] of Object.entries(FACT_BANK)) {
    if (lower.includes(k)) {
      ansEl.value = v;
      statusEl.textContent = '✅ Suggested factual answer!';
      return;
    }
  }

  statusEl.textContent = '🔍 Searching factual answer...';
  try {
    const query = qRaw.replace(/^(who is|what is|where is|when was|who was|the)\s+/i, '').replace(/\?/g, '').trim();
    const res = await fetch('https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=' + encodeURIComponent(query) + '&format=json&origin=*');
    const data = await res.json();
    const hits = (data.query && data.query.search) || [];
    if (hits.length > 0) {
      let best = hits[0].title;
      if (best.toLowerCase().includes(query.toLowerCase()) && hits.length > 1) {
        best = hits[1].title;
      }
      ansEl.value = best.replace(/\s*\(.*?\)\s*/g, '').trim();
      statusEl.textContent = '✅ Suggested from knowledge base!';
    } else {
      statusEl.textContent = 'No exact match found — type your answer manually.';
    }
  } catch (e) {
    statusEl.textContent = 'Offline — type your answer manually.';
  }
}

const PRO_PACKS = {
  'NAIJA2026': [
    { q: 'Who is the president of Nigeria?', a: 'Bola Ahmed Tinubu' },
    { q: 'What is the capital city of Nigeria?', a: 'Abuja' },
    { q: 'Which Nigerian artist won Best African Music Performance at the 2024 Grammys?', a: 'Tyla' },
    { q: 'What year did Nigeria gain independence?', a: '1960' },
    { q: 'What is the largest city by population in Nigeria?', a: 'Lagos' }
  ],
  'FOOTYPRO': [
    { q: 'Which country won the 2022 FIFA World Cup?', a: 'Argentina' },
    { q: 'Who has won the most Ballon dOr awards?', a: 'Lionel Messi' },
    { q: 'Which club has won the most UEFA Champions League titles?', a: 'Real Madrid' },
    { q: 'How many players are on the pitch for one football team?', a: '11' }
  ],
  'PARTYVIP': [
    { q: 'What is 25 * 4?', a: '100' },
    { q: 'How many days are in a leap year?', a: '366' },
    { q: 'Which planet is known as the Red Planet?', a: 'Mars' },
    { q: 'What gas do plants absorb from the atmosphere?', a: 'Carbon Dioxide' }
  ]
};

function getQB() {
  try { return JSON.parse(localStorage.getItem('ds_my_qb') || '[]'); } catch (e) { return []; }
}
function saveQB(list) {
  localStorage.setItem('ds_my_qb', JSON.stringify(list));
  renderQB();
}
function openQBModal() {
  renderQB();
  document.getElementById('qbModal').classList.remove('hidden');
}
function addQBItem() {
  const q = document.getElementById('qbQInput').value.trim();
  const a = document.getElementById('qbAInput').value.trim();
  if (!q || !a) return;
  const list = getQB();
  list.push({ q, a });
  saveQB(list);
  document.getElementById('qbQInput').value = '';
  document.getElementById('qbAInput').value = '';
}
function deleteQBItem(idx) {
  const list = getQB();
  list.splice(idx, 1);
  saveQB(list);
}
function redeemPack() {
  const raw = document.getElementById('packCodeInput').value.trim();
  if (!raw) return;
  const upper = raw.toUpperCase();
  const list = getQB();
  if (PRO_PACKS[upper]) {
    PRO_PACKS[upper].forEach(item => list.push(item));
    saveQB(list);
    alert('Unlocked ' + PRO_PACKS[upper].length + ' questions from ' + upper + '!');
    document.getElementById('packCodeInput').value = '';
    return;
  }
  if (raw.startsWith('DSPACK:')) {
    try {
      const decoded = JSON.parse(atob(raw.slice(7)));
      if (Array.isArray(decoded)) {
        decoded.forEach(item => { if (item.q && item.a) list.push({ q: item.q, a: item.a }); });
        saveQB(list);
        alert('Imported ' + decoded.length + ' custom pack questions!');
        document.getElementById('packCodeInput').value = '';
        return;
      }
    } catch (e) {}
  }
  alert('Invalid pack code.');
}
function exportSellablePack() {
  const list = getQB();
  if (!list.length) { alert('Add questions to My QB first!'); return; }
  const code = 'DSPACK:' + btoa(JSON.stringify(list));
  const box = document.getElementById('exportedPackBox');
  box.value = code;
  box.classList.remove('hidden');
  box.select();
}
function renderQB() {
  const list = getQB();
  const container = document.getElementById('qbListContainer');
  const sel = document.getElementById('qbQuickSelect');
  sel.innerHTML = '<option value="">-- Load from My QBs (' + list.length + ') --</option>';
  container.innerHTML = '';
  list.forEach((item, i) => {
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = item.q;
    sel.appendChild(opt);

    const row = document.createElement('div');
    row.className = 'player-item';
    row.innerHTML = '<div style="font-size:13px;"><b>' + escapeHtml(item.q) + '</b><br><span style="color:var(--green);">Ans: ' + escapeHtml(item.a) + '</span></div>' +
      '<button class="pill" type="button" onclick="deleteQBItem(' + i + ')">🗑</button>';
    container.appendChild(row);
  });
}
function pickFromQB() {
  const idx = document.getElementById('qbQuickSelect').value;
  if (idx === '') return;
  const item = getQB()[parseInt(idx, 10)];
  if (item) {
    document.getElementById('liveQuestionInput').value = item.q;
    document.getElementById('liveAnswerInput').value = item.a;
  }
}

function saveCreatorUrl() {
  const url = document.getElementById('creatorUrlInput').value.trim();
  localStorage.setItem('ds_creator_url', url);
  renderCreatorUrl();
}
function renderCreatorUrl() {
  const url = localStorage.getItem('ds_creator_url') || '';
  const box = document.getElementById('creatorLinkDisplay');
  if (url) {
    box.innerHTML = '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener" class="btn btn-gold" style="display:block;text-align:center;text-decoration:none;">🎟️ Buy Tournament Ticket / Support Creator</a>';
  } else {
    box.innerHTML = '';
  }
}

function openHowToPlay() {
  document.getElementById('howToPlayModal').classList.remove('hidden');
}

function escapeHtml(str) {
  return String(str || '').replace(/[&<>"']/g, function(m) {
    return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m];
  });
}

let currentCode = '';
let myPlayerId = '';
let pollTimer = null;

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  return res.json();
}

async function createRoom() {
  const name = document.getElementById('hostNameInput').value.trim() || 'Host';
  const mode = document.getElementById('gameModeSelect').value;
  const rounds = parseInt(document.getElementById('roundsInput').value || 5, 10);
  const timer = parseInt(document.getElementById('timerInput').value || 30, 10);
  const res = await apiPost('/api/create', { name, mode, rounds, timer });
  if (res.ok) enterRoom(res.room, res.player_id);
  else alert(res.error || 'Failed to create room');
}

async function joinRoom() {
  const name = document.getElementById('joinNameInput').value.trim() || 'Player';
  const code = document.getElementById('joinCodeInput').value.trim().toUpperCase();
  if (!code) { alert('Enter a 4-letter room code'); return; }
  const res = await apiPost('/api/join', { name, code });
  if (res.ok) enterRoom(res.room, res.player_id);
  else alert(res.error || 'Could not join room');
}

function enterRoom(room, pid) {
  currentCode = room.code;
  myPlayerId = pid;
  document.getElementById('homeView').classList.add('hidden');
  document.getElementById('roomView').classList.remove('hidden');
  renderQB();
  renderRoom(room);
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch('/api/state/' + currentCode);
      const data = await r.json();
      if (data.ok) renderRoom(data.room);
    } catch (e) {}
  }, 1500);
}

function copyInviteLink() {
  const link = location.origin + '/?room=' + currentCode;
  if (navigator.clipboard) navigator.clipboard.writeText(link);
  alert('Copied invite link: ' + link);
}

async function kickPlayer(targetId) {
  const res = await apiPost('/api/kick', { code: currentCode, host_id: myPlayerId, target_id: targetId });
  if (res.ok) renderRoom(res.room);
}

async function startMatch() {
  const res = await apiPost('/api/start', { code: currentCode, player_id: myPlayerId });
  if (res.ok) renderRoom(res.room);
}

async function sendQuestion() {
  const question = document.getElementById('liveQuestionInput').value.trim();
  const answer = document.getElementById('liveAnswerInput').value.trim();
  if (!question || !answer) { alert('Enter both a question and answer'); return; }
  const res = await apiPost('/api/ask', { code: currentCode, question, answer });
  if (res.ok) {
    document.getElementById('liveQuestionInput').value = '';
    document.getElementById('liveAnswerInput').value = '';
    renderRoom(res.room);
  }
}

async function submitGuess() {
  const guess = document.getElementById('playerGuessInput').value.trim();
  const res = await apiPost('/api/guess', { code: currentCode, player_id: myPlayerId, guess });
  if (res.ok) {
    document.getElementById('playerGuessInput').value = '';
    renderRoom(res.room);
  }
}

async function contestRuling() {
  const res = await apiPost('/api/contest', { code: currentCode });
  if (res.ok) renderRoom(res.room);
}

async function resolveContest(acceptGuesser) {
  const res = await apiPost('/api/resolve_contest', { code: currentCode, accept_guesser: acceptGuesser });
  if (res.ok) renderRoom(res.room);
}

async function nextRound() {
  const res = await apiPost('/api/next_round', { code: currentCode });
  if (res.ok) renderRoom(res.room);
}

function renderRoom(room) {
  const me = room.players.find(p => p.id === myPlayerId);
  if (!me) {
    alert('You were removed from the room.');
    location.href = '/';
    return;
  }
  const isHost = (room.host_id === myPlayerId);
  document.getElementById('roomCodeBadge').textContent = 'ROOM: ' + room.code;
  document.getElementById('roomModeBadge').textContent = room.mode === 'umpire' ? 'UMPIRE MODE' : 'STANDARD MODE';
  document.getElementById('roundBadge').textContent = 'Round ' + room.current_round + '/' + room.total_rounds;

  const sb = document.getElementById('scoreboardArea');
  sb.innerHTML = '';
  room.players.forEach(p => {
    const div = document.createElement('div');
    div.className = 'player-item';
    const roleTag = p.is_umpire ? '<span class="badge" style="color:var(--gold);">🎙 Umpire (Organizer)</span>' :
      '<span style="font-weight:900;color:var(--green);">' + p.score + ' pts</span> <span style="font-size:11px;color:var(--muted);">(' + p.total_time + 's)</span>';
    const kickBtn = (isHost && p.id !== myPlayerId) ? ' <button class="pill" type="button" onclick="kickPlayer(\'' + p.id + '\')">Kick</button>' : '';
    div.innerHTML = '<div><b>' + escapeHtml(p.name) + '</b>' + (p.id === myPlayerId ? ' (You)' : '') + '</div><div>' + roleTag + kickBtn + '</div>';
    sb.appendChild(div);
  });

  ['lobbyPhase', 'askingPhase', 'answeringPhase', 'reviewPhase', 'gameoverPhase'].forEach(id => {
    document.getElementById(id).classList.add('hidden');
  });

  if (room.phase === 'lobby') {
    document.getElementById('lobbyPhase').classList.remove('hidden');
    document.getElementById('startMatchBtn').classList.toggle('hidden', !isHost);
  } else if (room.phase === 'asking') {
    document.getElementById('askingPhase').classList.remove('hidden');
    const setter = room.players[room.setter_idx % room.players.length];
    const amAsker = (room.mode === 'umpire') ? me.is_umpire : (setter && setter.id === myPlayerId);
    document.getElementById('askerControls').classList.toggle('hidden', !amAsker);
    document.getElementById('waitingAskerBox').classList.toggle('hidden', amAsker);
    if (amAsker) {
      document.getElementById('askerTitle').textContent = room.mode === 'umpire'
        ? '🎙 Ask All Players Simultaneously'
        : '✍️ Your Turn to Set a Question';
    }
  } else if (room.phase === 'answering') {
    document.getElementById('answeringPhase').classList.remove('hidden');
    document.getElementById('activeQuestionText').textContent = '❓ ' + room.question;
    document.getElementById('activeHintText').textContent = '💡 Hint: ' + room.hint;

    const setter = room.players[room.setter_idx % room.players.length];
    const isAsker = (room.mode === 'umpire') ? me.is_umpire : (setter && setter.id === myPlayerId);
    const alreadySubmitted = Boolean(room.submissions && room.submissions[myPlayerId]);

    document.getElementById('guesserInputBox').classList.toggle('hidden', isAsker || alreadySubmitted);
    document.getElementById('submittedWaitBox').classList.toggle('hidden', !isAsker && !alreadySubmitted);
    if (isAsker) {
      document.getElementById('submittedWaitBox').innerHTML = '<p style="color:var(--accent);font-weight:700;">⏳ Players are answering your question...</p>';
    }

    const elapsed = (Date.now() / 1000) - room.question_sent_at;
    const rem = Math.max(0, Math.ceil(room.timer - elapsed));
    document.getElementById('countdownDisplay').textContent = '⏱ ' + rem + 's';
    if (rem <= 0 && isHost) {
      apiPost('/api/timeout', { code: currentCode });
    }
  } else if (room.phase === 'review') {
    document.getElementById('reviewPhase').classList.remove('hidden');
    document.getElementById('revealAnswerText').textContent = room.answer;

    const subList = document.getElementById('submissionsList');
    subList.innerHTML = '';
    const subs = Object.values(room.submissions || {});
    if (!subs.length) {
      subList.innerHTML = '<p style="color:var(--muted);">No answers submitted before time expired (0 pts awarded).</p>';
    } else {
      subs.forEach(s => {
        const badge = s.correct
          ? '<span style="color:var(--green);font-weight:800;">✅ +5 pts (' + s.time + 's)</span>'
          : '<span style="color:var(--red);font-weight:800;">❌ 0 pts (' + s.time + 's)</span>';
        subList.innerHTML += '<div class="player-item"><div><b>' + escapeHtml(s.name) + ':</b> ' + escapeHtml(s.guess) + '</div><div>' + badge + '</div></div>';
      });
    }

    const contestArea = document.getElementById('contestArea');
    if (room.mode === 'standard') {
      contestArea.classList.remove('hidden');
      const setter = room.players[room.setter_idx % room.players.length];
      const amSetter = setter && setter.id === myPlayerId;
      document.getElementById('contestBtn').classList.toggle('hidden', amSetter || room.contest_pending);
      document.getElementById('setterApprovalBox').classList.toggle('hidden', !amSetter || !room.contest_pending);
    } else {
      contestArea.classList.add('hidden');
    }

    document.getElementById('nextRoundBtn').classList.toggle('hidden', !isHost || room.contest_pending);
  } else if (room.phase === 'gameover') {
    document.getElementById('gameoverPhase').classList.remove('hidden');
    const ranked = room.players.filter(p => !p.is_umpire).sort((a, b) => (b.score - a.score) || (a.total_time - b.total_time));
    const pod = document.getElementById('finalPodium');
    pod.innerHTML = '';
    ranked.forEach((p, idx) => {
      const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '#' + (idx + 1);
      pod.innerHTML += '<div class="player-item"><div><b>' + medal + ' ' + escapeHtml(p.name) + '</b></div><div><b style="color:var(--gold);">' + p.score + ' pts</b> (' + p.total_time + 's)</div></div>';
    });
  }
}

window.addEventListener('DOMContentLoaded', () => {
  renderCreatorUrl();
  const params = new URLSearchParams(location.search);
  const code = params.get('room');
  if (code) document.getElementById('joinCodeInput').value = code.toUpperCase().slice(0, 4);
});
</script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

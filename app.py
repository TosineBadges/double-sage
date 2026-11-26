import os
import re
import time
import random
import string
from flask import Flask, request, jsonify, send_from_directory, render_template_string

app = Flask(__name__, static_folder='.', static_url_path='')

ROOMS = {}
ROOM_TTL = 7200
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
    target_lower = filename.lower()
    stem = os.path.splitext(target_lower)[0]
    valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp3', '.wav', '.ogg', '.m4a', '.js', '.css'}

    for root_dir in ('.', 'static', 'media', 'images', 'assets', 'public'):
        if os.path.isfile(os.path.join(root_dir, filename)):
            return root_dir, filename

    for dirpath, _, filenames in os.walk('.'):
        if '/.' in dirpath or '\\.' in dirpath:
            continue
        for f in filenames:
            fl = f.lower()
            if fl == target_lower:
                return dirpath, f
            f_stem, f_ext = os.path.splitext(fl)
            if f_stem == stem and f_ext in valid_exts:
                return dirpath, f
    return None, None


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/<path:filename>')
def serve_files(filename):
    if filename.endswith('.py'):
        return jsonify({'error': 'Forbidden'}), 403
    folder, actual = find_asset_file(os.path.basename(filename))
    if folder and actual:
        return send_from_directory(folder, actual)
    return jsonify({'error': 'Not found'}), 404


@app.route('/media/<path:filename>')
def serve_media(filename):
    folder, actual = find_asset_file(os.path.basename(filename))
    if folder and actual:
        return send_from_directory(folder, actual)
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


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Double Sage — Online Multiplayer</title>
<script src="https://jsdelivr.net" defer></script>
<script src="/packs.js?v=3" defer></script>
<style>
  :root { --bg:#090d16; --card:#121826; --card2:#1a2234; --accent:#38bdf8; --gold:#facc15; --green:#22c55e; --red:#ef4444; --text:#f8fafc; --muted:#94a3b8; }
  * { box-sizing:border-box; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  body { margin:0; background:var(--bg); color:var(--text); min-height:100vh; padding-bottom:40px; }
  header { background:#0f172a; border-bottom:1px solid #1e293b; padding:10px 14px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; position:sticky; top:0; z-index:50; }
  .brand { font-weight:900; font-size:18px; color:var(--gold); letter-spacing:0.5px; }
  .controls { display:flex; flex-wrap:wrap; align-items:center; gap:6px; }
  .pill { background:#1e293b; color:#e2e8f0; border:1px solid #334155; padding:5px 10px; border-radius:999px; font-size:12px; cursor:pointer; font-weight:600; }
  .container { max-width:640px; margin:14px auto; padding:0 12px; }
  .card { background:var(--card); border:1px solid #1e293b; border-radius:16px; padding:16px; margin-bottom:14px; box-shadow:0 10px 25px rgba(0,0,0,0.35); }
  h2, h3 { margin:0 0 10px 0; }
  label { display:block; font-size:12px; color:var(--muted); margin:10px 0 4px; font-weight:600; }
  input, select, textarea { width:100%; background:#0b1120; border:1px solid #334155; color:var(--text); padding:10px 12px; border-radius:10px; font-size:15px; outline:none; }
  .btn { width:100%; padding:12px; border:none; border-radius:12px; font-size:15px; font-weight:800; cursor:pointer; margin-top:10px; }
  .btn-primary { background:linear-gradient(135deg,#0284c7,#38bdf8); color:#04101d; }
  .btn-gold { background:linear-gradient(135deg,#eab308,#facc15); color:#1a1200; }
  .btn-green { background:var(--green); color:#041f0e; }
  .btn-red { background:var(--red); color:#fff; }
  .btn-dark { background:#1e293b; color:#e2e8f0; border:1px solid #334155; }
  .btn-sm { width:auto; padding:7px 12px; font-size:12px; margin-top:0; border-radius:8px; }
  .row { display:flex; gap:8px; align-items:center; }
  .row > * { flex:1; }
  .badge { display:inline-block; background:#1e293b; color:var(--accent); padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700; }
  .hint-box { background:#0f172a; border:1px dashed var(--gold); color:var(--gold); padding:10px 12px; border-radius:10px; font-weight:700; font-size:14px; margin:10px 0; }
  .player-item { display:flex; justify-content:space-between; align-items:center; background:var(--card2); padding:10px 12px; border-radius:10px; margin-bottom:8px; }
  .timer-bar { font-size:22px; font-weight:900; color:var(--gold); text-align:center; background:#0f172a; padding:8px; border-radius:10px; margin-bottom:10px; }
  .hidden { display:none !important; }
  #introOverlay { position:fixed; inset:0; background:#050811; z-index:99999; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:20px; text-align:center; }
  #introSlideImg { max-width:92%; max-height:62vh; border-radius:18px; box-shadow:0 12px 40px rgba(56,189,248,0.35); object-fit:contain; pointer-events:none; }
  #introTitle { margin-top:14px; font-size:22px; font-weight:900; color:var(--gold); pointer-events:none; }
  #skipIntroBtn { position:fixed; top:16px; right:16px; z-index:2147483647; cursor:pointer; background:var(--gold); color:#000; border:none; padding:10px 18px; border-radius:999px; font-weight:900; font-size:14px; }
  .modal-bg { position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:10000; display:flex; align-items:center; justify-content:center; padding:16px; }
  .modal-box { background:var(--card); border:1px solid #334155; border-radius:16px; max-width:520px; width:100%; max-height:85vh; overflow-y:auto; padding:18px; }
  .victory-poster { background:radial-gradient(circle at top,#1e293b 0%,#090d16 85%); border:2px solid var(--gold); border-radius:18px; padding:20px 16px; text-align:center; box-shadow:0 0 30px rgba(250,204,21,0.25); margin-bottom:14px; }
  .victory-trophy { font-size:52px; line-height:1.1; margin-bottom:6px; }
  .victory-title { font-size:13px; font-weight:800; letter-spacing:2px; color:var(--accent); text-transform:uppercase; }
  .victory-winner { font-size:28px; font-weight:900; color:var(--gold); margin:6px 0; }
  .victory-score-pill { display:inline-block; background:rgba(34,197,94,0.15); border:1px solid var(--green); color:var(--green); font-weight:900; font-size:16px; padding:6px 16px; border-radius:999px; margin:6px 0 12px; }
  .victory-share-box { background:#0b1120; border:1px solid #334155; border-radius:12px; padding:10px; text-align:left; margin-top:10px; }
</style>
</head>
<body>

<div id="introOverlay">
  <button id="skipIntroBtn" type="button" onclick="this.parentElement.style.display='none';if(window.startThemeAudio)startThemeAudio();">Skip Intro ⏭</button>
  <img id="introSlideImg" src="/double_sage_icon.jpg" alt="Double Sage" onerror="this.style.display='none'">
  <div id="introTitle">DOUBLE SAGE — BATTLE OF MINDS</div>
  <div style="color:#94a3b8;font-size:13px;margin-top:6px;pointer-events:none;">Press Skip Intro to enter immediately</div>
</div>

<audio id="bgMusic" src="/theme.mp3" loop preload="metadata"></audio>


<header>
  <div class="brand">⚔️ DOUBLE SAGE</div>
  <div class="controls">
    <button class="pill" type="button" onclick="openHowToPlay()">📖 How to Play</button>
    <button class="pill" type="button" onclick="openQBModal()">📚 My QBs</button>
    <button class="pill" id="musicToggleBtn" type="button" onclick="toggleMusic()">🎵 Music: ON</button>
    <label class="pill" style="margin:0;display:inline-block;">📂 Load Song<input type="file" id="songUploadInput" accept="audio/*" style="display:none" onchange="handleSongUpload(this)"></label>
    <button class="pill hidden" id="resetThemeBtn" type="button" style="border-color:#38bdf8;color:#38bdf8;" onclick="resetDefaultTheme()">🔄 Default Theme</button>
    <input type="range" id="volSlider" min="0" max="1" step="0.05" value="0.8" style="width:70px;padding:0;" oninput="setMasterVol(this.value)">
  </div>
</header>

<div class="container">
  <div id="homeView">
    <div id="rejoinBanner" class="card hidden" style="border:1px solid var(--green);background:#0d1f17;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
        <div><div style="font-weight:900;color:var(--green);">🔄 Active Match Found!</div><div id="rejoinBannerText" style="font-size:12px;color:#cbd5e1;">Room ----</div></div>
        <div style="display:flex;gap:6px;"><button class="btn btn-green btn-sm" type="button" onclick="rejoinSavedRoom()">Rejoin Now</button><button class="btn btn-dark btn-sm" type="button" onclick="clearSavedRoom()">Dismiss</button></div>
      </div>
    </div>

    <div class="card" style="border:1px solid var(--accent);">
      <h2 style="color:var(--accent);">🤖 Play vs. Sage Bot (Instant Solo Duel)</h2>
      <p style="font-size:13px;color:var(--muted);margin:0 0 8px;">No opponent online yet? Battle Sage Bot using any pack right now!</p>
      <div class="row">
        <div><label>Select Pack</label><select id="botPackSelect"></select></div>
        <div><label>Bot Difficulty</label><select id="botDiffSelect"><option value="rookie">Rookie (Casual)</option><option value="pro" selected>Pro (Balanced)</option><option value="grandmaster">Grandmaster (Fast)</option></select></div>
      </div>
      <button class="btn btn-primary" type="button" onclick="startBotMatch()">🤖 Start Solo Duel vs. Sage Bot</button>
    </div>

    <div class="card">
      <h2>🎮 Create Online Room</h2>
      <label>Your Name</label>
      <input id="hostNameInput" placeholder="Enter your name" maxlength="24">
      <div class="row">
        <div><label>Game Mode</label><select id="gameModeSelect"><option value="standard">Standard (Setter vs Guesser)</option><option value="umpire">Umpire Mode (Ask All Players — Up to 10)</option></select></div>
        <div><label>Rounds / Questions</label><input id="roundsInput" type="number" value="5" min="1" max="30"></div>
        <div><label>Timer (sec)</label><input id="timerInput" type="number" value="30" min="10" max="120"></div>
      </div>
      <button class="btn btn-primary" type="button" onclick="createRoom()">🚀 Create Room</button>
    </div>

    <div class="card">
      <h2>🔗 Join Existing Room</h2>
      <div class="row">
        <div><label>Your Name</label><input id="joinNameInput" placeholder="Enter your name" maxlength="24"></div>
        <div><label>4-Letter Code</label><input id="joinCodeInput" placeholder="ABCD" maxlength="4" style="text-transform:uppercase;"></div>
      </div>
      <button class="btn btn-gold" type="button" onclick="joinRoom()">⚡ Join Room</button>
    </div>

    <div class="card">
      <h3>🏆 Live Tournaments & Creator Hub</h3>
      <p style="font-size:13px;color:var(--muted);margin:0 0 10px;">Buy official Pro QB Packs, enter paid weekend tournaments, or support Double Sage.</p>
      <div id="creatorLinkDisplay" style="margin-bottom:8px;"></div>
      <div class="row"><input id="creatorUrlInput" placeholder="Paste Paystack / Selar / Flutterwave URL"><button class="btn btn-dark btn-sm" type="button" onclick="saveCreatorUrl()">Save Link</button></div>
    </div>
  </div>

  <div id="roomView" class="hidden">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <div><span class="badge" id="roomCodeBadge">ROOM: ----</span> <span class="badge" id="roomModeBadge">MODE</span> <span class="badge" id="roundBadge">Round 1/5</span></div>
        <div style="display:flex;gap:6px;"><button class="pill" type="button" onclick="copyInviteLink()">📋 Invite</button><button class="pill" type="button" style="border-color:var(--red);color:#fca5a5;" onclick="confirmLeaveRoom()">🏠 Home</button></div>
      </div>
      <div id="scoreboardArea" style="margin-top:12px;"></div>
    </div>

    <div id="lobbyPhase" class="card hidden">
      <h3>⏳ Waiting for Players (Up to 10)</h3>
      <p style="font-size:13px;color:var(--muted);">Share the room code or invite link. Host starts when everyone is in.</p>
      <button id="startMatchBtn" class="btn btn-green hidden" type="button" onclick="startMatch()">🔥 Start Match Now</button>
    </div>

    <div id="askingPhase" class="card hidden">
      <div id="askerControls" class="hidden">
        <h3 id="askerTitle">✍️ Set Your Question & Secret Answer</h3>
        <div class="row" style="margin-bottom:6px;"><select id="livePackSelect" onchange="syncLivePack()"><option value="">-- Select Pack --</option></select><button class="btn btn-gold btn-sm" type="button" onclick="autoPickNextQuestion()">🎲 Auto-Next</button></div>
        <div class="row" style="margin-bottom:6px;"><select id="qbQuickSelect"><option value="">-- Or Pick Specific Question --</option></select><button class="btn btn-dark btn-sm" type="button" onclick="pickFromQB()">Load</button></div>
        <label>Question</label>
        <input id="liveQuestionInput" placeholder="Type your question...">
        <label>Secret Answer</label>
        <div class="row"><input id="liveAnswerInput" placeholder="Type secret answer"><button class="btn btn-gold btn-sm" type="button" onclick="suggestAnswer('liveQuestionInput','liveAnswerInput','liveAiStatus')">✨ Suggest</button></div>
        <div id="liveAiStatus" style="font-size:12px;color:var(--accent);margin-top:4px;"></div>
        <button class="btn btn-primary" type="button" onclick="sendQuestion()">📤 Send Question to Players</button>
      </div>
      <div id="waitingAskerBox" class="hidden"><h3>⏳ Waiting for Question...</h3><p style="color:var(--muted);font-size:14px;">The Setter/Umpire is typing the question for this round.</p></div>
    </div>

    <div id="answeringPhase" class="card hidden">
      <div class="timer-bar" id="countdownDisplay">⏱ 30s</div>
      <div style="font-size:18px;font-weight:800;margin-bottom:8px;" id="activeQuestionText"></div>
      <div class="hint-box" id="activeHintText"></div>
      <div id="guesserInputBox"><label>Your Guess</label><input id="playerGuessInput" placeholder="Type your answer quickly..."><button class="btn btn-green" type="button" onclick="submitGuess()">✅ Submit Answer</button></div>
      <div id="submittedWaitBox" class="hidden"><p style="color:var(--green);font-weight:700;">✔ Answer submitted! Waiting for remaining players...</p></div>
    </div>

    <div id="reviewPhase" class="card hidden">
      <h3>📊 Round Results</h3>
      <div style="background:#0f172a;padding:10px;border-radius:10px;margin-bottom:10px;"><div style="font-size:12px;color:var(--muted);">Correct Answer:</div><div style="font-size:18px;font-weight:900;color:var(--green);" id="revealAnswerText"></div></div>
      <div id="submissionsList"></div>
      <div id="contestArea" class="hidden" style="margin-top:10px;">
        <button id="contestBtn" class="btn btn-red hidden" type="button" onclick="contestRuling()">⚖️ Contest Ruling (I Was Right!)</button>
        <div id="setterApprovalBox" class="hidden" style="background:#1e293b;padding:12px;border-radius:12px;margin-top:8px;">
          <div style="font-weight:800;color:var(--gold);margin-bottom:8px;">⚖️ Guesser Contested! Was their answer right?</div>
          <div class="row"><button class="btn btn-green btn-sm" type="button" onclick="resolveContest(true)">✅ Accept Guesser (+5 Pts)</button><button class="btn btn-red btn-sm" type="button" onclick="resolveContest(false)">❌ Reject (Setter Keeps +5)</button></div>
        </div>
      </div>
      <button id="nextRoundBtn" class="btn btn-primary hidden" type="button" onclick="nextRound()">➡️ Next Round</button>
    </div>

    <div id="gameoverPhase" class="card hidden">
      <div id="mpVictoryPoster" class="victory-poster"></div>
      <div id="finalPodium"></div>
      <button class="btn btn-primary" type="button" onclick="finishAndGoHome()">🏠 Back to Home</button>
    </div>
  </div>

  <div id="botView" class="hidden">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span class="badge" id="botRoundBadge">Round 1/5</span>
        <span class="badge" id="botDiffBadge" style="color:var(--gold);">🤖 PRO BOT</span>
        <button class="pill" type="button" style="border-color:var(--red);color:#fca5a5;" onclick="exitBotMatch()">🏠 Home</button>
      </div>
      <div class="row" style="margin-top:12px;">
        <div class="player-item"><b>🧑 You</b><span id="botPlayerScore" style="color:var(--green);font-weight:900;">0 pts</span></div>
        <div class="player-item"><b>🤖 Sage Bot</b><span id="botAiScore" style="color:var(--gold);font-weight:900;">0 pts</span></div>
      </div>
    </div>

    <div id="botAnsweringBox" class="card hidden">
      <div class="timer-bar" id="botTimerBar">⏱ 30s</div>
      <div style="font-size:18px;font-weight:800;margin-bottom:8px;" id="botQuestionText"></div>
      <div class="hint-box" id="botHintText"></div>
      <label>Your Answer</label>
      <input id="botUserGuessInput" placeholder="Type your answer before time runs out...">
      <button class="btn btn-green" type="button" onclick="submitBotUserGuess()">✅ Submit Answer</button>
    </div>

    <div id="botAskingBox" class="card hidden">
      <h3>✍️ Your Turn to Challenge Sage Bot!</h3>
      <div class="row" style="margin-bottom:6px;">
        <button class="btn btn-gold btn-sm" type="button" onclick="botAutoFillQuestion()">🎲 Auto-Pick From Pack</button>
      </div>
      <label>Question for Sage Bot</label>
      <input id="botCustomQInput" placeholder="Type a question or tap Auto-Pick">
      <label>Secret Answer</label>
      <div class="row">
        <input id="botCustomAInput" placeholder="Type secret answer">
        <button class="btn btn-gold btn-sm" type="button" onclick="suggestAnswer('botCustomQInput','botCustomAInput','botAiSuggestStatus')">✨ Suggest</button>
      </div>
      <div id="botAiSuggestStatus" style="font-size:12px;color:var(--accent);margin-top:4px;"></div>
      <button class="btn btn-primary" type="button" onclick="sendQuestionToBot()">📤 Challenge Sage Bot</button>
    </div>

    <div id="botThinkingBox" class="card hidden" style="text-align:center;">
      <h3 style="color:var(--gold);">🤖 Sage Bot is thinking...</h3>
      <p id="botThinkingHint" style="color:var(--muted);font-size:13px;"></p>
    </div>

    <div id="botReviewBox" class="card hidden">
      <h3>📊 Round Summary</h3>
      <div id="botResultBanner" style="font-size:16px;font-weight:800;margin-bottom:8px;"></div>
      <div style="background:#0f172a;padding:10px;border-radius:10px;margin-bottom:10px;">
        <div style="font-size:12px;color:var(--muted);">Secret Answer:</div>
        <div style="font-size:18px;font-weight:900;color:var(--green);" id="botRevealAnswer"></div>
      </div>
      <button id="botContestBtn" class="btn btn-red hidden" type="button" onclick="contestBotRuling()">⚖️ Contest Ruling (My Answer Was Right!)</button>
      <button class="btn btn-primary" type="button" onclick="nextBotRound()">➡️ Next Round</button>
    </div>

    <div id="botGameoverBox" class="card hidden">
      <div id="botVictoryPoster" class="victory-poster"></div>
      <div class="row">
        <button class="btn btn-gold" type="button" onclick="startBotMatch()">🔁 Rematch</button>
        <button class="btn btn-primary" type="button" onclick="exitBotMatch(true)">🏠 Back to Home</button>
      </div>
    </div>
  </div>
</div>

<div id="howToPlayModal" class="modal-bg hidden" onclick="if(event.target===this)this.classList.add('hidden')">
  <div class="modal-box">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h2 style="color:var(--gold);">📖 How to Play Double Sage</h2>
      <button class="pill" type="button" onclick="document.getElementById('howToPlayModal').classList.add('hidden')">✕</button>
    </div>
    <p style="font-size:14px;line-height:1.5;"><b>1. Standard Mode (Setter vs. Guesser):</b> Players take turns setting a secret question & answer. You get a smart hint showing word count, letter count, and digits (only when numbers exist). Match the answer before time runs out for <b>+5 pts</b>; miss and the Setter gets <b>+5 pts</b>. Think you were judged unfairly? Tap <b>⚖️ Contest</b> for Setter review!</p>
    <p style="font-size:14px;line-height:1.5;"><b>2. Simultaneous Umpire Mode (1–10 Players):</b> The Umpire is the organizer (<b>0 points</b>) who sets total rounds and asks <b>all players the exact same question at once</b>. Everyone who gets it right earns <b>+5 pts</b> with their speed recorded; if nobody gets it, <b>0 points</b> are awarded.</p>
    <p style="font-size:14px;line-height:1.5;"><b>3. 🤖 Sage Bot & Pro QB Studio:</b> Battle Sage Bot anytime using 300 built-in questions, import Excel/CSV sheets, or unlock Pro Packs in <b>📚 My QBs</b>!</p>
  </div>
</div>

<div id="qbModal" class="modal-bg hidden" onclick="if(event.target===this)this.classList.add('hidden')">
  <div class="modal-box">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <h2 style="color:var(--accent);margin:0;">📚 My QBs — Pro Pack Studio</h2>
      <button class="pill" type="button" onclick="document.getElementById('qbModal').classList.add('hidden')">✕</button>
    </div>

    <label>Active Question Pack</label>
    <div class="row">
      <select id="activePackSelect" onchange="switchActivePack(this.value)"></select>
      <button class="btn btn-primary btn-sm" type="button" onclick="createNewPack()">➕ New Pack</button>
      <button class="btn btn-red btn-sm" type="button" onclick="deleteActivePack()">🗑</button>
    </div>

    <label>Add Question to Current Pack</label>
    <input id="qbQInput" placeholder="Enter question">
    <div class="row" style="margin-top:6px;">
      <input id="qbAInput" placeholder="Enter answer">
      <button class="btn btn-gold btn-sm" type="button" onclick="suggestAnswer('qbQInput','qbAInput','qbAiStatus')">✨ Suggest</button>
    </div>
    <div id="qbAiStatus" style="font-size:12px;color:var(--accent);margin-top:4px;"></div>
    <button class="btn btn-primary btn-sm" type="button" style="margin-top:8px;" onclick="addQBItem()">➕ Save Question</button>

    <label>📊 Import Excel (.xlsx) or CSV (.csv) into Current Pack</label>
    <div class="row" style="margin-top:4px;">
      <label class="btn btn-primary btn-sm" style="text-align:center;margin:0;cursor:pointer;">
        📂 Upload Excel / CSV
        <input type="file" id="qbFileImport" accept=".csv,.xlsx,.xls" style="display:none" onchange="importQBSpreadsheet(this)">
      </label>
      <button class="btn btn-dark btn-sm" type="button" onclick="downloadSampleCSV()">📄 Sample CSV</button>
    </div>
    <div id="importStatusMsg" style="font-size:12px;color:var(--green);margin-top:4px;"></div>

    <label>🎟️ Unlock Pro QB Pack (NAIJA2026, FOOTYPRO, PARTYVIP, or DSPACK:...)</label>
    <div class="row">
      <input id="packCodeInput" placeholder="Paste pack code here">
      <button class="btn btn-green btn-sm" type="button" onclick="redeemPack()">Unlock</button>
    </div>

    <div id="exportSectionBox" style="margin-top:10px;background:#0b1120;padding:10px;border-radius:10px;border:1px solid #1e293b;">
      <label style="margin-top:0;display:flex;align-items:center;gap:6px;cursor:pointer;">
        <input type="checkbox" id="lockPackCheckbox" style="width:auto;">
        <span>🔒 Lock Pack from Buyer Re-Export (Commercial Protection)</span>
      </label>
      <button class="btn btn-gold btn-sm" type="button" style="margin-top:6px;" onclick="exportSellablePack()">📤 Export Sellable DSPACK Code</button>
      <textarea id="exportedPackBox" class="hidden" rows="2" style="margin-top:6px;font-size:11px;" readonly></textarea>
    </div>
    <div id="lockedPackNotice" class="hidden" style="margin-top:10px;font-size:12px;color:var(--gold);background:#1e293b;padding:8px 10px;border-radius:8px;">
      🔒 Commercial Pro Pack — Licensed for gameplay (Re-export disabled by creator).
    </div>

    <div class="row" style="margin-top:12px;">
      <input id="qbSearchInput" placeholder="🔍 Search questions in this pack..." oninput="renderQB()">
      <button class="btn btn-dark btn-sm" type="button" onclick="clearCurrentPack()">🧹 Clear Pack</button>
    </div>

    <div id="qbListContainer" style="margin-top:10px;"></div>
  </div>
</div>

<script src="/game.js?v=3" defer></script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)




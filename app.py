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


def find_asset_file(requested_name):
    clean_req = os.path.basename(requested_name).lower()
    stem, ext = os.path.splitext(clean_req)
    img_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    aud_exts = ('.mp3', '.wav', '.ogg', '.m4a')

    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'venv', '.venv')]
        for f in files:
            fl = f.lower()
            f_stem, f_ext = os.path.splitext(fl)
            if fl == clean_req:
                return root, f
            if f_stem == stem:
                if ext in img_exts and f_ext in img_exts:
                    return root, f
                if ext in aud_exts and f_ext in aud_exts:
                    return root, f
    return None, None


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/media-debug')
def media_debug():
    found = {}
    for target in ['double_sage_icon.jpg', 'double_sage_battle.jpg', 'double_sage_banner.jpg', 'double_sage_tournament.jpg', 'theme.mp3']:
        folder, fname = find_asset_file(target)
        found[target] = os.path.join(folder, fname) if folder else None
    return jsonify({'detected_assets': found})


@app.route('/<path:filename>')
def serve_files(filename):
    if filename.endswith('.py'):
        return jsonify({'error': 'Forbidden'}), 403
    if os.path.exists(os.path.join('.', filename)) and os.path.isfile(os.path.join('.', filename)):
        return send_from_directory('.', filename)
    folder, real_name = find_asset_file(filename)
    if folder and real_name:
        return send_from_directory(folder, real_name)
    return jsonify({'error': 'Not found'}), 404


@app.route('/media/<path:filename>')
def serve_media(filename):
    folder, real_name = find_asset_file(filename)
    if folder and real_name:
        return send_from_directory(folder, real_name)
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
<script src="/packs.js" defer></script>

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
    padding: 5px 10px; border-radius: 999px; font-size: 12px; cursor: pointer; font-weight: 600;
  }
  .pill:active { transform: scale(0.97); }
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
  .btn-sm { width: auto; padding: 7px 12px; font-size: 12px; margin-top: 0; border-radius: 8px; }
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
    position: fixed; inset: 0; background: #050811; z-index: 99999;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 20px; text-align: center; touch-action: manipulation;
  }
  #introSlideImg {
    max-width: 92%; max-height: 58vh; border-radius: 18px;
    box-shadow: 0 12px 40px rgba(56,189,248,0.35); object-fit: contain;
    pointer-events: none;
  }
  #introFallbackCrest {
    width: 140px; height: 140px; border-radius: 50%;
    background: radial-gradient(circle, #38bdf8 0%, #0f172a 75%);
    border: 3px solid var(--gold); display: flex; align-items: center; justify-content: center;
    font-size: 56px; box-shadow: 0 0 35px rgba(250,204,21,0.45); pointer-events: none;
  }
  #introTitle { margin-top: 14px; font-size: 22px; font-weight: 900; color: var(--gold); pointer-events: none; }
  #skipIntroBtn {
    position: fixed; top: 16px; right: 16px; z-index: 2147483647;
    pointer-events: auto; cursor: pointer; background: var(--gold); color: #000;
    border: none; padding: 12px 20px; border-radius: 999px; font-weight: 900; font-size: 15px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.6); touch-action: manipulation;
  }
  .modal-bg {
    position: fixed; inset: 0; background: rgba(0,0,0,0.82); z-index: 10000;
    display: flex; align-items: center; justify-content: center; padding: 16px;
  }
  .modal-box {
    background: var(--card); border: 1px solid #334155; border-radius: 16px;
    max-width: 520px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 18px;
  }
    .victory-poster {
    background: radial-gradient(circle at top, #1e293b 0%, #090d16 85%);
    border: 2px solid var(--gold); border-radius: 18px; padding: 20px 16px;
    text-align: center; box-shadow: 0 0 30px rgba(250, 204, 21, 0.25);
    margin-bottom: 14px; position: relative; overflow: hidden;
  }
  .victory-trophy { font-size: 52px; line-height: 1.1; margin-bottom: 6px; }
  .victory-title { font-size: 13px; font-weight: 800; letter-spacing: 2px; color: var(--accent); text-transform: uppercase; }
  .victory-winner { font-size: 28px; font-weight: 900; color: var(--gold); margin: 6px 0; text-shadow: 0 2px 12px rgba(250,204,21,0.4); }
  .victory-score-pill {
    display: inline-block; background: rgba(34, 197, 94, 0.15); border: 1px solid var(--green);
    color: var(--green); font-weight: 900; font-size: 16px; padding: 6px 16px; border-radius: 999px; margin: 6px 0 12px;
  }
  .victory-share-box {
    background: #0b1120; border: 1px solid #334155; border-radius: 12px; padding: 10px; text-align: left; margin-top: 10px;
  }

</style>
</head>
<body>

<div id="introOverlay" onclick="dismissIntroNow(event)">
  <button id="skipIntroBtn" type="button" style="position:fixed;top:16px;right:16px;z-index:2147483647;background:#facc15;color:#000;border:none;padding:10px 18px;border-radius:999px;font-weight:900;cursor:pointer;" onclick="this.parentElement.style.display='none';">Skip Intro ⏭</button>
  <img id="introSlideImg" src="/double_sage_icon.jpg" alt="Double Sage" onerror="this.style.display='none';document.getElementById('introFallbackCrest').classList.remove('hidden');">
  <div id="introFallbackCrest" class="hidden">⚔️</div>
  <div id="introTitle">DOUBLE SAGE — BATTLE OF MINDS</div>
  <div style="color:#94a3b8;font-size:13px;margin-top:6px;pointer-events:none;">Tap anywhere or press Skip Intro to enter</div>
</div>

<audio id="bgMusic" src="/theme.mp3" loop preload="none"></audio>

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
   <div id="rejoinBanner" class="card hidden" style="border:1px solid var(--green);background:#0d1f17;">
   <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
     <div>
       <div style="font-weight:900;color:var(--green);">🔄 Active Match Found!</div>
       <div id="rejoinBannerText" style="font-size:12px;color:#cbd5e1;">Room ----</div>
     </div>
     <div style="display:flex;gap:6px;">
       <button class="btn btn-green btn-sm" type="button" onclick="rejoinSavedRoom()">Rejoin Now</button>
       <button class="btn btn-dark btn-sm" type="button" onclick="clearSavedRoom()">Dismiss</button>
     </div>
   </div>
 </div>

      <div class="card" style="border:1px solid var(--accent);">
      <h2 style="color:var(--accent);">🤖 Play vs. Sage Bot (Instant Solo Duel)</h2>
      <p style="font-size:13px;color:var(--muted);margin:0 0 8px;">No opponent online yet? Battle Sage Bot using any pack right now!</p>
      <div class="row">
        <div>
          <label>Select Pack</label>
          <select id="botPackSelect"></select>
        </div>
        <div>
          <label>Bot Difficulty</label>
          <select id="botDiffSelect">
            <option value="rookie">Rookie (Casual)</option>
            <option value="pro" selected>Pro (Balanced)</option>
            <option value="grandmaster">Grandmaster (Fast)</option>
          </select>
        </div>
      </div>
      <button class="btn btn-primary" type="button" onclick="startBotMatch()">🤖 Start Solo Duel vs. Sage Bot</button>
    </div>

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
             <div style="display:flex;gap:6px;">
       <button class="pill" type="button" onclick="copyInviteLink()">📋 Invite</button>
       <button class="pill" type="button" style="border-color:var(--red);color:#fca5a5;" onclick="confirmLeaveRoom()">🏠 Home</button>
     </div>
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
          <select id="livePackSelect" onchange="syncLivePack()"><option value="">-- Select Pack --</option></select>
          <button class="btn btn-gold btn-sm" type="button" onclick="autoPickNextQuestion()">🎲 Auto-Next</button>
        </div>
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
   <div id="mpVictoryPoster" class="victory-poster"></div>
   <div id="finalPodium"></div>
   <button class="btn btn-primary" type="button" onclick="finishAndGoHome()">🏠 Back to Home</button>
 </div>

  </div>
</div>
  <div id="botView" class="hidden">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span class="badge" id="botRoundBadge">Round 1/5</span>
        <span class="badge" id="botDiffBadge" style="color:var(--gold);">🤖 PRO BOT</span>
        <button class="pill" type="button" onclick="exitBotMatch()">✕ Exit</button>
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


<script>
const INTRO_SLIDES = [
  { img: '/double_sage_icon.jpg', title: 'DOUBLE SAGE — BATTLE OF MINDS' },
  { img: '/double_sage_battle.jpg', title: 'OUTSMART RIVALS & BEAT THE CLOCK' },
  { img: '/double_sage_banner.jpg', title: 'SIMULTANEOUS UMPIRE & DUEL MODES' },
  { img: '/double_sage_tournament.jpg', title: 'CLIMB THE LEADERBOARD TO VICTORY' }
];
let slideIdx = 0;
const slideInterval = setInterval(function() {
  const ov = document.getElementById('introOverlay');
  if (!ov || ov.style.display === 'none') { clearInterval(slideInterval); return; }
  slideIdx++;
  if (slideIdx >= INTRO_SLIDES.length) {
    ov.style.display = 'none';
    clearInterval(slideInterval);
    startThemeAudio();
    return;
  }
  const imgEl = document.getElementById('introSlideImg');
  const titleEl = document.getElementById('introTitle');
  if (imgEl) { imgEl.style.display = 'inline-block'; imgEl.src = INTRO_SLIDES[slideIdx].img; }
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
    bg.play().catch(function() { startSynthFallback(); });
  }
}

function startSynthFallback() {
  if (synthTimer || !musicEnabled) return;
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    audioCtx = audioCtx || new AudioContextClass();
    const notes = [261.63, 329.63, 392.00, 523.25, 392.00, 329.63];
    let step = 0;
    synthTimer = setInterval(function() {
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
  if (musicEnabled) bg.play().catch(function() {});
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
  if (musicEnabled) bg.play().catch(function() { startSynthFallback(); });
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
  const personalWords = ['my ', ' me', 'i ', 'mine', 'our ', 'we ', 'nickname', 'favorite', 'favourite', 'birthday', 'crush'];
  for (let i = 0; i < personalWords.length; i++) {
    if (lower.indexOf(personalWords[i]) !== -1) {
      statusEl.textContent = '🔒 Personal question detected — enter your own secret answer!';
      return;
    }
  }

  const cleaned = lower.replace('what is', '').replace('calculate', '').replace('solve', '').replace('?', '').replace('=', '').replace(/x/g, '*').trim();
  if (/^[0-9+\-*/().\s]+$/.test(cleaned) && /[0-9]/.test(cleaned)) {
    try {
      const val = Function('return (' + cleaned + ')')();
      if (typeof val === 'number' && isFinite(val)) {
        ansEl.value = String(Number.isInteger(val) ? val : Math.round(val * 100) / 100);
        statusEl.textContent = '✅ Solved math expression!';
        return;
      }
    } catch (e) {}
  }

  for (const k in FACT_BANK) {
    if (lower.indexOf(k) !== -1) {
      ansEl.value = FACT_BANK[k];
      statusEl.textContent = '✅ Suggested factual answer!';
      return;
    }
  }

  statusEl.textContent = '🔍 Searching factual answer...';
  try {
    const query = qRaw.replace(/who is|what is|where is|when was|who was|\?/gi, '').trim();
    const res = await fetch('https://wikipedia.org' + encodeURIComponent(query) + '&format=json&origin=*');
    const data = await res.json();
    const hits = (data.query && data.query.search) || [];
    if (hits.length > 0) {
      let best = hits[0].title;
      if (best.toLowerCase().indexOf(query.toLowerCase()) !== -1 && hits.length > 1) {
        best = hits[1].title;
      }
      ansEl.value = best.replace(/\(.*?\)/g, '').trim();
      statusEl.textContent = '✅ Suggested from knowledge base!';
    } else {
      statusEl.textContent = 'No exact match — type your answer manually.';
    }
  } catch (e) {
    statusEl.textContent = 'Offline — type your answer manually.';
  }
}
const PRO_PACKS = {
  'NAIJA2026': {
    title: 'Naija 2026 Pro Pack',
    locked: true,
    items: [
      { q: 'Who is the president of Nigeria?', a: 'Bola Ahmed Tinubu' },
      { q: 'What is the capital city of Nigeria?', a: 'Abuja' },
      { q: 'What year did Nigeria gain independence?', a: '1960' },
      { q: 'What is the largest city by population in Nigeria?', a: 'Lagos' }
    ]
  },
  'FOOTYPRO': {
    title: 'Football Legends Pro Pack',
    locked: true,
    items: [
      { q: 'Which country won the 2022 FIFA World Cup?', a: 'Argentina' },
      { q: 'Which club has won the most UEFA Champions League titles?', a: 'Real Madrid' },
      { q: 'How many players are on the pitch for one football team?', a: '11' }
    ]
  },
  'PARTYVIP': {
    title: 'Party & Speed Math VIP',
    locked: true,
    items: [
      { q: 'What is 25 * 4?', a: '100' },
      { q: 'How many days are in a leap year?', a: '366' },
      { q: 'Which planet is known as the Red Planet?', a: 'Mars' }
    ]
  }
};

let usedQuestionKeys = {};

function getPackStore() {
  try {
    const raw = JSON.parse(localStorage.getItem('ds_qb_packs_v2') || 'null');
    if (raw && raw.packs && Object.keys(raw.packs).length) return raw;
  } catch (e) {}
  // Migrate any legacy flat questions into "My Custom Pack"
  let legacy = [];
  try { legacy = JSON.parse(localStorage.getItem('ds_my_qb') || '[]'); } catch (e) {}
  const store = {
    activeId: 'custom_default',
    packs: {
      custom_default: { title: 'My Custom Pack', locked: false, items: Array.isArray(legacy) ? legacy : [] }
    }
  };
  savePackStore(store);
  return store;
}

function savePackStore(store) {
  localStorage.setItem('ds_qb_packs_v2', JSON.stringify(store));
  renderQB();
}

function openQBModal() {
  renderQB();
  document.getElementById('qbModal').classList.remove('hidden');
}

function switchActivePack(packId) {
  const store = getPackStore();
  if (store.packs[packId]) {
    store.activeId = packId;
    savePackStore(store);
  }
}

function createNewPack() {
  const name = prompt('Enter new pack name (e.g. Couples Night, JAMB Drill):');
  if (!name || !name.trim()) return;
  const store = getPackStore();
  const id = 'pack_' + Date.now();
  store.packs[id] = { title: name.trim().slice(0, 32), locked: false, items: [] };
  store.activeId = id;
  savePackStore(store);
}

function deleteActivePack() {
  const store = getPackStore();
  const ids = Object.keys(store.packs);
  if (ids.length <= 1) { alert('You must keep at least one pack.'); return; }
  const current = store.packs[store.activeId];
  if (!confirm('Delete "' + current.title + '" and all its questions?')) return;
  delete store.packs[store.activeId];
  store.activeId = Object.keys(store.packs)[0];
  savePackStore(store);
}

function clearCurrentPack() {
  const store = getPackStore();
  const pack = store.packs[store.activeId];
  if (!pack || !pack.items.length) return;
  if (!confirm('Clear all ' + pack.items.length + ' questions in "' + pack.title + '"?')) return;
  pack.items = [];
  savePackStore(store);
}

function addQBItem() {
  const q = document.getElementById('qbQInput').value.trim();
  const a = document.getElementById('qbAInput').value.trim();
  if (!q || !a) return;
  const store = getPackStore();
  store.packs[store.activeId].items.push({ q: q, a: a });
  savePackStore(store);
  document.getElementById('qbQInput').value = '';
  document.getElementById('qbAInput').value = '';
}

function editQBItem(idx) {
  const store = getPackStore();
  const item = store.packs[store.activeId].items[idx];
  if (!item) return;
  const newQ = prompt('Edit Question:', item.q);
  if (newQ === null) return;
  const newA = prompt('Edit Secret Answer:', item.a);
  if (newA === null) return;
  if (newQ.trim() && newA.trim()) {
    store.packs[store.activeId].items[idx] = { q: newQ.trim(), a: newA.trim() };
    savePackStore(store);
  }
}

function deleteQBItem(idx) {
  const store = getPackStore();
  store.packs[store.activeId].items.splice(idx, 1);
  savePackStore(store);
}

function downloadSampleCSV() {
  const csv = 'Question,Answer\n"Who is the president of Nigeria?","Bola Ahmed Tinubu"\n"What is 25 * 4?","100"\n"What is the capital of Ogun State?","Abeokuta"\n';
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'double_sage_template.csv';
  a.click();
}

function importQBSpreadsheet(inp) {
  if (!inp.files || !inp.files[0]) return;
  const file = inp.files[0];
  const statusEl = document.getElementById('importStatusMsg');
  const reader = new FileReader();

  reader.onload = function(e) {
    try {
      let rows = [];
      if (typeof XLSX !== 'undefined') {
        const wb = XLSX.read(new Uint8Array(e.target.result), { type: 'array' });
        const sheet = wb.Sheets[wb.SheetNames[0]];
        rows = XLSX.utils.sheet_to_json(sheet, { header: 1 });
      } else {
        const text = new TextDecoder().decode(e.target.result);
        rows = text.split(/\r?\n/).map(function(line) { return line.split(','); });
      }

      const store = getPackStore();
      const pack = store.packs[store.activeId];
      let added = 0;
      rows.forEach(function(row, idx) {
        if (!row || row.length < 2) return;
        const q = String(row[0] || '').trim();
        const a = String(row[1] || '').trim();
        if (!q || !a) return;
        if (idx === 0 && (q.toLowerCase() === 'question' || q.toLowerCase() === 'q') && (a.toLowerCase() === 'answer' || a.toLowerCase() === 'a')) {
          return;
        }
        pack.items.push({ q: q, a: a });
        added++;
      });

      savePackStore(store);
      inp.value = '';
      if (statusEl) statusEl.textContent = '✅ Imported ' + added + ' questions into "' + pack.title + '"!';
    } catch (err) {
      if (statusEl) statusEl.textContent = '❌ Could not read file. Use a 2-column CSV or Excel sheet.';
    }
  };
  reader.readAsArrayBuffer(file);
}

function redeemPack() {
  const raw = document.getElementById('packCodeInput').value.trim();
  if (!raw) return;
  const upper = raw.toUpperCase();
  const store = getPackStore();

  if (PRO_PACKS[upper]) {
    const p = PRO_PACKS[upper];
    const id = 'pro_' + upper.toLowerCase();
    store.packs[id] = { title: p.title, locked: true, items: p.items.slice() };
    store.activeId = id;
    savePackStore(store);
    alert('Unlocked "' + p.title + '" (' + p.items.length + ' questions)!');
    document.getElementById('packCodeInput').value = '';
    return;
  }

  if (raw.indexOf('DSPACK:') === 0) {
    try {
      const decoded = JSON.parse(atob(raw.slice(7)));
      // Supports both v2 {title, locked, items} and legacy [{q, a}] codes
      if (decoded && Array.isArray(decoded.items)) {
        const id = 'pack_' + Date.now();
        store.packs[id] = {
          title: String(decoded.title || 'Unlocked Pro Pack').slice(0, 32),
          locked: Boolean(decoded.locked),
          items: decoded.items.filter(function(x) { return x && x.q && x.a; })
        };
        store.activeId = id;
        savePackStore(store);
        alert('Unlocked "' + store.packs[id].title + '" (' + store.packs[id].items.length + ' questions)!');
        document.getElementById('packCodeInput').value = '';
        return;
      } else if (Array.isArray(decoded)) {
        const id = 'pack_' + Date.now();
        store.packs[id] = {
          title: 'Unlocked Pack #' + Object.keys(store.packs).length,
          locked: false,
          items: decoded.filter(function(x) { return x && x.q && x.a; })
        };
        store.activeId = id;
        savePackStore(store);
        alert('Imported ' + store.packs[id].items.length + ' questions!');
        document.getElementById('packCodeInput').value = '';
        return;
      }
    } catch (e) {}
  }
  alert('Invalid pack code.');
}

function exportSellablePack() {
  const store = getPackStore();
  const pack = store.packs[store.activeId];
  if (pack.locked) { alert('This commercial pack is locked by its creator.'); return; }
  if (!pack.items.length) { alert('Add questions to "' + pack.title + '" first!'); return; }
  const lockIt = document.getElementById('lockPackCheckbox').checked;
  const payload = { title: pack.title, locked: lockIt, items: pack.items };
  const code = 'DSPACK:' + btoa(JSON.stringify(payload));
  const box = document.getElementById('exportedPackBox');
  box.value = code;
  box.classList.remove('hidden');
  box.select();
}

function renderQB() {
  const store = getPackStore();
  const pack = store.packs[store.activeId] || store.packs[Object.keys(store.packs)[0]];
  const activeSel = document.getElementById('activePackSelect');
  const livePackSel = document.getElementById('livePackSelect');
  const qSel = document.getElementById('qbQuickSelect');
  const container = document.getElementById('qbListContainer');
  const searchVal = (document.getElementById('qbSearchInput')?.value || '').toLowerCase().trim();

  if (activeSel) {
    activeSel.innerHTML = '';
    Object.keys(store.packs).forEach(function(pid) {
      const p = store.packs[pid];
      const opt = document.createElement('option');
      opt.value = pid;
      opt.textContent = (p.locked ? '🔒 ' : '📁 ') + p.title + ' (' + p.items.length + ')';
      if (pid === store.activeId) opt.selected = true;
      activeSel.appendChild(opt);
    });
  }

  if (livePackSel) {
    const prev = livePackSel.value || store.activeId;
    livePackSel.innerHTML = '';
    Object.keys(store.packs).forEach(function(pid) {
      const p = store.packs[pid];
      const opt = document.createElement('option');
      opt.value = pid;
      opt.textContent = p.title + ' (' + p.items.length + ')';
      if (pid === prev) opt.selected = true;
      livePackSel.appendChild(opt);
    });
  }
const botPackSel = document.getElementById('botPackSelect');
if (botPackSel) {
  botPackSel.innerHTML = '';
  Object.keys(store.packs).forEach(function(pid) {
    const p = store.packs[pid];
    if (p.items && p.items.length > 0) {
      const opt = document.createElement('option');
      opt.value = pid;
      opt.textContent = p.title + ' (' + p.items.length + ' Qs)';
      botPackSel.appendChild(opt);
    }
  });
  Object.keys(PRO_PACKS).forEach(function(code) {
    if (!store.packs['pro_' + code.toLowerCase()]) {
      const opt = document.createElement('option');
      opt.value = 'builtin_' + code;
      opt.textContent = '⭐ ' + PRO_PACKS[code].title + ' (' + PRO_PACKS[code].items.length + ' Qs)';
      botPackSel.appendChild(opt);
    }
  });
}


  const exportBox = document.getElementById('exportSectionBox');
  const lockedNotice = document.getElementById('lockedPackNotice');
  if (exportBox && lockedNotice) {
    exportBox.classList.toggle('hidden', Boolean(pack.locked));
    lockedNotice.classList.toggle('hidden', !pack.locked);
  }

  const livePid = (livePackSel && livePackSel.value) || store.activeId;
  const livePack = store.packs[livePid] || pack;
  if (qSel) {
    qSel.innerHTML = '<option value="">-- Pick Specific Question (' + livePack.items.length + ') --</option>';
    livePack.items.forEach(function(item, i) {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = item.q;
      qSel.appendChild(opt);
    });
  }

  if (!container) return;
  container.innerHTML = '';
  pack.items.forEach(function(item, i) {
    if (searchVal && item.q.toLowerCase().indexOf(searchVal) === -1 && item.a.toLowerCase().indexOf(searchVal) === -1) return;
    const row = document.createElement('div');
    row.className = 'player-item';
    row.innerHTML = '<div style="font-size:13px;padding-right:8px;"><b>' + escapeHtml(item.q) + '</b><br><span style="color:var(--green);">Ans: ' + escapeHtml(item.a) + '</span></div>' +
      '<div style="display:flex;gap:4px;"><button class="pill" type="button" onclick="editQBItem(' + i + ')">✏️</button><button class="pill" type="button" onclick="deleteQBItem(' + i + ')">🗑</button></div>';
    container.appendChild(row);
  });
}

function syncLivePack() {
  renderQB();
}

function pickFromQB() {
  const store = getPackStore();
  const livePid = document.getElementById('livePackSelect')?.value || store.activeId;
  const pack = store.packs[livePid];
  const idx = document.getElementById('qbQuickSelect').value;
  if (idx === '' || !pack) return;
  const item = pack.items[parseInt(idx, 10)];
  if (item) {
    document.getElementById('liveQuestionInput').value = item.q;
    document.getElementById('liveAnswerInput').value = item.a;
    usedQuestionKeys[livePid + ':' + idx] = true;
  }
}

function autoPickNextQuestion() {
  const store = getPackStore();
  const livePid = document.getElementById('livePackSelect')?.value || store.activeId;
  const pack = store.packs[livePid];
  if (!pack || !pack.items.length) {
    alert('This pack is empty! Add or unlock questions in My QBs first.');
    return;
  }
  let unplayed = [];
  pack.items.forEach(function(item, i) {
    if (!usedQuestionKeys[livePid + ':' + i]) unplayed.push(i);
  });
  if (!unplayed.length) {
    pack.items.forEach(function(_, i) { delete usedQuestionKeys[livePid + ':' + i]; });
    unplayed = pack.items.map(function(_, i) { return i; });
  }
  const pickIdx = unplayed[Math.floor(Math.random() * unplayed.length)];
  usedQuestionKeys[livePid + ':' + pickIdx] = true;
  const chosen = pack.items[pickIdx];
  document.getElementById('liveQuestionInput').value = chosen.q;
  document.getElementById('liveAnswerInput').value = chosen.a;
  const statusEl = document.getElementById('liveAiStatus');
  if (statusEl) statusEl.textContent = '🎲 Loaded unused question from "' + pack.title + '"!';
}

function saveCreatorUrl() {
const url = document.getElementById('creatorUrlInput').value.trim();
localStorage.setItem('ds_creator_url', url);
renderCreatorUrl();
}
function renderCreatorUrl() {
const url = localStorage.getItem('ds_creator_url') || '';
const box = document.getElementById('creatorLinkDisplay');
if (!box) return;
if (url) {
box.innerHTML = '🎟️ Buy Tournament Ticket / Support Creator';
} else {
box.innerHTML = '';
}
}
function openHowToPlay() {
document.getElementById('howToPlayModal').classList.remove('hidden');
}
function escapeHtml(str) {
return String(str || '').replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>').replace(/"/g, '"');
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
const res = await apiPost('/api/create', { name: name, mode: mode, rounds: rounds, timer: timer });
if (res.ok) enterRoom(res.room, res.player_id);
else alert(res.error || 'Failed to create room');
}
async function joinRoom() {
const name = document.getElementById('joinNameInput').value.trim() || 'Player';
const code = document.getElementById('joinCodeInput').value.trim().toUpperCase();
if (!code) { alert('Enter a 4-letter room code'); return; }
const res = await apiPost('/api/join', { name: name, code: code });
if (res.ok) enterRoom(res.room, res.player_id);
else alert(res.error || 'Could not join room');
}
function buildVictoryPosterHtml(winnerName, pointsText, subtitleText) {
  const defaultLink = localStorage.getItem('ds_custom_share_link') || location.origin;
  return '<div class="victory-trophy">🏆👑🏆</div>' +
    '<div class="victory-title">DOUBLE SAGE GRAND CHAMPION</div>' +
    '<div class="victory-winner">' + escapeHtml(winnerName) + '</div>' +
    '<div class="victory-score-pill">⚡ ' + escapeHtml(pointsText) + '</div>' +
    '<div style="font-size:12px;color:#cbd5e1;">' + escapeHtml(subtitleText) + '</div>' +
    '<div class="victory-share-box">' +
      '<label style="margin:0 0 4px;font-size:11px;color:var(--gold);">🔗 Editable Game Link (Tap to edit & share your victory):</label>' +
      '<div class="row">' +
        '<input id="victoryShareUrlInput" value="' + escapeHtml(defaultLink) + '" oninput="localStorage.setItem(\'ds_custom_share_link\', this.value)" style="font-size:12px;padding:7px 9px;">' +
        '<button class="btn btn-gold btn-sm" type="button" onclick="shareVictoryCard(\'' + escapeHtml(winnerName).replace(/'/g, '') + '\', \'' + escapeHtml(pointsText).replace(/'/g, '') + '\')">📤 Share</button>' +
      '</div>' +
    '</div>';
}

function shareVictoryCard(winnerName, pointsText) {
  const link = (document.getElementById('victoryShareUrlInput')?.value || location.origin).trim();
  const msg = '🏆 DOUBLE SAGE CHAMPION!\n👑 Winner: ' + winnerName + '\n⚡ Score: ' + pointsText + '\n\nThink you can beat me? Play Double Sage here:\n' + link;
  if (navigator.share) {
    navigator.share({ title: 'Double Sage Victory!', text: msg, url: link }).catch(function() {});
  } else {
    if (navigator.clipboard) navigator.clipboard.writeText(msg);
    alert('Victory card copied! Paste on WhatsApp or X to challenge friends:\n\n' + msg);
  }
}

function saveActiveRoomSession(code, pid) {
  localStorage.setItem('ds_active_room', code);
  localStorage.setItem('ds_active_pid', pid);
}

function clearSavedRoom() {
  localStorage.removeItem('ds_active_room');
  localStorage.removeItem('ds_active_pid');
  const b = document.getElementById('rejoinBanner');
  if (b) b.classList.add('hidden');
}

function confirmLeaveRoom() {
  const ok = confirm('Do you really want to give up?\n\nPress OK (YES) to return Home (you can still Rejoin while the room is active), or Cancel (NO) to stay in the match.');
  if (!ok) return;
  if (pollTimer) clearInterval(pollTimer);
  document.getElementById('roomView').classList.add('hidden');
  document.getElementById('homeView').classList.remove('hidden');
  checkSavedRoomBanner();
}

function finishAndGoHome() {
  clearSavedRoom();
  if (pollTimer) clearInterval(pollTimer);
  document.getElementById('roomView').classList.add('hidden');
  document.getElementById('homeView').classList.remove('hidden');
}

async function checkSavedRoomBanner() {
  const code = localStorage.getItem('ds_active_room');
  const pid = localStorage.getItem('ds_active_pid');
  const banner = document.getElementById('rejoinBanner');
  if (!code || !pid || !banner) return;
  try {
    const r = await fetch('/api/state/' + code);
    const data = await r.json();
    if (data.ok && data.room && data.room.phase !== 'gameover') {
      const stillIn = data.room.players.some(function(p) { return p.id === pid; });
      if (stillIn) {
        document.getElementById('rejoinBannerText').textContent = 'Room ' + code + ' • Round ' + data.room.current_round + '/' + data.room.total_rounds;
        banner.classList.remove('hidden');
        return;
      }
    }
  } catch (e) {}
  clearSavedRoom();
}

async function rejoinSavedRoom() {
  const code = localStorage.getItem('ds_active_room');
  const pid = localStorage.getItem('ds_active_pid');
  if (!code || !pid) return;
  try {
    const r = await fetch('/api/state/' + code);
    const data = await r.json();
    if (data.ok && data.room) {
      document.getElementById('rejoinBanner').classList.add('hidden');
      enterRoom(data.room, pid);
    } else {
      alert('That room has ended or expired.');
      clearSavedRoom();
    }
  } catch (e) {
    alert('Network error — check connection and tap Rejoin again.');
  }
}
function enterRoom(room, pid) {
currentCode = room.code;
myPlayerId = pid;
saveActiveRoomSession(room.code, pid);
document.getElementById('homeView').classList.add('hidden');
document.getElementById('roomView').classList.remove('hidden');
renderQB();
renderRoom(room);
if (pollTimer) clearInterval(pollTimer);
pollTimer = setInterval(async function() {
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
const res = await apiPost('/api/ask', { code: currentCode, question: question, answer: answer });
if (res.ok) {
document.getElementById('liveQuestionInput').value = '';
document.getElementById('liveAnswerInput').value = '';
renderRoom(res.room);
}
}
async function submitGuess() {
const guess = document.getElementById('playerGuessInput').value.trim();
const res = await apiPost('/api/guess', { code: currentCode, player_id: myPlayerId, guess: guess });
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
const me = room.players.find(function(p) { return p.id === myPlayerId; });
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
room.players.forEach(function(p) {
const div = document.createElement('div');
div.className = 'player-item';
const roleTag = p.is_umpire
? '🎙 Umpire (Organizer)'
: '' + p.score + ' pts (' + p.total_time + 's)';
const kickBtn = (isHost && p.id !== myPlayerId) ? ' Kick' : '';
div.innerHTML = '' + escapeHtml(p.name) + '' + (p.id === myPlayerId ? ' (You)' : '') + '' + roleTag + kickBtn + '';
sb.appendChild(div);
});
['lobbyPhase', 'askingPhase', 'answeringPhase', 'reviewPhase', 'gameoverPhase'].forEach(function(id) {
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
document.getElementById('submittedWaitBox').innerHTML = '⏳ Players are answering your question...';
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
subList.innerHTML = 'No answers submitted before time expired (0 pts awarded).';
} else {
subs.forEach(function(s) {
const badge = s.correct
? '✅ +5 pts (' + s.time + 's)'
: '❌ 0 pts (' + s.time + 's)';
subList.innerHTML += '' + escapeHtml(s.name) + ': ' + escapeHtml(s.guess) + '' + badge + '';
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
const ranked = room.players.filter(function(p) { return !p.is_umpire; }).sort(function(a, b) { return (b.score - a.score) || (a.total_time - b.total_time); });
 const ranked = room.players.filter(function(p) { return !p.is_umpire; }).sort(function(a, b) { return (b.score - a.score) || (a.total_time - b.total_time); });
 const champ = ranked;
 const poster = document.getElementById('mpVictoryPoster');
 if (poster && champ) {
   poster.innerHTML = buildVictoryPosterHtml(
     champ.name,
     champ.score + ' Points (' + champ.total_time + 's)',
     'Room ' + room.code + ' • ' + (room.mode === 'umpire' ? 'Umpire Arena' : 'Standard Duel')
   );
 }
 const pod = document.getElementById('finalPodium');
 pod.innerHTML = '';
 ranked.forEach(function(p, idx) {
   const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '#' + (idx + 1);
   pod.innerHTML += '<div class="player-item"><div><b>' + medal + ' ' + escapeHtml(p.name) + '</b></div><div><b style="color:var(--gold);">' + p.score + ' pts</b> (' + p.total_time + 's)</div></div>';
 });

}
}
// --- SAGE BOT SOLO DUEL ENGINE ---
let botState = null;
let botTimerInterval = null;

function computeSmartHint(ans) {
  const raw = String(ans || '').trim();
  const words = raw.split(/\s+/).filter(Boolean).length;
  let letters = 0, digits = 0;
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (/[a-zA-Z]/.test(ch)) letters++;
    else if (/[0-9]/.test(ch)) digits++;
  }
  const parts = [];
  if (letters > 0) {
    parts.push(words + (words === 1 ? ' word' : ' words'));
    parts.push(letters + (letters === 1 ? ' letter' : ' letters'));
  }
  if (digits > 0) {
    parts.push(digits + (digits === 1 ? ' digit' : ' digits'));
  }
  return parts.join(', ');
}

function normBotText(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ').trim();
}

function getBotPackItems(packVal) {
  if (packVal.indexOf('builtin_') === 0) {
    const code = packVal.replace('builtin_', '');
    return (PRO_PACKS[code] && PRO_PACKS[code].items) ? PRO_PACKS[code].items.slice() : [];
  }
  const store = getPackStore();
  return (store.packs[packVal] && store.packs[packVal].items) ? store.packs[packVal].items.slice() : [];
}

function startBotMatch() {
  const packVal = document.getElementById('botPackSelect').value;
  const diff = document.getElementById('botDiffSelect').value;
  const items = getBotPackItems(packVal);
  if (!items.length) { alert('Please select a pack with questions!'); return; }

  botState = {
    items: items,
    used: {},
    diff: diff,
    round: 1,
    totalRounds: Math.min(6, Math.max(4, items.length)),
    userScore: 0,
    botScore: 0,
    currentQ: '',
    currentA: '',
    lastUserMissed: false
  };

  document.getElementById('homeView').classList.add('hidden');
  document.getElementById('botView').classList.remove('hidden');
  document.getElementById('botDiffBadge').textContent = '🤖 ' + diff.toUpperCase() + ' BOT';
  updateBotScores();
  runBotTurn();
}

function exitBotMatch(skipConfirm) {
  if (!skipConfirm && botState) {
    const ok = confirm('Do you really want to give up?\n\nPress OK (YES) to quit to Home, or Cancel (NO) to keep playing.');
    if (!ok) return;
  }
  if (botTimerInterval) clearInterval(botTimerInterval);
  botState = null;
  document.getElementById('botView').classList.add('hidden');
  document.getElementById('homeView').classList.remove('hidden');
}



function updateBotScores() {
  if (!botState) return;
  document.getElementById('botRoundBadge').textContent = 'Round ' + botState.round + '/' + botState.totalRounds;
  document.getElementById('botPlayerScore').textContent = botState.userScore + ' pts';
  document.getElementById('botAiScore').textContent = botState.botScore + ' pts';
}

function hideAllBotBoxes() {
  ['botAnsweringBox', 'botAskingBox', 'botThinkingBox', 'botReviewBox', 'botGameoverBox'].forEach(function(id) {
    document.getElementById(id).classList.add('hidden');
  });
}

function pickUnusedBotItem() {
  const avail = [];
  botState.items.forEach(function(_, i) { if (!botState.used[i]) avail.push(i); });
  if (!avail.length) {
    botState.used = {};
    botState.items.forEach(function(_, i) { avail.push(i); });
  }
  const idx = avail[Math.floor(Math.random() * avail.length)];
  botState.used[idx] = true;
  return botState.items[idx];
}

function runBotTurn() {
  hideAllBotBoxes();
  updateBotScores();
  if (botState.round % 2 === 1) {
    // Odd round: Sage Bot asks the player
    const item = pickUnusedBotItem();
    botState.currentQ = item.q;
    botState.currentA = item.a;
    document.getElementById('botQuestionText').textContent = '🤖 Sage Bot asks: ' + item.q;
    document.getElementById('botHintText').textContent = '💡 Hint: ' + computeSmartHint(item.a);
    document.getElementById('botUserGuessInput').value = '';
    document.getElementById('botAnsweringBox').classList.remove('hidden');

    let sec = 30;
    document.getElementById('botTimerBar').textContent = '⏱ ' + sec + 's';
    if (botTimerInterval) clearInterval(botTimerInterval);
    botTimerInterval = setInterval(function() {
      sec--;
      document.getElementById('botTimerBar').textContent = '⏱ ' + sec + 's';
      if (sec <= 0) {
        clearInterval(botTimerInterval);
        finishBotUserAnswer('');
      }
    }, 1000);
  } else {
    // Even round: Player challenges Sage Bot
    document.getElementById('botCustomQInput').value = '';
    document.getElementById('botCustomAInput').value = '';
    document.getElementById('botAskingBox').classList.remove('hidden');
  }
}

function submitBotUserGuess() {
  if (botTimerInterval) clearInterval(botTimerInterval);
  const guess = document.getElementById('botUserGuessInput').value.trim();
  finishBotUserAnswer(guess);
}

function finishBotUserAnswer(guess) {
  hideAllBotBoxes();
  const isRight = Boolean(guess) && normBotText(guess) === normBotText(botState.currentA);
  botState.lastUserMissed = !isRight;
  if (isRight) {
    botState.userScore += 5;
    document.getElementById('botResultBanner').innerHTML = '<span style="color:var(--green);">✅ Spot on! You earned +5 pts!</span>';
  } else {
    botState.botScore += 5;
    document.getElementById('botResultBanner').innerHTML = '<span style="color:var(--red);">❌ Missed (Your guess: "' + escapeHtml(guess || 'Time up') + '"). Sage Bot gets +5 pts!</span>';
  }
  document.getElementById('botRevealAnswer').textContent = botState.currentA;
  document.getElementById('botContestBtn').classList.toggle('hidden', isRight);
  updateBotScores();
  document.getElementById('botReviewBox').classList.remove('hidden');
}

function contestBotRuling() {
  if (!botState || !botState.lastUserMissed) return;
  botState.lastUserMissed = false;
  botState.botScore = Math.max(0, botState.botScore - 5);
  botState.userScore += 5;
  document.getElementById('botContestBtn').classList.add('hidden');
  document.getElementById('botResultBanner').innerHTML = '<span style="color:var(--gold);">⚖️ Contest Accepted! +5 pts transferred to You!</span>';
  updateBotScores();
}

function botAutoFillQuestion() {
  if (!botState) return;
  const item = pickUnusedBotItem();
  document.getElementById('botCustomQInput').value = item.q;
  document.getElementById('botCustomAInput').value = item.a;
}

function sendQuestionToBot() {
  const q = document.getElementById('botCustomQInput').value.trim();
  const a = document.getElementById('botCustomAInput').value.trim();
  if (!q || !a) { alert('Enter a question and answer, or tap Auto-Pick!'); return; }
  botState.currentQ = q;
  botState.currentA = a;
  hideAllBotBoxes();
  document.getElementById('botThinkingHint').textContent = 'Analyzing hint: ' + computeSmartHint(a);
  document.getElementById('botThinkingBox').classList.remove('hidden');

  const delay = botState.diff === 'grandmaster' ? 1800 : (botState.diff === 'pro' ? 3000 : 4200);
  const winChance = botState.diff === 'grandmaster' ? 0.85 : (botState.diff === 'pro' ? 0.60 : 0.35);

  setTimeout(function() {
    if (!botState) return;
    hideAllBotBoxes();
    const botGotIt = Math.random() < winChance;
    document.getElementById('botContestBtn').classList.add('hidden');
    if (botGotIt) {
      botState.botScore += 5;
      document.getElementById('botResultBanner').innerHTML = '<span style="color:var(--gold);">🤖 Sage Bot guessed "' + escapeHtml(a) + '" and scored +5 pts!</span>';
    } else {
      botState.userScore += 5;
      document.getElementById('botResultBanner').innerHTML = '<span style="color:var(--green);">🎉 You stumped Sage Bot! You earn +5 pts!</span>';
    }
    document.getElementById('botRevealAnswer').textContent = a;
    updateBotScores();
    document.getElementById('botReviewBox').classList.remove('hidden');
  }, delay);
}

function nextBotRound() {
  if (!botState) return;
  if (botState.round >= botState.totalRounds) {
    hideAllBotBoxes();
    const msg = botState.userScore > botState.botScore
      ? '🏆 VICTORY! You defeated Sage Bot (' + botState.userScore + ' - ' + botState.botScore + ')!'
      : (botState.userScore < botState.botScore
        ? '🤖 Sage Bot wins (' + botState.botScore + ' - ' + botState.userScore + '). Rematch?'
        : '🤝 DRAW! Tied at ' + botState.userScore + ' pts!');
    document.getElementById('botFinalHeadline').textContent = botState.userScore >= botState.botScore ? '🏆 MATCH COMPLETE!' : '🤖 SAGE BOT WINS!';
    document.getElementById('botFinalSummary').textContent = msg;
    document.getElementById('botGameoverBox').classList.remove('hidden');
    return;
  }
  botState.round++;
  runBotTurn();
}

window.addEventListener('DOMContentLoaded', function() {
renderCreatorUrl();
renderQB();
checkSavedRoomBanner();
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

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
HTML_TEMPLATE = r"""




Double Sage — Online Multiplayer



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
• { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
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
padding: 20px; text-align: center;
}
#introSlideImg {
max-width: 92%; max-height: 62vh; border-radius: 18px;
box-shadow: 0 12px 40px rgba(56,189,248,0.35); object-fit: contain; pointer-events: none;
}
#introTitle { margin-top: 14px; font-size: 22px; font-weight: 900; color: var(--gold); pointer-events: none; }
#skipIntroBtn {
position: fixed; top: 16px; right: 16px; z-index: 2147483647;
pointer-events: auto; cursor: pointer; background: var(--gold); color: #000;
border: none; padding: 10px 18px; border-radius: 999px; font-weight: 900; font-size: 14px;
box-shadow: 0 4px 15px rgba(0,0,0,0.6);
}
.modal-bg {
position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 10000;
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


Skip Intro ⏭

DOUBLE SAGE — BATTLE OF MINDS
Press Skip Intro to enter immediately
⚔️ DOUBLE SAGE

📖 How to Play
📚 My QBs
🎵 Music: ON
📂 Load Song
🔄 Default Theme


🔄 Active Match Found!
Room ----


Rejoin Now
Dismiss


🤖 Play vs. Sage Bot (Instant Solo Duel)
No opponent online yet? Battle Sage Bot using any pack right now!
Select Pack
Bot Difficulty
Rookie (Casual)
Pro (Balanced)
Grandmaster (Fast)



🤖 Start Solo Duel vs. Sage Bot
🎮 Create Online Room
Your Name
Game Mode
Standard (Setter vs Guesser)
Umpire Mode (Ask All Players — Up to 10)


Rounds / Questions
Timer (sec)
🚀 Create Room
🔗 Join Existing Room

Your Name
4-Letter Code
⚡ Join Room
🏆 Live Tournaments & Creator Hub
Buy official Pro QB Packs, enter paid weekend tournaments, or support Double Sage.
Save Link


ROOM: ----
MODE
Round 1/5


📋 Invite
🏠 Home



⏳ Waiting for Players (Up to 10)
Share the room code or invite link. Host starts when everyone is in.
🔥 Start Match Now
✍️ Set Your Question & Secret Answer

-- Select Pack --
🎲 Auto-Next


-- Or Pick Specific Question --
Load
Question
Secret Answer
✨ Suggest


📤 Send Question to Players


⏳ Waiting for Question...
The Setter/Umpire is typing the question for this round.
⏱ 30s


Your Guess
✅ Submit Answer

✔ Answer submitted! Waiting for remaining players...
📊 Round Results

Correct Answer:


⚖️ Contest Ruling (I Was Right!)

⚖️ Guesser Contested! Was their answer right?

✅ Accept Guesser (+5 Pts)
❌ Reject (Setter Keeps +5)


➡️ Next Round
🏠 Back to Home

Round 1/5
🤖 PRO BOT
🏠 Home


🧑 You0 pts
🤖 Sage Bot0 pts

⏱ 30s

Your Answer
✅ Submit Answer
✍️ Your Turn to Challenge Sage Bot!

🎲 Auto-Pick From Pack
Question for Sage Bot
Secret Answer
✨ Suggest


📤 Challenge Sage Bot
🤖 Sage Bot is thinking...
📊 Round Summary


Secret Answer:


⚖️ Contest Ruling (My Answer Was Right!)
➡️ Next Round
🔁 Rematch
🏠 Back to Home



📖 How to Play Double Sage
✕
1. Standard Mode (Setter vs. Guesser): Players take turns setting a secret question & answer. You get a smart hint showing word count, letter count, and digits (only when numbers exist). Match the answer before time runs out for +5 pts; miss and the Setter gets +5 pts. Think you were judged unfairly? Tap ⚖️ Contest for Setter review!
2. Simultaneous Umpire Mode (1–10 Players): The Umpire is the organizer (0 points) who sets total rounds and asks all players the exact same question at once. Everyone who gets it right earns +5 pts with their speed recorded; if nobody gets it, 0 points are awarded.
3. 🤖 Sage Bot & Pro QB Studio: Battle Sage Bot anytime using 300 built-in questions, import Excel/CSV sheets, or unlock Pro Packs in 📚 My QBs!
📚 My QBs — Pro Pack Studio
✕
Active Question Pack
➕ New Pack
🗑
Add Question to Current Pack
✨ Suggest


➕ Save Question
📊 Import Excel (.xlsx) or CSV (.csv) into Current Pack
📂 Upload Excel / CSV
📄 Sample CSV

🎟️ Unlock Pro QB Pack (NAIJA2026, FOOTYPRO, PARTYVIP, or DSPACK:...)
Unlock
📤 Export Sellable DSPACK Code



🔒 Commercial Pro Pack — Licensed for gameplay (Re-export disabled by creator).
🧹 Clear Pack
"""
if name == 'main':
port = int(os.environ.get('PORT', 10000))
app.run(host='0.0.0.0', port=port)

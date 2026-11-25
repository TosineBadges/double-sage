// --- INTRO SLIDESHOW ---
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

// --- AUDIO ENGINE ---
let musicEnabled = true;
let audioCtx = null;
let synthTimer = null;

function startThemeAudio() {
  if (!musicEnabled) return;
  const bg = document.getElementById('bgMusic');
  if (bg) {
    bg.volume = parseFloat(document.getElementById('volSlider')?.value || 0.8);
    const p = bg.play();
    if (p !== undefined) {
      p.then(function() {
        if (synthTimer) { clearInterval(synthTimer); synthTimer = null; }
      }).catch(function() {});
    }
  }
}

document.addEventListener('pointerdown', function() {
  const bg = document.getElementById('bgMusic');
  if (musicEnabled && bg && bg.paused) startThemeAudio();
}, { once: true });

function toggleMusic() {
  musicEnabled = !musicEnabled;
  const btn = document.getElementById('musicToggleBtn');
  const bg = document.getElementById('bgMusic');
  if (btn) btn.textContent = musicEnabled ? '🎵 Music: ON' : '🎵 Music: OFF';
  if (musicEnabled) startThemeAudio();
  else if (bg) bg.pause();
}

function setMasterVol(v) {
  const bg = document.getElementById('bgMusic');
  if (bg) bg.volume = parseFloat(v);
}

function handleSongUpload(inp) {
  if (!inp.files || !inp.files[0]) return;
  const bg = document.getElementById('bgMusic');
  bg.src = URL.createObjectURL(inp.files[0]);
  bg.loop = true;
  if (musicEnabled) bg.play().catch(function() {});
  document.getElementById('resetThemeBtn')?.classList.remove('hidden');
}

function resetDefaultTheme() {
  const inp = document.getElementById('songUploadInput');
  if (inp) inp.value = '';
  const bg = document.getElementById('bgMusic');
  bg.pause();
  bg.src = '/theme.mp3';
  bg.loop = true;
  bg.load();
  if (musicEnabled) bg.play().catch(function() {});
  document.getElementById('resetThemeBtn')?.classList.add('hidden');
}

// --- AI & MATH ANSWER HELPER ---
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

// --- PRO QB STUDIO ---
window.PRO_PACKS = window.PRO_PACKS || {};
const PRO_PACKS = window.PRO_PACKS;
let usedQuestionKeys = {};

function getPackStore() {
  try {
    const raw = JSON.parse(localStorage.getItem('ds_qb_packs_v2') || 'null');
    if (raw && raw.packs && Object.keys(raw.packs).length) return raw;
  } catch (e) {}
  const store = {
    activeId: 'custom_default',
    packs: {
      custom_default: { title: 'My Custom Pack', locked: false, items: [] }
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
  document.getElementById('qbModal')?.classList.remove('hidden');
}

function switchActivePack(packId) {
  const store = getPackStore();
  if (store.packs[packId]) { store.activeId = packId; savePackStore(store); }
}

function createNewPack() {
  const name = prompt('Enter new pack name:');
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
  if (!confirm('Delete "' + store.packs[store.activeId].title + '"?')) return;
  delete store.packs[store.activeId];
  store.activeId = Object.keys(store.packs)[0];
  savePackStore(store);
}

function clearCurrentPack() {
  const store = getPackStore();
  const pack = store.packs[store.activeId];
  if (!pack || !pack.items.length) return;
  if (!confirm('Clear all questions in "' + pack.title + '"?')) return;
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
  const newA = prompt('Edit Answer:', item.a);
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
        if (idx === 0 && (q.toLowerCase() === 'question' || q.toLowerCase() === 'q')) return;
pack.items.push({ q: q, a: a });
added++;
});
savePackStore(store);
inp.value = '';
if (statusEl) statusEl.textContent = '✅ Imported ' + added + ' questions!';
} catch (err) {
if (statusEl) statusEl.textContent = '❌ Invalid CSV/Excel file.';
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
if (decoded && Array.isArray(decoded.items)) {
const id = 'pack_' + Date.now();
store.packs[id] = {
title: String(decoded.title || 'Unlocked Pro Pack').slice(0, 32),
locked: Boolean(decoded.locked),
items: decoded.items.filter(function(x) { return x && x.q && x.a; })
};
store.activeId = id;
savePackStore(store);
alert('Unlocked "' + store.packs[id].title + '"!');
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
if (pack.locked) { alert('Commercial pack is locked.'); return; }
if (!pack.items.length) { alert('Add questions first!'); return; }
const lockIt = document.getElementById('lockPackCheckbox')?.checked || false;
const code = 'DSPACK:' + btoa(JSON.stringify({ title: pack.title, locked: lockIt, items: pack.items }));
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
const botPackSel = document.getElementById('botPackSelect');
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
qSel.innerHTML = '-- Pick Specific Question (' + livePack.items.length + ') --';
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
row.innerHTML = '' + escapeHtml(item.q) + '
Ans: ' + escapeHtml(item.a) + '' +
'✏️🗑';
container.appendChild(row);
});
}
function syncLivePack() { renderQB(); }
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
if (!pack || !pack.items.length) { alert('This pack is empty!'); return; }
let unplayed = [];
pack.items.forEach(function(, i) { if (!usedQuestionKeys[livePid + ':' + i]) unplayed.push(i); });
if (!unplayed.length) {
pack.items.forEach(function(, i) { delete usedQuestionKeys[livePid + ':' + i]; });
unplayed = pack.items.map(function(_, i) { return i; });
}
const pickIdx = unplayed[Math.floor(Math.random() * unplayed.length)];
usedQuestionKeys[livePid + ':' + pickIdx] = true;
const chosen = pack.items[pickIdx];
document.getElementById('liveQuestionInput').value = chosen.q;
document.getElementById('liveAnswerInput').value = chosen.a;
const statusEl = document.getElementById('liveAiStatus');
if (statusEl) statusEl.textContent = '🎲 Loaded question from "' + pack.title + '"!';
}
// --- CREATOR LINK & MODALS ---
function saveCreatorUrl() {
localStorage.setItem('ds_creator_url', document.getElementById('creatorUrlInput').value.trim());
renderCreatorUrl();
}
function renderCreatorUrl() {
const url = localStorage.getItem('ds_creator_url') || '';
const box = document.getElementById('creatorLinkDisplay');
if (!box) return;
box.innerHTML = url ? '🎟️ Buy Tournament Ticket / Support Creator' : '';
}
function openHowToPlay() { document.getElementById('howToPlayModal')?.classList.remove('hidden'); }
function escapeHtml(str) {
return String(str || '').replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>').replace(/"/g, '"');
}
// --- VICTORY POSTER & REJOIN ---
function saveShareLink(val) { localStorage.setItem('ds_custom_share_link', val); }
function buildVictoryPosterHtml(winnerName, pointsText, subtitleText) {
const defaultLink = localStorage.getItem('ds_custom_share_link') || location.origin;
return '🏆👑🏆' +
'DOUBLE SAGE GRAND CHAMPION' +
'' + escapeHtml(winnerName) + '' +
'⚡ ' + escapeHtml(pointsText) + '' +
'' + escapeHtml(subtitleText) + '' +
'' +
'🔗 Editable Game Link (Tap to edit & share):' +
'' +
'' +
'📤 Share' +
'' +
'';
}
function shareVictoryCard(btn) {
const winnerName = btn.getAttribute('data-winner') || 'Champion';
const pointsText = btn.getAttribute('data-pts') || '';
const link = (document.getElementById('victoryShareUrlInput')?.value || location.origin).trim();
const msg = '🏆 DOUBLE SAGE CHAMPION!\n👑 Winner: ' + winnerName + '\n⚡ Score: ' + pointsText + '\n\nThink you can beat me? Play Double Sage here:\n' + link;
if (navigator.share) {
navigator.share({ title: 'Double Sage Victory!', text: msg, url: link }).catch(function() {});
} else {
if (navigator.clipboard) navigator.clipboard.writeText(msg);
alert('Victory card copied!\n\n' + msg);
}
}
function saveActiveRoomSession(code, pid) {
localStorage.setItem('ds_active_room', code);
localStorage.setItem('ds_active_pid', pid);
}
function clearSavedRoom() {
localStorage.removeItem('ds_active_room');
localStorage.removeItem('ds_active_pid');
document.getElementById('rejoinBanner')?.classList.add('hidden');
}
function confirmLeaveRoom() {
if (!confirm('Do you really want to give up?\n\nPress OK (YES) to return Home (you can Rejoin while active), or Cancel (NO) to stay.')) return;
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
if (data.room.players.some(function(p) { return p.id === pid; })) {
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
alert('Room ended or expired.');
clearSavedRoom();
}
} catch (e) { alert('Network error — tap Rejoin again.'); }
}
// --- MULTIPLAYER ROOMS ---
let currentCode = '';
let myPlayerId = '';
let pollTimer = null;
async function apiPost(url, body) {
const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
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
if (!question || !answer) { alert('Enter both question and answer'); return; }
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
if (res.ok) { document.getElementById('playerGuessInput').value = ''; renderRoom(res.room); }
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
if (!me) { alert('Removed from room.'); finishAndGoHome(); return; }
const isHost = (room.host_id === myPlayerId);
document.getElementById('roomCodeBadge').textContent = 'ROOM: ' + room.code;
document.getElementById('roomModeBadge').textContent = room.mode === 'umpire' ? 'UMPIRE MODE' : 'STANDARD MODE';
document.getElementById('roundBadge').textContent = 'Round ' + room.current_round + '/' + room.total_rounds;
const sb = document.getElementById('scoreboardArea');
sb.innerHTML = '';
room.players.forEach(function(p) {
const div = document.createElement('div');
div.className = 'player-item';
const roleTag = p.is_umpire ? '🎙 Umpire' :
'' + p.score + ' pts (' + p.total_time + 's)';
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
if (amAsker) document.getElementById('askerTitle').textContent = room.mode === 'umpire' ? '🎙 Ask All Players Simultaneously' : '✍️ Your Turn to Set a Question';
} else if (room.phase === 'answering') {
document.getElementById('answeringPhase').classList.remove('hidden');
document.getElementById('activeQuestionText').textContent = '❓ ' + room.question;
document.getElementById('activeHintText').textContent = '💡 Hint: ' + room.hint;
const setter = room.players[room.setter_idx % room.players.length];
const isAsker = (room.mode === 'umpire') ? me.is_umpire : (setter && setter.id === myPlayerId);
const alreadySubmitted = Boolean(room.submissions && room.submissions[myPlayerId]);
document.getElementById('guesserInputBox').classList.toggle('hidden', isAsker || alreadySubmitted);
document.getElementById('submittedWaitBox').classList.toggle('hidden', !isAsker && !alreadySubmitted);
if (isAsker) document.getElementById('submittedWaitBox').innerHTML = '⏳ Players are answering...';
const rem = Math.max(0, Math.ceil(room.timer - ((Date.now() / 1000) - room.question_sent_at)));
document.getElementById('countdownDisplay').textContent = '⏱ ' + rem + 's';
if (rem <= 0 && isHost) apiPost('/api/timeout', { code: currentCode });
} else if (room.phase === 'review') {
document.getElementById('reviewPhase').classList.remove('hidden');
document.getElementById('revealAnswerText').textContent = room.answer;
const subList = document.getElementById('submissionsList');
subList.innerHTML = '';
const subs = Object.values(room.submissions || {});
if (!subs.length) subList.innerHTML = 'No answers submitted (0 pts).';
else subs.forEach(function(s) {
const badge = s.correct ? '✅ +5 pts (' + s.time + 's)' : '❌ 0 pts (' + s.time + 's)';
subList.innerHTML += '' + escapeHtml(s.name) + ': ' + escapeHtml(s.guess) + '' + badge + '';
});
const contestArea = document.getElementById('contestArea');
if (room.mode === 'standard') {
contestArea.classList.remove('hidden');
const setter = room.players[room.setter_idx % room.players.length];
const amSetter = setter && setter.id === myPlayerId;
document.getElementById('contestBtn').classList.toggle('hidden', amSetter || room.contest_pending);
document.getElementById('setterApprovalBox').classList.toggle('hidden', !amSetter || !room.contest_pending);
} else contestArea.classList.add('hidden');
document.getElementById('nextRoundBtn').classList.toggle('hidden', !isHost || room.contest_pending);
} else if (room.phase === 'gameover') {
document.getElementById('gameoverPhase').classList.remove('hidden');
const ranked = room.players.filter(function(p) { return !p.is_umpire; }).sort(function(a, b) { return (b.score - a.score) || (a.total_time - b.total_time); });
const champ = ranked[0];
const poster = document.getElementById('mpVictoryPoster');
if (poster && champ) {
poster.innerHTML = buildVictoryPosterHtml(champ.name, champ.score + ' Points (' + champ.total_time + 's)', 'Room ' + room.code);
}
const pod = document.getElementById('finalPodium');
pod.innerHTML = '';
ranked.forEach(function(p, idx) {
const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '#' + (idx + 1);
pod.innerHTML += '' + medal + ' ' + escapeHtml(p.name) + '' + p.score + ' pts (' + p.total_time + 's)';
});
}
}
// --- SAGE BOT SOLO DUEL ---
let botState = null;
let botTimerInterval = null;
function computeSmartHint(ans) {
const raw = String(ans || '').trim();
const words = raw.split(/\s+/).filter(Boolean).length;
let letters = 0, digits = 0;
for (let i = 0; i < raw.length; i++) {
if (/[a-zA-Z]/.test(raw[i])) letters++;
else if (/[0-9]/.test(raw[i])) digits++;
}
const parts = [];
if (letters > 0) {
parts.push(words + (words === 1 ? ' word' : ' words'));
parts.push(letters + (letters === 1 ? ' letter' : ' letters'));
}
if (digits > 0) parts.push(digits + (digits === 1 ? ' digit' : ' digits'));
return parts.join(', ');
}
function normBotText(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ').trim(); }
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
if (!items.length) { alert('Select a pack with questions!'); return; }
botState = { items: items, used: {}, diff: diff, round: 1, totalRounds: Math.min(6, Math.max(4, items.length)), userScore: 0, botScore: 0, currentQ: '', currentA: '', lastUserMissed: false };
document.getElementById('homeView').classList.add('hidden');
document.getElementById('botView').classList.remove('hidden');
document.getElementById('botDiffBadge').textContent = '🤖 ' + diff.toUpperCase() + ' BOT';
updateBotScores();
runBotTurn();
}
function exitBotMatch(skipConfirm) {
if (!skipConfirm && botState && !confirm('Do you really want to give up?\n\nPress OK (YES) to quit to Home, or Cancel (NO) to keep playing.')) return;
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
['botAnsweringBox', 'botAskingBox', 'botThinkingBox', 'botReviewBox', 'botGameoverBox'].forEach(function(id) { document.getElementById(id).classList.add('hidden'); });
}
function pickUnusedBotItem() {
const avail = [];
botState.items.forEach(function(, i) { if (!botState.used[i]) avail.push(i); });
if (!avail.length) { botState.used = {}; botState.items.forEach(function(, i) { avail.push(i); }); }
const idx = avail[Math.floor(Math.random() * avail.length)];
botState.used[idx] = true;
return botState.items[idx];
}
function runBotTurn() {
hideAllBotBoxes();
updateBotScores();
if (botState.round % 2 === 1) {
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
if (sec <= 0) { clearInterval(botTimerInterval); finishBotUserAnswer(''); }
}, 1000);
} else {
document.getElementById('botCustomQInput').value = '';
document.getElementById('botCustomAInput').value = '';
document.getElementById('botAskingBox').classList.remove('hidden');
}
}
function submitBotUserGuess() {
if (botTimerInterval) clearInterval(botTimerInterval);
finishBotUserAnswer(document.getElementById('botUserGuessInput').value.trim());
}
function finishBotUserAnswer(guess) {
hideAllBotBoxes();
const isRight = Boolean(guess) && normBotText(guess) === normBotText(botState.currentA);
botState.lastUserMissed = !isRight;
if (isRight) {
botState.userScore += 5;
document.getElementById('botResultBanner').innerHTML = '✅ Spot on! You earned +5 pts!';
} else {
botState.botScore += 5;
document.getElementById('botResultBanner').innerHTML = '❌ Missed. Sage Bot gets +5 pts!';
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
document.getElementById('botResultBanner').innerHTML = '⚖️ Contest Accepted! +5 pts to You!';
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
if (!q || !a) { alert('Enter a question and answer!'); return; }
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
document.getElementById('botResultBanner').innerHTML = '🤖 Sage Bot guessed "' + escapeHtml(a) + '" (+5 pts)!';
} else {
botState.userScore += 5;
document.getElementById('botResultBanner').innerHTML = '🎉 You stumped Sage Bot (+5 pts)!';
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
const winnerLabel = botState.userScore > botState.botScore ? 'YOU (Challenger)' : (botState.userScore < botState.botScore ? 'SAGE BOT' : 'TIE MATCH');
const winPts = Math.max(botState.userScore, botState.botScore) + ' Points (' + botState.userScore + ' - ' + botState.botScore + ')';
document.getElementById('botVictoryPoster').innerHTML = buildVictoryPosterHtml(winnerLabel, winPts, 'Solo Arena • ' + botState.diff.toUpperCase());
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

# Double Sage — 1v1 & Multiplayer Word & Clue Duel

**Outsmart. Outguess. Outscore.**

Double Sage is a fast-paced social trivia and word-guessing game where players write custom questions for each other while a neutral **Manager** calculates exact structural hints (words, letters, and conditional digits), enforces uniform countdown timers, and settles tie-breakers by total answering speed.

---

## Core Game Rules

1. **The Trap (Asker / Umpire):** One player (or a dedicated Umpire) enters a question and a secret answer—or picks and edits one from the built-in quick prompts.
2. **The Manager's Hint:** The Manager hides the secret answer and reveals only the question along with exact counts:
   - **Word count** (e.g., `2 words`)
   - **Letter count** (e.g., `11 letters`)
   - **Conditional Digit count:** Shown **only** if numbers appear in the answer (e.g., `57` -> `2 digits`, `0` -> `1 digit`). Omitted completely when there are no numbers.
3. **5-Point Swing & Speed Tie-Breaker:**
   - Correct guess within the time limit (10s–60s): **+5 points to the Guesser**.
   - Wrong guess or time-out: **+5 points to the Asker** (in Standard Mode).
   - If players tie on points at the end of the match, the player with the **shortest cumulative answering time** wins.
4. **Two-Step Contest & Approval:**
   - **Standard Mode:** If a Guesser is marked wrong due to a typo or unfair answer, they can tap **Contest Answer**, allowing the Asker to either **Accept Guess (+5 Pts to Guesser)** or **Send New Question (0 Pts & Re-Ask)**.
   - **Umpire Mode:** When an Umpire organizes and sets questions for the players, the **Umpire's ruling is always final**.

---

## Repository Files

- **`index.html`** — Standalone **Same-Phone Pass & Play** web app (ready for **Vercel**). Supports 2–10 players, Umpire Mode, editable quick prompts, Web Audio SFX & vibration alerts, and Contest & Approval.
- **`app.py`** — Real-time **Online Multiplayer** Flask server (ready for **Render**). Generates 4-letter room codes, one-tap invite links (`/?room=XXXX`), host kick controls, Umpire Mode, and remote Contest & Approval across separate phones.
- **`requirements.txt`** — Python dependencies (`flask` and `gunicorn`) for cloud deployment.

---

## Quick Deployment

### 1. Deploy Pass-and-Play on Vercel (Free)
1. Upload `index.html` (and any game images) to a GitHub repository.
2. Go to [vercel.com](https://vercel.com), import your GitHub repository, and click **Deploy**.

### 2. Deploy Online Multiplayer on Render (Free)
1. Upload `app.py` and `requirements.txt` to your GitHub repository.
2. Go to [render.com](https://render.com), create a **New Web Service** connected to your repository, and set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
3. Click **Create Web Service** and share your live `.onrender.com` link with friends.

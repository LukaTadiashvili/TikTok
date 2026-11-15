# Daily Georgian TikTok videos (free)

Every morning around **07:20 Tbilisi time**, GitHub Actions makes one 20-30 second vertical video and sends it to your **Telegram** before 08:00. You post it to TikTok yourself.

**What each video contains** (rendered with [Remotion](https://remotion.dev) in `render/`)
- **Hook:** a yellow title box with a shake, a zoom hit and a bass sound in the first second
- **Visuals that follow the words:** each spoken phrase gets its own AI-generated cinematic image (Pollinations), animated with camera moves; stock video is used only as a fallback
- **Suspense:** dark color grade, film grain, glitch hits, camera shake, booms, risers, heartbeat and an ambient drone
- **Pop-ups synced to the voice:** emojis, counting numbers (`700 000 ₾`), keyword cards and ✅/❌ marks, each with a pop sound
- **Captions:** word-by-word with exact timing; the spoken word is highlighted and key words sit on yellow boxes
- **Progress bar** at the top, plus whoosh sounds and optional music from `assets/music/`
- **Voice:** tried in this order: ElevenLabs (paid, most realistic), then Gemini TTS (free API key; Georgian is a preview language), then the free edge-tts voice.

Cost: ElevenLabs Starter is about $6 per month. Everything else is free.

## Scripts
`scripts/bank.json` holds ready-made Georgian scripts, written by Claude in chat. The job uses one per day and picks the topic with the fewest videos so far. When 5 or fewer are left, the bot warns you in Telegram. Then ask Claude: *"write 30 more scripts for the TikTok bank"*.

Format of one script: each beat is one spoken phrase.
```json
{"id": "S025", "niche": "facts", "hook_type": "shock", "title": "...", "hook_text": "on-screen hook",
 "beats": [{"say": "Georgian phrase, *key words* in asterisks", "tone": "excited", "shot": "english stock-video query",
            "pop": {"type": "emoji|number|card|check|cross", "value": "🍯 or 700000", "suffix": " ₾", "text": "card text"}}],
 "caption": "...", "hashtags": ["#..."]}
```

## Experiment: find what works
Each video has an ID such as `V007`, shown in the Telegram message. About 48 hours after posting, add a line to `data/results.csv`:
```
V007,2026-11-20,1520,130,12,4,9      (id, date, views, likes, comments, shares, saves)
```
Then run `python analyze.py` to see averages by **topic**, **hook type** (shock, question, mistake, story) and **voice**. When a topic clearly wins, set the repo variable `LOCK_NICHE` (for example `facts`).

## One-time setup (about 15 min)
Go to GitHub repo **Settings, then Secrets and variables, then Actions, then New repository secret**:

| Secret | How to get it (all free) |
|---|---|
| `TELEGRAM_BOT_TOKEN` | In Telegram, message **@BotFather**, send `/newbot`, and copy the token |
| `TELEGRAM_CHAT_ID` | Send "hi" to your new bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the number in `"chat":{"id":...}` |
| `PIXABAY_API_KEY` | Sign up at pixabay.com, then open pixabay.com/api/docs and copy the green key shown under **Parameters** next to `key` |
| `POLLINATIONS_API_KEY` | enter.pollinations.ai, then sign in, then Keys, then create a secret key (costs about $0.02-0.04 per video in Pollen) |
| `GEMINI_API_KEY` | *Free.* aistudio.google.com, then Get API key, then Create API key |
| `ELEVENLABS_API_KEY` | *Optional, paid.* elevenlabs.io, then the Starter plan, then Profile, then API Keys, then Create (Text to Speech and Voices read access) |

Variables (the Variables tab): `ELEVENLABS_VOICES` = comma-separated voice IDs to rotate (otherwise `voices.json` is used). Optionally `ELEVENLABS_MODEL` to force a model.

The workflow file must be on the repo's **default branch** for the daily schedule to run.

**Test:** open the Actions tab, then **Daily TikTok video**, then **Run workflow**. A video arrives in Telegram within about 5-10 minutes.

## Tips when posting
- In TikTok, add a **trending sound** at low volume. This gives a big reach boost.
- Post at the same time every day. In Georgia, 12:00-14:00 or 19:00-22:00 usually work best.
- Copy the caption from the last Telegram message.

## Run locally
```bash
pip install -r requirements.txt && (cd render && npm ci)   # needs ffmpeg + Node 22
python generate.py --script S001 --no-send --no-log
```

Footage: Pixabay / Pexels (free licenses). Optional `PEXELS_API_KEY` works too if you have one. Font: Noto Sans and Noto Sans Georgian (SIL OFL, `assets/fonts/OFL.txt`).

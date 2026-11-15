"""Mini-series pipeline: Veo clips (made by hand in Google Flow) -> finished TikTok episode.

Flow:
  1. `python series.py prompts`  -> the bot sends the next episode's Veo prompts to Telegram
  2. you generate the clips in Flow and send them to the bot (in order: clip 1, then clip 2)
  3. `python series.py check`    -> quick: reads Telegram, says if all clips of the episode arrived
     `python series.py collect`  -> picks up the clips from Telegram, edits the episode
     (narrator voice, Georgian subtitles, title, pop-ups, sound effects, end card),
     sends it back, then sends the prompts for the next episode
  Local test: `python series.py render 1 clip1.mp4 clip2.mp4`

Telegram commands you can send the bot:  /prompts  (resend prompts)   /reset  (forget received clips)
"""

import json
import os
import random
import shutil
import sys
from pathlib import Path

import requests

import generate as g

ROOT = Path(__file__).parent
STATE = ROOT / "series/state.json"
OUT = ROOT / "output"
END_CARD = 2.6  # seconds


def load_season(sid):
    return json.loads((ROOT / f"series/{sid}.json").read_text())


def episode(season, n):
    return next((e for e in season["episodes"] if e["n"] == n), None)


# ---------------------------------------------------------------- narration

NARRATOR_GEMINI = os.getenv("NARRATOR_GEMINI_VOICE") or "Charon"


def narrate(text, path):
    """One narrator line. ElevenLabs -> Gemini -> edge-tts -> none. Returns duration or None."""
    plain = g.plain(text)
    key = os.getenv("ELEVENLABS_API_KEY")
    if key:
        try:
            voice = os.getenv("ELEVENLABS_NARRATOR_VOICE") or (g.eleven_auto_voices(key) or [None])[0]
            if voice:
                model = g.eleven_model(key)
                tagged = f"[mysterious] {plain}" if ("v3" in model or "v4" in model) else plain
                r = requests.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": key, "Content-Type": "application/json"},
                    json={"text": tagged, "model_id": model, "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
                    timeout=120)
                r.raise_for_status()
                path.write_bytes(r.content)
                return g.duration(path)
        except Exception as e:
            g.log(f"ElevenLabs narrator failed: {e}")
    gkey = os.getenv("GEMINI_API_KEY")
    if gkey:
        try:
            model = os.getenv("GEMINI_TTS_MODEL") or "gemini-2.5-flash-preview-tts"
            prompt = ("You are the narrator of a dark Georgian psychological thriller series, like a movie trailer "
                      "voice: deep, slow, calm and ominous, with dramatic pauses. Say in Georgian:\n" + plain)
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": gkey, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                          "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": NARRATOR_GEMINI}}}}},
                timeout=180)
            r.raise_for_status()
            import base64
            import re
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            pcm = path.with_suffix(".pcm")
            pcm.write_bytes(base64.b64decode(part["data"]))
            rate = re.search(r"rate=(\d+)", part.get("mimeType", ""))
            g.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", rate.group(1) if rate else "24000",
                   "-ac", "1", "-i", pcm, "-af", "silenceremove=start_periods=1:start_threshold=-45dB,"
                   "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse", path])
            return g.duration(path)
        except Exception as e:
            g.log(f"Gemini narrator failed: {e}")
    try:
        if g.edge_voice(path, plain, "ka-GE-GiorgiNeural"):
            return g.duration(path)
    except Exception as e:
        g.log(f"edge-tts narrator failed: {e}")
    return None


# ------------------------------------------------------------------- render

def words_for(text, a, z, page0):
    """Caption words spread over [a, z]; pages of up to 3 words."""
    toks = []
    for i, part in enumerate(text.split("*")):
        for w in part.split():
            toks.append((w, i % 2 == 1))
    weights = [len(w) + 1 for w, _ in toks]
    out, t, page, cnt = [], a, page0, 0
    for (w, emph), wt in zip(toks, weights):
        d = (z - a) * wt / sum(weights)
        if cnt >= 3:
            page, cnt = page + 1, 0
        out.append({"text": w, "start": round(t, 3), "end": round(t + d, 3), "emph": emph, "page": page})
        t += d
        cnt += 1
        if w[-1] in ".!?,:…":
            page, cnt = page + 1, 0
    return out, page + 1


def render_episode(season, ep, clip_files, final):
    work = OUT / f"{season['id']}_ep{ep['n']:02d}"
    if work.exists():
        shutil.rmtree(work)
    (work / "clips").mkdir(parents=True)
    g.CACHE.mkdir(parents=True, exist_ok=True)

    clips, words, overlays, sfx, duck, page, t0 = [], [], [], [], [], 0, 0.0
    sfx.append({"src": "sfx/hit.wav", "start": 0.0, "volume": 0.8})
    for i, (spec, src) in enumerate(zip(ep["clips"], clip_files)):
        name = f"clips/c{i}{Path(src).suffix or '.mp4'}"
        shutil.copy(src, work / name)
        dur = g.duration(work / name)
        clips.append({"src": name, "start": round(t0, 3), "end": round(t0 + dur, 3), "move": "none", "withAudio": True})
        if i:
            sfx.append({"src": "sfx/whoosh.wav", "start": max(0, t0 - 0.15), "volume": 0.5})
        for j, line in enumerate(sorted(spec.get("lines", []), key=lambda l: l.get("at", l.get("from", 0)))):
            if line["who"] == "narrator":
                a = t0 + line["at"]
                audio = work / f"narr_{i}_{j}.mp3"
                d = narrate(line["text"], audio)
                if d:
                    sfx.append({"src": audio.name, "start": a, "volume": 1.0})
                else:
                    d = len(g.plain(line["text"]).split()) * 0.42
                duck.append([round(a, 3), round(a + d, 3)])
                w, page = words_for(line["text"], a, a + d, page)
            else:
                w, page = words_for(line["text"], t0 + line["from"], t0 + line["to"], page)
            words += w
        for k, p in enumerate(spec.get("pops", [])):
            at = t0 + p["at"]
            o = {k2: v for k2, v in p.items() if k2 not in ("at", "dur")}
            overlays.append({**o, "start": round(at, 3), "end": round(at + p.get("dur", 1.6), 3), "slot": k})
            sfx.append({"src": "sfx/ding.wav" if p["type"] == "number" else "sfx/pop.wav", "start": at, "volume": 0.6})
        t0 += dur

    total = t0 + END_CARD
    sfx.append({"src": "sfx/riser.wav", "start": max(0, t0 - 1.6), "volume": 0.5})
    sfx.append({"src": "sfx/boom.wav", "start": t0, "volume": 0.9})
    props = {
        "fps": g.FPS, "durationInFrames": int(total * g.FPS), "audio": None, "music": None,
        "hook": {"text": "", "end": 0},
        "title": {"series": season["title"], "episode": f"სერია {ep['n']} / {season['episodes_total']}", "end": 2.6},
        "endCard": {"start": round(t0, 3), "text": ep.get("next", "გაგრძელება იქნება..."), "sub": "გამოიწერე, რომ არ გამოგრჩეს 🔔"},
        "clips": clips, "words": words, "overlays": overlays, "sfx": sfx,
        "flashes": [], "glitches": [], "shakes": [], "mood": "bright", "duck": duck,
        "captionTop": 1440, "overlayTop": 400,
        "_total": total,
    }
    # narrator audio files live in the work dir root; sfx paths are relative to it
    g.render(props, work, final)
    return total


# ----------------------------------------------------------------- telegram

def tg(method, **data):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=120)
    r.raise_for_status()
    return r.json()["result"]


def send_text(text):
    tg("sendMessage", chat_id=os.environ["TELEGRAM_CHAT_ID"], text=text)


def send_prompts(season, n, state):
    ep = episode(season, n)
    if not ep:
        send_text(f"✅ სეზონი დასრულდა ან სერია {n} ჯერ არ დაწერილა. სთხოვე Claude-ს შემდეგი სერიები.")
        return
    send_text(f"🎬 {season['title']} · სერია {n}/{season['episodes_total']}: „{ep['title']}“\n\n"
              f"Flow-ში დააგენერირე {len(ep['clips'])} კლიპი (9:16) და გამომიგზავნე რიგით 👇")
    for i, c in enumerate(ep["clips"], 1):
        send_text(f"კლიპი {i}/{len(ep['clips'])}:\n\n{c['prompt']}")
    state["prompts_sent_for"] = n


def collect(season, state, do_render=True):
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    updates = tg("getUpdates", offset=state["last_update_id"] + 1, timeout=0,
                 allowed_updates=json.dumps(["message"]))
    for u in updates:
        state["last_update_id"] = u["update_id"]
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) != chat:
            continue
        text = (m.get("text") or "").strip().lower()
        if text in ("/reset", "reset"):
            state["received"] = []
            send_text("🔄 მიღებული კლიპები წაიშალა. გამომიგზავნე თავიდან.")
        elif text in ("/prompts", "prompts"):
            send_prompts(season, state["next_episode"], state)
        media = m.get("video") or m.get("document")
        if media and (m.get("video") or str(media.get("mime_type", "")).startswith("video")):
            state["received"].append(media["file_id"])
            ep = episode(season, state["next_episode"])
            need = len(ep["clips"]) if ep else 2
            if len(state["received"]) < need:
                send_text(f"👍 კლიპი {len(state['received'])}/{need} მივიღე.")

    ep = episode(season, state["next_episode"])
    if not ep or len(state["received"]) < len(ep["clips"]):
        return False
    if not do_render:  # light check: tell the workflow that a render is needed
        out = os.getenv("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as f:
                f.write("ready=true\n")
        return True
    send_text(f"⏳ სერია {ep['n']}-ს ვამონტაჟებ (დაახლოებით 5 წუთი)...")
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    files = []
    dl = OUT / "incoming"
    dl.mkdir(parents=True, exist_ok=True)
    for i, fid in enumerate(state["received"][:len(ep["clips"])]):
        info = tg("getFile", file_id=fid)
        p = dl / f"ep{ep['n']}_c{i}.mp4"
        g.download(f"https://api.telegram.org/file/bot{token}/{info['file_path']}", p)
        files.append(p)
    final = (OUT / f"{season['id']}_ep{ep['n']:02d}.mp4").resolve()
    total = render_episode(season, ep, files, final)
    caption = (f"{season['title']} · სერია {ep['n']} 🔒\n\n{ep.get('caption', 'რომელი მათგანი იტყუება? დაწერე 👇')}\n\n"
               + " ".join(ep.get("hashtags", ["#ექსპერიმენტი", "#სერიალი", "#თრილერი", "#საქართველო", "#fyp"])))
    with open(final, "rb") as f:
        requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                      data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "supports_streaming": "true",
                            "caption": f"✅ სერია {ep['n']} მზადაა ({total:.0f} წმ)"},
                      files={"video": f}, timeout=300).raise_for_status()
    send_text(caption)
    send_text("📌 ატვირთვისას TikTok-ში ჩართე „AI-generated content“.")
    state["received"] = state["received"][len(ep["clips"]):]
    state["next_episode"] += 1
    send_prompts(season, state["next_episode"], state)
    return True


# --------------------------------------------------------------------- main

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    state = json.loads(STATE.read_text())
    season = load_season(state["series"])
    if cmd == "render":
        n, files = int(sys.argv[2]), [Path(p) for p in sys.argv[3:]]
        final = (OUT / f"{season['id']}_ep{n:02d}.mp4").resolve()
        total = render_episode(season, episode(season, n), files, final)
        g.log(f"Episode ready: {final} ({total:.1f}s)")
        return
    if cmd == "prompts":
        send_prompts(season, state["next_episode"], state)
    else:
        if state.get("prompts_sent_for") != state["next_episode"]:
            send_prompts(season, state["next_episode"], state)
        collect(season, state, do_render=(cmd != "check"))
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()

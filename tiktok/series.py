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
import re
import shutil
import sys
from pathlib import Path

import requests

import generate as g

ROOT = Path(__file__).parent
STATE = ROOT / "series/state.json"
OUT = ROOT / "output"
END_CARD = 2.4  # seconds


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
            prompt = f"Say in a deep, slow, ominous thriller-trailer voice, in Georgian: {plain}"
            part = None
            for attempt in range(4):
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": gkey, "Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                              "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": NARRATOR_GEMINI}}}}},
                    timeout=180)
                if r.status_code == 429:
                    import time
                    time.sleep(20)
                    continue
                r.raise_for_status()
                cand = (r.json().get("candidates") or [{}])[0]
                parts = (cand.get("content") or {}).get("parts") or []
                part = next((p["inlineData"] for p in parts if "inlineData" in p), None)
                if part:
                    break
                g.log(f"Gemini narrator empty answer (finishReason={cand.get('finishReason')}), retrying")
            if not part:
                raise RuntimeError("Gemini gave no audio")
            import base64
            import re
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


def speech_spans(path):
    """Voiced intervals [(a, b)] in a clip's audio (non-silent parts)."""
    import re
    import subprocess
    out = subprocess.run(["ffmpeg", "-i", str(path), "-af", "highpass=f=150,lowpass=f=4000,silencedetect=noise=-32dB:d=0.25",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    total = g.duration(path)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    spans, t = [], 0.0
    for a, b in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if a > t:
            spans.append((t, a))
        t = b
    if t < total:
        spans.append((t, total))
    return spans


def fit_window(spans, a, b):
    """Snap a subtitle window to the speech actually heard around it."""
    starts = [x for x, _ in spans if a - 0.6 <= x <= a + 1.0]
    ends = [y for _, y in spans if b - 1.0 <= y <= b + 0.6]
    s0 = starts[0] if starts else a
    s1 = ends[-1] if ends else b
    return (s0, s1) if s1 - s0 > 0.6 else (a, b)


def make_cover(season, ep, clip_files, out):
    """Thumbnail 1080x1920: a strong frame from the episode + big "სერია N" title.
    Text sits in the middle band so it also reads in TikTok's 3:4 profile grid crop."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W, H = 1080, 1920
    # one fixed background per series (series/<id>_cover.jpg) so all episodes look the same;
    # if it doesn't exist yet, take a frame from this episode and keep it for the next ones
    frame = ROOT / f"series/{season['id']}_cover.jpg"
    if not frame.exists():
        src = clip_files[-1]
        g.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{g.duration(src) * 0.8:.2f}", "-i", src,
               "-frames:v", "1", "-q:v", "2", frame])
    img = Image.open(frame).convert("RGB")
    sc = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * sc), round(img.height * sc)), Image.LANCZOS)
    l, t = (img.width - W) // 2, (img.height - H) // 2
    img = img.crop((l, t, l + W, t + H)).convert("RGBA")
    # darken for contrast: vertical gradient, strongest behind the text band
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for y in range(H):
        k = 0.25 + 0.5 * max(0.0, 1 - abs(y - H * 0.62) / (H * 0.32))
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(255 * k)))
    img.alpha_composite(shade)
    font = str(ROOT / "assets/fonts/TikTokGeo.ttf")

    def centered(text, size, y, fill, glow=None, spacing=0):
        f = ImageFont.truetype(font, size)
        dd = ImageDraw.Draw(img)
        w = sum(dd.textlength(ch, font=f) for ch in text) + spacing * (len(text) - 1)
        if glow:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(layer)
            x = (W - w) / 2
            for ch in text:
                gd.text((x, y), ch, font=f, fill=glow)
                x += gd.textlength(ch, font=f) + spacing
            blur = layer.filter(ImageFilter.GaussianBlur(28))
            img.alpha_composite(blur)
            img.alpha_composite(blur)
        x = (W - w) / 2
        for ch in text:
            dd.text((x, y), ch, font=f, fill=fill)
            x += dd.textlength(ch, font=f) + spacing

    centered(season["title"].upper(), 74, int(H * 0.47), (255, 255, 255, 235), spacing=10)
    centered(f"სერია {ep['n']}", 190, int(H * 0.53), (255, 255, 255, 255), glow=(255, 30, 50, 255))
    img.convert("RGB").save(out, quality=92)
    return out


def render_episode(season, ep, clip_files, final):
    """Cinematic edit: Veo sound untouched, film subtitles, title, freeze-frame end card."""
    work = OUT / f"{season['id']}_ep{ep['n']:02d}"
    if work.exists():
        shutil.rmtree(work)
    (work / "clips").mkdir(parents=True)
    g.CACHE.mkdir(parents=True, exist_ok=True)

    clips, subs, cards, sfx, duck, t0 = [], [], [], [], [], 0.0
    for i, (spec, src) in enumerate(zip(ep["clips"], clip_files)):
        name = f"clips/c{i}{Path(src).suffix or '.mp4'}"
        shutil.copy(src, work / name)
        dur = g.duration(work / name)
        spans = speech_spans(work / name)
        planned = max([l.get("to", l.get("at", 0)) for l in spec.get("lines", [])] + [15.0])
        k = min(1.0, dur / planned) if dur < planned - 0.5 else 1.0  # clip shorter than planned: scale times
        clips.append({"src": name, "start": round(t0, 3), "end": round(t0 + dur, 3), "move": "none", "withAudio": True})
        for j, line in enumerate(spec.get("lines", [])):
            text = g.plain(line["text"])
            if line["who"] == "card":  # on-screen trailer text, no voice
                cards.append({"text": text, "start": round(t0 + line["from"] * k, 3), "end": round(t0 + line["to"] * k, 3)})
                continue
            if line["who"] == "narrator":  # narrator added in the edit (older episodes)
                a = t0 + line["at"] * k
                audio = work / f"narr_{i}_{j}.mp3"
                d = narrate(line["text"], audio)
                if d:
                    sfx.append({"src": audio.name, "start": a, "volume": 1.0})
                    duck.append([round(a, 3), round(a + d, 3)])
                else:
                    d = len(text.split()) * 0.42
                subs.append({"text": text, "start": round(a, 3), "end": round(a + d + 0.2, 3)})
            else:  # spoken inside the Veo clip
                a, b = fit_window(spans, line["from"] * k, line["to"] * k)
                subs.append({"text": text, "start": round(t0 + a, 3), "end": round(t0 + min(b, dur), 3)})
        t0 += dur
    # long lines -> one sentence per subtitle, time split by length
    split = []
    for x in subs:
        parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", x["text"]) if p.strip()]
        if len(x["text"]) <= 45 or len(parts) < 2:
            split.append(x)
            continue
        t, span = x["start"], x["end"] - x["start"]
        for p in parts:
            d = span * len(p) / sum(len(q) for q in parts)
            split.append({"text": p, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
    subs = sorted(split, key=lambda x: x["start"])
    for n in range(len(subs) - 1):  # never overlap two subtitles
        subs[n]["end"] = min(subs[n]["end"], subs[n + 1]["start"] - 0.05)
    subs = [x for x in subs if x["end"] - x["start"] >= 0.4]

    # last frame for the freeze-frame end card
    last = work / "clips" / f"c{len(clips) - 1}{Path(clip_files[-1]).suffix or '.mp4'}"
    g.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.1", "-i", last, "-frames:v", "1", "-q:v", "2", work / "end.jpg"])

    total = t0 + END_CARD
    props = {
        "fps": g.FPS, "durationInFrames": int(total * g.FPS), "audio": None, "music": None,
        "hook": {"text": "", "end": 0},
        "title": {"series": season["title"], "episode": f"სერია {ep['n']}", "end": 2.4},
        "endCard": {"start": round(t0, 3), "text": ep.get("next", "გაგრძელება იქნება..."), "sub": "გამოიწერე, რომ არ გამოგრჩეს"},
        "endStill": "end.jpg",
        "clips": clips, "words": [], "subs": subs, "cards": cards, "overlays": [], "sfx": sfx,
        "flashes": [], "glitches": [], "shakes": [], "mood": "bright", "duck": duck, "cinema": True,
        "_total": total,
    }
    g.render(props, work, final)
    return total


# ----------------------------------------------------------------- telegram

def tg(method, **data):
    """Telegram call with retries (connections from CI runners sometimes get reset)."""
    import time
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    for attempt in range(5):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=120)
            if r.status_code == 429:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)) + 1)
                continue
            r.raise_for_status()
            return r.json()["result"]
        except requests.ConnectionError as e:
            g.log(f"Telegram {method} attempt {attempt + 1} failed: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Telegram {method} failed after retries")


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


def collect(season, state, do_render=True, wait=0):
    chat = str(os.environ["TELEGRAM_CHAT_ID"])
    updates = tg("getUpdates", offset=state["last_update_id"] + 1, timeout=wait,
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
    try:
        cover = make_cover(season, ep, files, final.with_suffix(".cover.jpg"))
        with open(cover, "rb") as f:
            requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                          data={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                                "caption": "🖼️ ყდა (cover): TikTok-ში „Edit cover“ → ატვირთე ეს სურათი"},
                          files={"photo": f}, timeout=120).raise_for_status()
        with open(cover, "rb") as f:  # also as a file, full quality
            requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                          data={"chat_id": os.environ["TELEGRAM_CHAT_ID"]},
                          files={"document": (f"cover_ep{ep['n']:02d}.jpg", f, "image/jpeg")}, timeout=120)
    except Exception as e:
        g.log(f"cover failed: {e}")
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
    try:
        if cmd == "prompts":
            send_prompts(season, state["next_episode"], state)
        else:
            if state.get("prompts_sent_for") != state["next_episode"]:
                send_prompts(season, state["next_episode"], state)
            if cmd == "check":
                # listen for a while (long polling) so the bot answers within seconds
                import time
                end = time.time() + int(os.getenv("LISTEN_SECONDS", "0"))
                while not collect(season, state, do_render=False, wait=25 if time.time() < end else 0):
                    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")
                    if time.time() >= end:
                        break
            else:
                collect(season, state)
    finally:  # never lose the Telegram offset / received clips
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()

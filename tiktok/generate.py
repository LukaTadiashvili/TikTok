"""Daily Georgian TikTok video generator.

script (scripts/bank.json)
 -> voice: ElevenLabs (realistic, emotional) with exact word timings
           fallback: free edge-tts, then silent
 -> footage: one stock clip per spoken phrase (Pixabay / Pexels)
 -> render (Remotion, render/): camera moves, word-by-word captions, hook title,
    emoji / number / keyword pop-ups, progress bar, flashes, sound effects
 -> Telegram

Usage: python generate.py [--script S005] [--niche facts] [--no-send]
"""

import argparse
import base64
import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests
from PIL import Image, ImageFilter

ROOT = Path(__file__).parent
RENDER = ROOT / "render"
BANK = Path(os.getenv("TIKTOK_BANK") or ROOT / "scripts/bank.json")
HISTORY = ROOT / "data/history.json"
OUT = ROOT / "output"
CACHE = OUT / "cache"
W, H, FPS = 1080, 1920, 30
TBILISI = dt.timezone(dt.timedelta(hours=4))
EDGE_VOICES = ["ka-GE-EkaNeural"]  # female
TAG = re.compile(r"\[[^\]]*\]")


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def run(cmd, cwd=None):
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# -------------------------------------------------------------------- script

def pick_script(history, script_id=None, niche=None):
    """Next unused script; the niche with the fewest videos so far goes first."""
    bank = json.loads(BANK.read_text())
    if script_id:
        return next(s for s in bank if s["id"] == script_id), bank
    used = {h.get("script_id") for h in history}
    niche = niche or os.getenv("LOCK_NICHE") or None
    fresh = [s for s in bank if s["id"] not in used and (not niche or s["niche"] == niche)]
    if not fresh:
        return None, bank
    priority = os.getenv("PRIORITY_NICHE")
    if priority and any(s["niche"] == priority for s in fresh):
        fresh = [s for s in fresh if s["niche"] == priority]
        return fresh[0], bank  # priority series goes in order
    count = {}
    for h in history:
        count[h["niche"]] = count.get(h["niche"], 0) + 1
    low = min(count.get(s["niche"], 0) for s in fresh)
    return random.choice([s for s in fresh if count.get(s["niche"], 0) == low]), bank


def plain(text):
    """Text as shown/spoken: no *emphasis* marks, no [audio tags]."""
    return " ".join(TAG.sub("", text).replace("*", "").split())


def caption_words(beats):
    """[(word, emph, beat_index)] in speaking order."""
    out = []
    for b, beat in enumerate(beats):
        for i, part in enumerate(TAG.sub("", beat["say"]).split("*")):
            for w in part.split():
                out.append((w, i % 2 == 1, b))
    return out


# --------------------------------------------------------------------- voice

def eleven_model(key):
    """Most expressive ElevenLabs model that lists Georgian (ka)."""
    forced = os.getenv("ELEVENLABS_MODEL")
    if forced:
        return forced
    r = requests.get("https://api.elevenlabs.io/v1/models", headers={"xi-api-key": key}, timeout=30)
    r.raise_for_status()
    ka = [m["model_id"] for m in r.json()
          if m.get("can_do_text_to_speech") and any(l.get("language_id") == "ka" for l in m.get("languages", []))]
    for pref in ("v4", "v3", "multilingual"):
        for m in ka:
            if pref in m and "flash" not in m and "turbo" not in m:
                return m
    return ka[0] if ka else "eleven_v3"


def eleven_auto_voices(key):
    """No voices configured: take the most-used Georgian voices from the ElevenLabs library."""
    hdr = {"xi-api-key": key}
    mine = requests.get("https://api.elevenlabs.io/v1/voices", headers=hdr, timeout=30).json().get("voices", [])
    ka_mine = [v["voice_id"] for v in mine if (v.get("labels") or {}).get("language") == "ka"
               or "georgian" in (v.get("name", "") + json.dumps(v.get("labels") or {})).lower()]
    if ka_mine:
        return ka_mine[:2]
    r = requests.get("https://api.elevenlabs.io/v1/shared-voices", headers=hdr, timeout=30,
                     params={"language": "ka", "page_size": 10, "sort": "usage_character_count_1y"})
    r.raise_for_status()
    picked = []
    for v in r.json().get("voices", [])[:2]:
        add = requests.post(f"https://api.elevenlabs.io/v1/voices/add/{v['public_owner_id']}/{v['voice_id']}",
                            headers=hdr, json={"new_name": f"georgian - {v.get('name', 'voice')}"}, timeout=30)
        if add.ok:
            picked.append(add.json().get("voice_id", v["voice_id"]))
            log(f"Added Georgian library voice: {v.get('name')}")
    return picked


def eleven_voice(key, path, text_with_tags):
    voices = [v for v in (os.getenv("ELEVENLABS_VOICES") or "").split(",") if v.strip()]
    if not voices:
        voices = json.loads((ROOT / "voices.json").read_text()).get("elevenlabs", [])
    if not voices:
        voices = eleven_auto_voices(key)
    if not voices:
        log("No Georgian ElevenLabs voice found - set ELEVENLABS_VOICES")
        return None
    voice = random.choice(voices).strip()
    model = eleven_model(key)
    tags_ok = "v3" in model or "v4" in model
    text = text_with_tags if tags_ok else plain(text_with_tags)
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": text, "model_id": model, "language_code": "ka",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
        timeout=180)
    if r.status_code == 400 and "language_code" in r.text:  # older models reject language_code
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={"text": text, "model_id": model, "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
            timeout=180)
    r.raise_for_status()
    data = r.json()
    path.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or data.get("normalized_alignment") or {}
    words, cur, s, e, in_tag = [], "", 0.0, 0.0, False
    for c, a, b in zip(al.get("characters", []), al.get("character_start_times_seconds", []),
                       al.get("character_end_times_seconds", [])):
        if c == "[":
            in_tag = True
        if in_tag:
            in_tag = c != "]"
            continue
        if c.isspace() or c == "*":
            if cur:
                words.append((cur, s, e))
                cur = ""
            continue
        if not cur:
            s = a
        cur, e = cur + c, b
    if cur:
        words.append((cur, s, e))
    return f"ElevenLabs/{model}", words


GEMINI_VOICES = ["Zephyr", "Kore", "Leda", "Aoede"]  # female voices


def gemini_voice(key, path, beats, targets):
    """Free Gemini API voice (Georgian is a preview language). One request for the whole script;
    beat boundaries come from the pauses in the audio, words are spread inside each beat."""
    model = os.getenv("GEMINI_TTS_MODEL") or "gemini-2.5-flash-preview-tts"
    voice = os.getenv("GEMINI_VOICE") or random.choice(GEMINI_VOICES)
    lines = "\n".join((f"[{b['tone']}] " if b.get("tone") else "") + plain(b["say"]) for b in beats)
    prompt = ("You are a young Georgian woman, a hugely popular TikTok storyteller. Perform this voiceover in "
              "Georgian with BIG, genuine emotion, like you are telling a friend the most surprising thing you "
              "just learned: gasp, smile, lower your voice for secrets, rise with excitement, punch the key words, "
              "never sound like you are reading. Start the first line with intense energy so nobody scrolls away. "
              "Keep a fast, lively TikTok pace and make a short clear pause after each line. The words in "
              "[brackets] are emotion directions: act them out but never read them aloud.\n\n" + lines)
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                  "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}},
        timeout=300)
    r.raise_for_status()
    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = path.with_suffix(".pcm")
    pcm.write_bytes(base64.b64decode(part["data"]))
    rate = re.search(r"rate=(\d+)", part.get("mimeType", "")) or None
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", rate.group(1) if rate else "24000",
         "-ac", "1", "-i", pcm, "-af", "silenceremove=start_periods=1:start_threshold=-45dB", "-b:a", "160k", path])
    return f"Gemini/{voice}", words_from_pauses(path, beats, targets)


def words_from_pauses(path, beats, targets):
    total = duration(path)
    out = subprocess.run(["ffmpeg", "-i", str(path), "-af", "silencedetect=noise=-38dB:d=0.15", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    gaps = [(e - s, (s + e) / 2) for s, e in zip(starts, ends) if 0.2 < s and e < total - 0.2]
    n = len(beats)
    chars = [len(plain(b["say"])) for b in beats]
    if len(gaps) >= n - 1:
        cuts = sorted(mid for _, mid in sorted(gaps, reverse=True)[:n - 1])
    else:  # not enough clear pauses: split by text length
        cuts, acc = [], 0
        for c in chars[:-1]:
            acc += c
            cuts.append(total * acc / sum(chars))
    bounds = [0.0] + cuts + [total]
    words = []
    for b in range(n):
        ws = [w for w, _, bb in targets if bb == b]
        a, z = bounds[b] + 0.05, bounds[b + 1] - 0.1
        weights = [len(w) + 1 for w in ws]
        t = a
        for w, wt in zip(ws, weights):
            d = (z - a) * wt / sum(weights)
            words.append((w, t, t + d))
            t += d
    return words


def edge_voice(path, text, voice):
    if os.getenv("DISABLE_EDGE_TTS"):
        return None
    import asyncio
    import edge_tts

    async def go():
        words = []
        com = edge_tts.Communicate(text, voice, rate="+10%", boundary="WordBoundary")
        with open(path, "wb") as f:
            async for ch in com.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":
                    st = ch["offset"] / 1e7
                    words.append((ch["text"], st, st + ch["duration"] / 1e7))
        return words

    words = asyncio.run(go())
    return (f"edge/{voice}", words) if path.exists() and path.stat().st_size > 1000 else None


def make_voice(script, work):
    """Returns (label, audio_path or None, timed words matching caption_words)."""
    targets = caption_words(script["beats"])
    tagged = " ".join((f"[{b['tone']}] " if b.get("tone") else "") + b["say"].replace("*", "")
                      for b in script["beats"])
    audio = work / "voice.mp3"
    result = None
    key = os.getenv("ELEVENLABS_API_KEY")
    if key:
        try:
            result = eleven_voice(key, audio, tagged)
        except Exception as e:
            log(f"ElevenLabs failed: {e}")
    gkey = os.getenv("GEMINI_API_KEY")
    if not result and gkey:
        try:
            result = gemini_voice(gkey, audio, script["beats"], targets)
        except Exception as e:
            log(f"Gemini TTS failed: {e}")
    if not result:
        try:
            result = edge_voice(audio, plain(tagged), random.choice(EDGE_VOICES))
        except Exception as e:
            log(f"edge-tts failed: {e}")
    if result:
        label, got = result
        total = duration(audio)
        return label, audio, align(targets, got, total)
    # no voice at all: reading-speed timing
    t, timed = 0.3, []
    for w, emph, b in targets:
        d = 0.16 + 0.055 * len(w)
        timed.append((w, emph, b, t, t + d))
        t += d + (0.25 if w[-1] in ".!?" else 0.04)
    return "none", None, timed


def norm(w):
    return re.sub(r"[^\w]", "", w.lower())


def align(targets, got, total):
    """Map caption words onto spoken word timings (counts can differ slightly)."""
    if got and len(got) == len(targets):
        return [(w, e, b, s, en) for (w, e, b), (_, s, en) in zip(targets, got)]
    if got:  # greedy match by normalized text, fill gaps by interpolation
        out, j = [], 0
        for w, e, b in targets:
            k = next((i for i in range(j, min(j + 4, len(got))) if norm(got[i][0]) == norm(w)), None)
            if k is not None:
                out.append([w, e, b, got[k][1], got[k][2]])
                j = k + 1
            else:
                out.append([w, e, b, None, None])
        known = [i for i, o in enumerate(out) if o[3] is not None]
        for i, o in enumerate(out):
            if o[3] is None:
                prev = max([k for k in known if k < i], default=None)
                nxt = min([k for k in known if k > i], default=None)
                a = out[prev][4] if prev is not None else 0.0
                z = out[nxt][3] if nxt is not None else total
                gap = [x for x in range(prev + 1 if prev is not None else 0, nxt if nxt is not None else len(out))]
                step = (z - a) / max(1, len(gap))
                pos = gap.index(i)
                o[3], o[4] = a + step * pos, a + step * (pos + 1)
        return [tuple(o) for o in out]
    # proportional
    weights = [len(w) + 1 for w, _, _ in targets]
    t, out = 0.0, []
    for (w, e, b), wt in zip(targets, weights):
        d = total * wt / sum(weights)
        out.append((w, e, b, t, t + d))
        t += d
    return out


# ------------------------------------------------------------------- footage

def download(url, path):
    if not path.exists():
        with requests.get(url, stream=True, timeout=180) as d:
            d.raise_for_status()
            tmp = path.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in d.iter_content(1 << 20):
                    f.write(chunk)
            tmp.rename(path)
    return path


def pixabay_video(query, used, min_len):
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return None
    r = requests.get("https://pixabay.com/api/videos/", timeout=30, params={
        "key": key, "q": query[:100], "per_page": 30, "safesearch": "true", "order": "popular"})
    r.raise_for_status()
    hits = [h for h in r.json().get("hits", []) if h["id"] not in used and h.get("duration", 0) >= min_len]
    top = hits[:6]
    random.shuffle(top)
    for h in top:
        sizes = h.get("videos", {})
        options = [sizes[k] for k in ("medium", "large", "small") if sizes.get(k, {}).get("url")]

        # horizontal clips lose most of their width in the 9:16 crop, so they need ~4K to stay sharp
        def sharp(v):
            return v["width"] >= 1080 if v["height"] > v["width"] else v["height"] >= 1900
        options.sort(key=lambda v: (not sharp(v), v["width"] * v["height"] * (1 if sharp(v) else -1)))
        if not options:
            continue
        used.add(h["id"])
        path = download(options[0]["url"], CACHE / f"pixabay_{h['id']}_{options[0]['height']}.mp4")
        return path, float(h["duration"])
    return None


def pexels_video(query, used, min_len):
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return None
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key}, timeout=30,
                     params={"query": query, "per_page": 15, "orientation": "portrait"})
    r.raise_for_status()
    vids = [v for v in r.json().get("videos", []) if v["id"] not in used and v["duration"] >= min_len]
    for v in vids[:6]:
        files = [f for f in v["video_files"] if f.get("height") and f.get("file_type") == "video/mp4"]
        files.sort(key=lambda f: abs(f["height"] - 1920))
        if files:
            used.add(v["id"])
            return download(files[0]["link"], CACHE / f"pexels_{v['id']}.mp4"), float(v["duration"])
    return None


def stock_video(query, used, min_len):
    for q in dict.fromkeys([query, " ".join(query.split()[-2:]), query.split()[-1]]):
        for source in (pixabay_video, pexels_video):
            try:
                got = source(q, used, min_len)
            except requests.RequestException as e:
                log(f"{source.__name__} failed for '{q}': {e}")
                got = None
            if got:
                return got
    return None


IMAGE_STYLE = ("cinematic film still, dramatic moody lighting, high contrast, deep shadows, "
               "teal and orange color grade, 35mm photo, film grain, ultra detailed, photorealistic, "
               "vertical composition, no text, no letters, no watermark")


def ai_image(prompt, path, seed):
    """Pollinations: with POLLINATIONS_API_KEY full-size images on a free/cheap model,
    otherwise the anonymous endpoint (smaller image with a small logo)."""
    from urllib.parse import quote
    import hashlib
    tier = "key" if os.getenv("POLLINATIONS_API_KEY") else "anon"
    cached = CACHE / f"img_{hashlib.md5(f'{prompt}|{seed}|{tier}'.encode()).hexdigest()}.jpg"
    if cached.exists():
        shutil.copy(cached, path)
        return True
    full = quote(f"{prompt}, {IMAGE_STYLE}", safe="")
    key = os.getenv("POLLINATIONS_API_KEY")
    if key:
        model = os.getenv("POLLINATIONS_MODEL") or "zimage"
        url = f"https://gen.pollinations.ai/image/{full}"
        params = {"model": model, "width": 1080, "height": 1920, "seed": seed, "nologo": "true"}
        headers = {"Authorization": f"Bearer {key}"}
    else:
        url = f"https://image.pollinations.ai/prompt/{full}"
        params = {"width": 1080, "height": 1920, "seed": seed, "nologo": "true", "model": "flux"}
        headers = {}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=180)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                tmp = path.with_suffix(".src")
                tmp.write_bytes(r.content)
                # normalize to exact 1080x1920 (cover) as JPEG
                img = Image.open(tmp).convert("RGB")
                scale = max(W / img.width, H / img.height)
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
                left, top = (img.width - W) // 2, (img.height - H) // 2
                img.crop((left, top, left + W, top + H)).save(path, quality=92)
                shutil.copy(path, cached)
                return True
            log(f"image attempt {attempt + 1}: HTTP {r.status_code}")
        except (requests.RequestException, OSError) as e:
            log(f"image attempt {attempt + 1} failed: {e}")
    return False


PALETTES = [((255, 61, 104), (255, 179, 71)), ((58, 123, 213), (0, 210, 255)),
            ((131, 58, 180), (253, 29, 29)), ((17, 153, 142), (56, 239, 125))]


def gradient(path, seed):
    a, b = PALETTES[seed % len(PALETTES)]
    small = Image.new("RGB", (8, 64))
    small.putdata([tuple(int(a[i] + (b[i] - a[i]) * (y / 63 * 0.75 + x / 7 * 0.25)) for i in range(3))
                   for y in range(64) for x in range(8)])
    small.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(30)).save(path)


def prep_clip(src, src_len, length, out):
    """Trim a random section and normalize to 1080x1920@30 so the renderer just plays it."""
    start = random.uniform(0.3, src_len - length - 0.3) if src_len > length + 0.8 else 0
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{length + 0.3:.2f}", "-i", src,
         "-vf", f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1",
         "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out])


# --------------------------------------------------------------------- sound

SFX = {
    "pop": "sine=f=900:d=0.12,asetrate=44100*1.0,afade=t=out:st=0.02:d=0.1,volume=0.7",
    "whoosh": "anoisesrc=d=0.4:c=pink:a=0.6,highpass=f=600,lowpass=f=5000,afade=t=in:d=0.18,afade=t=out:st=0.18:d=0.22,volume=0.5",
    "hit": "sine=f=50:d=0.7,afade=t=out:st=0.02:d=0.65,volume=3.5",
    "ding": "sine=f=1320:d=0.5,afade=t=out:st=0.02:d=0.45,volume=0.45",
    "tick": "sine=f=2400:d=0.03,volume=0.25",
    "riser": "anoisesrc=d=1.6:c=white:a=0.5,highpass=f=300,lowpass=f=8000,afade=t=in:d=1.5:curve=exp,afade=t=out:st=1.5:d=0.1,volume=0.6",
    "boom": "sine=f=38:d=1.6,afade=t=out:st=0.05:d=1.5,volume=5,acompressor",
    "heartbeat": "sine=f=48:d=0.16,afade=t=out:st=0.02:d=0.14,volume=4,apad=pad_dur=0.12,aloop=loop=1:size=13000,apad=pad_dur=0.55,aloop=loop=2:size=40000",
    "glitch": "anoisesrc=d=0.25:c=white:a=0.7,tremolo=f=40:d=1,highpass=f=1000,volume=0.5",
}


def make_sfx(work, total):
    d = work / "sfx"
    d.mkdir(exist_ok=True)
    for name, f in SFX.items():
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f, "-ar", "44100", "-ac", "2", d / f"{name}.wav"])
    # dark ambient bed: low drone + filtered noise, slowly pulsing
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"sine=f=55:d={total:.2f}", "-f", "lavfi", "-i", f"sine=f=82.4:d={total:.2f}",
         "-f", "lavfi", "-i", f"anoisesrc=d={total:.2f}:c=brown:a=0.3",
         "-filter_complex", "[0][1][2]amix=inputs=3:normalize=0,lowpass=f=400,tremolo=f=0.25:d=0.5,"
         f"afade=t=in:d=1.5,afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5,volume=0.8",
         "-ar", "44100", "-ac", "2", d / "drone.wav"])


# ---------------------------------------------------------------------- plan

def build(script, work, history):
    label, audio, timed = make_voice(script, work)
    beats = script["beats"]
    n = len(beats)
    b_start = [min(t[3] for t in timed if t[2] == b) for b in range(n)]
    total = (max(t[4] for t in timed) if timed else 10) + 0.7
    b_end = b_start[1:] + [total]
    b_start[0] = 0.0
    log(f"Voice: {label}, {total:.1f}s")

    # caption pages: 1-3 words, break on punctuation and beat change
    words, page, cnt, prev_b = [], 0, 0, 0
    for w, emph, b, s, e in timed:
        if cnt and (cnt >= 3 or b != prev_b or sum(len(x["text"]) for x in words if x["page"] == page) + len(w) > 15):
            page, cnt = page + 1, 0
        words.append({"text": w, "start": round(s, 3), "end": round(e, 3), "emph": emph, "page": page})
        cnt, prev_b = cnt + 1, b
        if w[-1] in ".!?,:":
            page, cnt = page + 1, 0

    # footage: one shot per beat, two if the beat is long
    used, clips, real = set(), [], 0
    moves = ["push", "drift", "pull", "push", "drift"]
    (work / "clips").mkdir(exist_ok=True)
    jobs = []  # (beat, part, a, z, name)
    for b, beat in enumerate(beats):
        st, en = b_start[b], b_end[b]
        parts = 2 if en - st > 3.2 else 1
        for j in range(parts):
            jobs.append((b, j, st + (en - st) * j / parts, st + (en - st) * (j + 1) / parts, f"clips/b{b}_{j}"))

    def visual(job):
        b, j, a, z, name = job
        beat = beats[b]
        if beat.get("image"):
            prompt = beat["image"] if j == 0 else beat.get("image2") or f"extreme close-up detail, {beat['image']}"
            if ai_image(prompt, work / f"{name}.jpg", seed=(b * 31 + j * 7 + sum(map(ord, script["id"]))) % 100000):
                return f"{name}.jpg", True
        if beat.get("shot"):
            queries = beat["shot"] if isinstance(beat["shot"], list) else [beat["shot"]]
            got = stock_video(queries[j % len(queries)], used, z - a + 0.8)
            if got:
                prep_clip(got[0], got[1], z - a, work / f"{name}.mp4")
                return f"{name}.mp4", True
        gradient(work / f"{name}.png", b * 2 + j + len(history))
        return f"{name}.png", False

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(visual, jobs))
    for (b, j, a, z, _), (src, ok) in zip(jobs, results):
        real += ok
        clips.append({"src": src, "start": round(a, 3), "end": round(z, 3),
                      "move": "punch" if j == 0 else moves[(b + j) % len(moves)]})
    log(f"Footage: {len(clips)} shots, {real} real")

    # pop-ups + sound effects
    overlays, sfx = [], [{"src": "sfx/hit.wav", "start": 0.0, "volume": 0.9}]
    for b, beat in enumerate(beats):
        st, en = b_start[b], b_end[b]
        if b:
            sfx.append({"src": "sfx/whoosh.wav", "start": max(0, st - 0.15), "volume": 0.5})
        pop = beat.get("pop")
        if pop:
            at = st + 0.15 if b else 0.6
            o = {**pop, "start": round(at, 3), "end": round(max(en - 0.05, at + 1.2), 3), "slot": b}
            overlays.append(o)
            sfx.append({"src": "sfx/ding.wav" if pop["type"] == "number" else "sfx/pop.wav",
                        "start": at, "volume": 0.6})
    for w in words:
        if w["emph"]:
            sfx.append({"src": "sfx/tick.wav", "start": w["start"], "volume": 0.5})
    flashes, glitches, shakes = [], [], []
    for b, beat in enumerate(beats):
        st, en = b_start[b], b_end[b]
        fx = beat.get("fx", [])
        if "riser" in fx:
            sfx.append({"src": "sfx/riser.wav", "start": max(0, st - 1.6), "volume": 0.6})
        if "boom" in fx:
            sfx.append({"src": "sfx/boom.wav", "start": st, "volume": 0.9})
            flashes.append(st)
            shakes.append([st, st + 0.5])
        if "heartbeat" in fx:
            sfx.append({"src": "sfx/heartbeat.wav", "start": st, "volume": 0.8})
        if "glitch" in fx:
            sfx.append({"src": "sfx/glitch.wav", "start": st, "volume": 0.6})
            glitches.append(st)
        if "shake" in fx:
            shakes.append([st, min(en, st + 0.8)])
    if not any(beat.get("fx") for beat in beats):
        flashes = [b_start[b] for b in range(1, n) if b % 2 == 0]
    mood = script.get("mood", "bright")
    if mood == "dark":
        sfx.append({"src": "sfx/drone.wav", "start": 0, "volume": 0.35})

    music = sorted((ROOT / "assets/music").glob("*.mp3"))
    music_src = None
    if music:
        shutil.copy(random.choice(music), work / "music.mp3")
        music_src = "music.mp3"
    hook_end = b_end[0] if n > 1 else min(total, 3)
    props = {
        "fps": FPS, "durationInFrames": int(total * FPS), "audio": "voice.mp3" if audio else None,
        "music": music_src, "hook": {"text": script["hook_text"], "end": round(max(hook_end, 1.8), 3)},
        "clips": clips, "words": words, "overlays": overlays, "sfx": sfx, "flashes": flashes,
        "glitches": glitches, "shakes": shakes, "mood": mood,
    }
    props["_total"] = total
    return props, label, total, len(clips), real


def render(props, work, final):
    shutil.copy(ROOT / "assets/fonts/TikTokGeo.ttf", work / "TikTokGeo.ttf")
    make_sfx(work, props.pop("_total"))
    (work / "props.json").write_text(json.dumps(props, ensure_ascii=False))
    cmd = ["npx", "remotion", "render", "src/index.ts", "Main", str(final),
           f"--props={(work / 'props.json').resolve()}", f"--public-dir={work.resolve()}",
           "--codec=h264", "--crf=21", "--log=error"]
    if os.getenv("REMOTION_BROWSER"):
        cmd.append(f"--browser-executable={os.getenv('REMOTION_BROWSER')}")
    if os.getenv("REMOTION_CONCURRENCY"):
        cmd.append(f"--concurrency={os.getenv('REMOTION_CONCURRENCY')}")
    run(cmd, cwd=RENDER)


# ------------------------------------------------------------------ telegram

def telegram(method, data, files=None):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}",
                      data={"chat_id": chat, **data}, files=files, timeout=300)
    r.raise_for_status()
    return True


def send_telegram(video, info_text, caption):
    if not telegram("sendMessage", {"text": info_text}):
        log("No Telegram credentials - skipping delivery")
        return False
    with open(video, "rb") as f:
        telegram("sendVideo", {"supports_streaming": "true", "width": W, "height": H}, files={"video": f})
    telegram("sendMessage", {"text": caption})
    return True


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script")
    ap.add_argument("--niche")
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--no-log", action="store_true", help="test run: don't record in history")
    args = ap.parse_args()

    history = json.loads(HISTORY.read_text())
    script, bank = pick_script(history, args.script, args.niche)
    if script is None:
        telegram("sendMessage", {"text": "⚠️ სცენარები დამთავრდა - სთხოვე Claude-ს ახლების დაწერა"})
        sys.exit("Script bank is empty - add new scripts to scripts/bank.json")
    used_ids = {h.get("script_id") for h in history} | {script["id"]}
    left = len([s for s in bank if s["id"] not in used_ids])

    vid = f"V{len(history) + 1:03d}"
    today = dt.datetime.now(TBILISI).date().isoformat()
    log(f"{vid}: {script['id']} '{script['title']}' niche={script['niche']} hook={script['hook_type']}")
    work = OUT / f"{today}_{vid}"
    work.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    props, voice, total, shots, real = build(script, work, history)
    final = (OUT / f"{today}_{vid}.mp4").resolve()
    render(props, work, final)
    log(f"Video ready: {final}")

    caption = f"{script['caption']}\n\n{' '.join(script['hashtags'])}"
    info = (f"🎬 {vid} | {today}\n"
            f"თემა: {script['niche']} | ჰუკი: {script['hook_type']}\n"
            f"„{script['title']}“ · {total:.0f} წმ · {shots} კადრი · ხმა: {voice.split('/')[0]}\n"
            + ("" if real else "🎨 ვიდეო-კადრები ვერ მოიძებნა - ფონები გრადიენტია\n")
            + f"📚 დარჩენილი სცენარები: {left}\n"
            + f"📊 2 დღეში ჩაწერე ნახვები data/results.csv-ში (ID: {vid})")
    sent = False if args.no_send else send_telegram(final, info, caption)
    if left <= 5:
        telegram("sendMessage", {"text": f"⚠️ მხოლოდ {left} სცენარი დარჩა - სთხოვე Claude-ს ახლების დაწერა"})

    if not args.no_log:
        history.append({"id": vid, "date": today, "script_id": script["id"], "niche": script["niche"],
                        "hook_type": script["hook_type"], "voice": voice, "title": script["title"],
                        "seconds": round(total, 1), "shots": shots, "real_footage": real, "sent": sent})
        HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")
    log("Done")


if __name__ == "__main__":
    main()

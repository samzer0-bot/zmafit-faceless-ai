"""Render one faceless vertical video for ZMAFIT.

Inputs come from environment variables (set by the GitHub Actions workflow):
  JOB_ID            unique id for this video
  AUDIO_URL         public URL of the voiceover (wav/mp3)
  SCRIPT_B64 / SCRIPT            voiceover text (used to guide subtitles)
  HOOK_B64 / HOOK                on-screen hook for the first seconds
  VIDEO_SEARCH_B64 / VIDEO_SEARCH  Pexels search phrase
  TITLE_B64, CAPTION_B64         passed through to Make
  PEXELS_API_KEY    Pexels API key (GitHub secret)

Output: work/final.mp4 and work/meta.json. used_clips.json is updated so the
same stock clip is never used twice.
"""
import base64
import json
import os
import random
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

W, H, FPS = 1080, 1920, 30
ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
FONTS = ROOT / "fonts"
USED_FILE = ROOT / "used_clips.json"

FALLBACK_QUERIES = [
    "home workout", "woman workout", "man workout", "dumbbell training",
    "gym training", "healthy meal prep", "running outdoors", "bodyweight exercise",
    "fitness motivation", "stretching", "jump rope", "kettlebell", "squats",
    "push ups", "healthy breakfast", "yoga mat workout",
]

# Colours are ASS format &HAABBGGRR
TEMPLATES = [
    {"name": "anton-yellow", "font": "Anton", "size": 104, "hl": "&H003FD2FF",
     "box": False, "margin_v": 620, "upper": True,
     "grade": "eq=contrast=1.06:saturation=1.12", "cta_box": "&H00305AFF"},
    {"name": "poppins-green", "font": "Poppins ExtraBold", "size": 76, "hl": "&H0050C83D",
     "box": True, "margin_v": 520, "upper": False,
     "grade": "eq=contrast=1.04:saturation=1.05:brightness=0.01", "cta_box": "&H00506E0D"},
    {"name": "bebas-coral", "font": "Bebas Neue", "size": 132, "hl": "&H004E5AFF",
     "box": False, "margin_v": 860, "upper": True,
     "grade": "eq=contrast=1.08:saturation=0.95", "cta_box": "&H004E5AFF"},
    {"name": "archivo-cyan", "font": "Archivo Black", "size": 82, "hl": "&H00FFE03F",
     "box": True, "margin_v": 440, "upper": False,
     "grade": "eq=contrast=1.05:saturation=1.18", "cta_box": "&H00A07A1E"},
]


def text_input(name):
    raw = os.environ.get(name + "_B64", "").strip()
    if raw:
        try:
            return base64.b64decode(raw).decode("utf-8").strip()
        except Exception:
            pass
    return os.environ.get(name, "").strip()


def run(cmd, cwd=None):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "zmafit-faceless-ai", **(headers or {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def media_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def word_timings(audio, script):
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio), language="en", word_timestamps=True,
                                       initial_prompt=script[:220] or None)
        words = [(w.start, w.end, w.word.strip()) for s in segments for w in (s.words or []) if w.word.strip()]
        if words:
            return words
    except Exception as e:  # fall back to evenly spaced words
        print("whisper failed:", e, flush=True)
    total = media_duration(audio)
    tokens = script.split() or ["..."]
    step = total / len(tokens)
    return [(i * step, (i + 1) * step, t) for i, t in enumerate(tokens)]


def best_file(video):
    files = [f for f in video.get("video_files", [])
             if f.get("link") and (f.get("height") or 0) >= (f.get("width") or 0) and (f.get("height") or 0) >= 1280]
    if not files:
        return None
    return min(files, key=lambda f: abs((f.get("height") or 0) - 1920))


def pick_clips(query, need, used):
    key = os.environ["PEXELS_API_KEY"]
    queries = [query] if query else []
    extra = FALLBACK_QUERIES[:]
    random.shuffle(extra)
    queries += extra
    picked = []
    for q in queries:
        for _ in range(3):
            params = urllib.parse.urlencode({"query": q, "orientation": "portrait", "per_page": 15,
                                             "page": random.randint(1, 5), "size": "medium"})
            try:
                data = json.loads(fetch("https://api.pexels.com/videos/search?" + params, {"Authorization": key}))
            except Exception as e:
                print("pexels error:", e, flush=True)
                continue
            videos = data.get("videos", [])
            random.shuffle(videos)
            for v in videos:
                if v["id"] in used or any(p["id"] == v["id"] for p in picked):
                    continue
                f = best_file(v)
                if f:
                    picked.append({"id": v["id"], "url": f["link"], "duration": float(v.get("duration") or 8)})
                if len(picked) >= need:
                    return picked
    return picked


def ass_escape(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words, hook, cta, total, t):
    white, black = "&H00FFFFFF", "&H00000000"
    border_style = 3 if t["box"] else 1
    sub_outline = "&H96000000" if t["box"] else black
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{t['font']},{t['size']},{white},{white},{sub_outline},&H64000000,-1,0,0,0,100,100,1,0,"
        f"{border_style},{14 if t['box'] else 7},2,2,90,90,{t['margin_v']},1",
        f"Style: Hook,{t['font']},{int(t['size'] * 1.05)},{white},{white},&HB4000000,&H00000000,-1,0,0,0,100,100,1,0,"
        f"3,22,0,8,80,80,300,1",
        f"Style: CTA,{t['font']},{int(t['size'] * 0.85)},{white},{white},{t['cta_box']},&H00000000,-1,0,0,0,100,100,1,0,"
        f"3,26,0,5,90,90,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def ts(sec):
        sec = max(0.0, sec)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h)}:{int(m):02d}:{s:05.2f}"

    def fmt(w):
        w = ass_escape(w)
        return w.upper() if t["upper"] else w

    # group words into short chunks, breaking after punctuation
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 3 or w[2][-1:] in ".,!?;:":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    cta_start = max(0.0, total - 3.4)
    for ci, chunk in enumerate(chunks):
        next_chunk_start = chunks[ci + 1][0][0] if ci + 1 < len(chunks) else chunk[-1][1] + 0.25
        for wi, (start, end, _) in enumerate(chunk):
            stop = chunk[wi + 1][0] if wi + 1 < len(chunk) else min(next_chunk_start, end + 0.35)
            stop = max(stop, start + 0.06)
            if start >= cta_start:
                continue
            stop = min(stop, cta_start)
            parts = []
            for wj, (_, _, txt) in enumerate(chunk):
                if wj == wi:
                    parts.append("{\\c" + t["hl"] + "\\fscx108\\fscy108}" + fmt(txt) + "{\\c" + white + "\\fscx100\\fscy100}")
                else:
                    parts.append(fmt(txt))
            lines.append(f"Dialogue: 1,{ts(start)},{ts(stop)},Sub,,0,0,0,,{' '.join(parts)}")

    if hook:
        h = ass_escape(hook.upper() if t["upper"] else hook)
        lines.append(f"Dialogue: 2,{ts(0)},{ts(2.9)},Hook,,0,0,0,,{{\\fad(120,200)}}{h}")
    c = ass_escape(cta).replace("|", "\\N")
    lines.append(f"Dialogue: 2,{ts(cta_start)},{ts(total)},CTA,,0,0,0,,{{\\fad(200,0)}}{c}")
    return "\n".join(lines) + "\n"


def main():
    WORK.mkdir(exist_ok=True)
    job = os.environ.get("JOB_ID") or "manual"
    script = text_input("SCRIPT")
    hook = text_input("HOOK")
    query = text_input("VIDEO_SEARCH")
    title = text_input("TITLE")
    caption = text_input("CAPTION")
    cta = os.environ.get("CTA") or "Build YOUR plan in 3 min|link in bio"

    random.seed(job + str(random.random()))
    t = random.choice(TEMPLATES)
    print("template:", t["name"], flush=True)

    audio = WORK / "voice.audio"
    audio.write_bytes(fetch(os.environ["AUDIO_URL"]))
    run(["ffmpeg", "-y", "-i", audio, "-ar", "48000", "-ac", "2", WORK / "voice.wav"])
    audio = WORK / "voice.wav"
    voice_len = media_duration(audio)
    total = voice_len + 0.6

    # cut lengths between 2.6 and 4.4 seconds keep the pace up
    cuts, acc = [], 0.0
    while acc < total:
        c = round(random.uniform(2.6, 4.4), 2)
        cuts.append(c)
        acc += c

    used = set(json.loads(USED_FILE.read_text()) if USED_FILE.exists() else [])
    clips = pick_clips(query, len(cuts), used)
    if not clips:
        raise SystemExit("No Pexels clips found")

    parts = []
    for i, cut in enumerate(cuts):
        clip = clips[i % len(clips)]
        src = WORK / f"src_{clip['id']}.mp4"
        if not src.exists():
            src.write_bytes(fetch(clip["url"]))
        max_start = max(0.0, clip["duration"] - cut - 0.5)
        start = round(random.uniform(0, max_start), 2) if max_start > 0 else 0
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,{t['grade']}"
        if random.random() < 0.3:
            vf = "hflip," + vf
        out = WORK / f"part_{i:02d}.mp4"
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-ss", f"{start:.2f}", "-i", src, "-t", f"{cut:.2f}", "-an",
             "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", out])
        parts.append(out.name)

    (WORK / "parts.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "parts.txt", "-c", "copy", "base.mp4"], cwd=WORK)

    words = word_timings(audio, script)
    (WORK / "subs.ass").write_text(build_ass(words, hook, cta, total, t), encoding="utf-8")

    run(["ffmpeg", "-y", "-i", "base.mp4", "-i", "voice.wav",
         "-filter_complex", "[0:v]ass=subs.ass:fontsdir=../fonts[v];[1:a]apad[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "final.mp4"], cwd=WORK)

    used.update(c["id"] for c in clips)
    USED_FILE.write_text(json.dumps(sorted(used)[-5000:]))
    (WORK / "meta.json").write_text(json.dumps({
        "job_id": job, "title": title, "caption": caption, "hook": hook,
        "template": t["name"], "duration": round(total, 2), "clips": [c["id"] for c in clips],
    }, ensure_ascii=False))
    print("done:", WORK / "final.mp4", flush=True)


if __name__ == "__main__":
    main()

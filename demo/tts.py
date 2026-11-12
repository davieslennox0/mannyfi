"""Speak every line of narration.py with Kokoro (an expressive open-source voice), measure each one, and build:
   timeline.js     the scene and line timings the video is driven by (so the visuals follow the voice)
   timeline.json   the same, for render.py
   narration.wav   the voice track, each line placed at its start time
Run with an environment that has `kokoro-onnx` and `soundfile`:  python tts.py
The model files (kokoro-v1.0.onnx, voices-v1.0.bin) come from
https://github.com/thewh1teagle/kokoro-onnx/releases (model-files-v1.0).
"""
import json, os, pathlib, wave
import numpy as np
from kokoro_onnx import Kokoro

from narration import GAP, LEAD, SCENES, TAIL

HERE = pathlib.Path(__file__).resolve().parent
MODELS = pathlib.Path(os.environ.get("KOKORO_DIR", "/root/tts-models"))
VOICE = os.environ.get("KOKORO_VOICE", "af_heart")     # the best-rated female voice
SPEED = float(os.environ.get("KOKORO_SPEED", "1.10"))   # a touch brisker: reads as a presenter, not a chat
OUT = HERE / "audio"; OUT.mkdir(exist_ok=True)

kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))


def speak(text, path):
    audio, sr = kokoro.create(text, voice=VOICE, speed=SPEED, lang="en-us")
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
    return pcm, sr, len(pcm) / sr


t = 0.0
timeline, clips, SR = [], [], None
for sc in SCENES:
    a = t
    cur = a + LEAD
    lines = []
    for i, ln in enumerate(sc["lines"]):
        wav, SR, dur = speak(ln["say"], OUT / f"{sc['id']}_{i}.wav")
        lines.append({"a": round(cur, 3), "b": round(cur + dur, 3), "dur": round(dur, 3), "show": ln["show"],
                      "ev": ln.get("ev"), "user": ln.get("user")})
        clips.append((cur, wav))
        cur += dur + GAP
    b = max(cur - GAP + TAIL, a + sc["min"])
    timeline.append({"id": sc["id"], "a": round(a, 3), "b": round(b, 3), "lines": lines})
    t = b

total = round(t, 3)
track = np.zeros(int(total * SR) + SR, dtype=np.int16)
for start, wav in clips:
    i = int(start * SR)
    track[i:i + len(wav)] = np.clip(track[i:i + len(wav)].astype(np.int32) + wav, -32768, 32767).astype(np.int16)
with wave.open(str(HERE / "narration.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(track.tobytes())

(HERE / "timeline.json").write_text(json.dumps({"total": total, "scenes": timeline}, indent=1))
(HERE / "timeline.js").write_text("window.TL = " + json.dumps({"total": total, "scenes": timeline}) + ";\n")
print(f"voice {VOICE} speed {SPEED}  total {total}s")
for sc in timeline:
    print(sc["id"], f"{sc['a']:6.1f} -> {sc['b']:6.1f}", " | ".join(f"{l['dur']:.1f}s" for l in sc["lines"]))

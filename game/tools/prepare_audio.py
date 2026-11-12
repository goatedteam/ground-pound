"""Prepare game audio: trim, level and encode sound effects; find loop points in songs.

    python game/tools/prepare_audio.py --sfx <dir of raw takes> [--music base=<song.mp3>] [--music fight=<song.mp3>]

Raw sound-effect takes are named <sound>_<take>.mp3 (reel_stop_1.mp3, reel_stop_2.mp3 ...), as listed
in the audio prompts doc. Each take is trimmed of leading and trailing silence (loops are left whole),
levelled to a common loudness, faded at the tail and written as .webm (Opus) and .mp3 under
game/client/public/assets/audio/. Songs get a loop region that starts after the intro and ends on a
matching beat before the ending, with a short crossfade baked in so the loop has no seam.
assets/audio/manifest.json lists every file, its playback gain and the loop points.
Requires ffmpeg and numpy.
"""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "game" / "client" / "public" / "assets" / "audio"
SR = 48000

# Playback gain per sound, on top of the levelling: quiet UI ticks, loud tier stings.
GAIN = {
    "ui_click": 0.5, "bet_step": 0.55, "spin": 0.75, "reel_stop": 0.55, "belt_land": 0.9, "anticipation": 0.8,
    "hit_small": 0.7, "hit_big": 0.95, "damage_up": 0.5, "takedown": 0.85, "belt_count": 0.7, "bell_intro": 0.95,
    "crowd_roar": 0.8, "grudge_stamp": 0.9, "extra_rounds": 0.95, "tier_rocked": 0.9, "tier_brutal": 0.95,
    "tier_savage": 1.0, "tier_goated": 1.0, "knockout": 1.0, "count_loop": 0.35, "count_end": 0.8,
    "fight_over": 0.9, "buy_open": 0.7, "buy_sign": 0.85, "no_credit": 0.6, "blood_splat": 0.6, "crowd_bed": 0.45,
}
LOOPS = {"count_loop", "crowd_bed"}
TARGET_MEAN_DB = -20.0
PEAK_CEIL_DB = -1.0


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def decode(path, channels=2):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", str(channels), "-ar", str(SR), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, channels).copy()


def encode(x, stem, bitrate_opus="96k", bitrate_mp3="160k"):
    with tempfile.NamedTemporaryFile(suffix=".f32") as tmp:
        x.astype(np.float32).tofile(tmp.name)
        src = ["-f", "f32le", "-ar", str(SR), "-ac", str(x.shape[1]), "-i", tmp.name]
        run(["ffmpeg", "-v", "error", "-y", *src, "-c:a", "libopus", "-b:a", bitrate_opus, f"{stem}.webm"])
        run(["ffmpeg", "-v", "error", "-y", *src, "-ar", "44100", "-c:a", "libmp3lame", "-b:a", bitrate_mp3, f"{stem}.mp3"])


def db(v):
    return 20 * np.log10(max(v, 1e-9))


def prepare_sfx(path, loop):
    x = decode(path)
    if not loop:
        env = np.abs(x).max(1)
        thr = 10 ** (-50 / 20) * max(env.max(), 1e-9) * 10  # -30 dB below the peak
        idx = np.where(env > thr)[0]
        if len(idx):
            a = max(0, idx[0] - int(0.004 * SR))
            b = min(len(x), idx[-1] + int(0.08 * SR))
            x = x[a:b]
        n = min(len(x), int(0.03 * SR))
        x[-n:] *= np.linspace(1, 0, n)[:, None]
    rms = float(np.sqrt((x ** 2).mean()))
    gain_db = TARGET_MEAN_DB - db(rms)
    peak_db = db(float(np.abs(x).max())) + gain_db
    if peak_db > PEAK_CEIL_DB:
        gain_db -= peak_db - PEAK_CEIL_DB
    return x * (10 ** (gain_db / 20))


def onset_env(m, hop):
    n = len(m) // hop
    e = np.log1p(1000 * np.sqrt((m[: n * hop].reshape(n, hop) ** 2).mean(1)))
    return np.maximum(0, np.diff(e, prepend=e[0]))


def find_loop(x):
    """Loop start after the intro, loop end a whole number of bars later, where the music matches best."""
    m = x.mean(1)
    hop = 480
    fps = SR / hop
    on = onset_env(m, hop)
    o = on - on.mean()
    ac = np.correlate(o, o, "full")[len(o) - 1:]
    bpm = max(np.arange(70, 200, 0.25), key=lambda b: np.interp([60 / b * fps * k for k in (1, 2, 4)], np.arange(len(ac)), ac).sum())
    bar = 4 * 60 / bpm
    w = int(3 * fps)
    n = len(on)
    dur = len(m) / SR

    def win(i):
        v = on[i - w:i + w]
        v = v - v.mean()
        return v / (np.linalg.norm(v) + 1e-9)

    best = (-9.0, 0, 0)
    for ls in range(int(10 * fps), int(min(30, dur / 3) * fps)):
        a = win(ls)
        kmax = int((dur - 1.5 - ls / fps) / bar)
        for k in range(kmax, max(kmax - 12, 1), -1):
            guess = ls + k * bar * fps
            for le in range(int(guess - 6), int(guess + 7)):
                if le + w >= n:
                    continue
                c = float(a @ win(le))
                if c > best[0]:
                    best = (c, ls, le)
    _, ls, le = best
    s0, e0 = int(ls / fps * SR), int(le / fps * SR)
    ref = m[s0 - int(0.2 * SR):s0]
    shift = max(range(-int(0.02 * SR), int(0.02 * SR) + 1, 4),
                key=lambda j: float(np.dot(ref, m[e0 + j - len(ref):e0 + j])))
    e0 += shift
    xf = int(0.08 * SR)
    out = x[:e0].copy()
    t = np.linspace(0, 1, xf)[:, None]
    out[e0 - xf:e0] = out[e0 - xf:e0] * np.cos(t * np.pi / 2) + x[s0 - xf:s0] * np.sin(t * np.pi / 2)
    return out, s0 / SR, e0 / SR, bpm


def loudnorm(x, target=-18.0):
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.f32"
        dst = Path(d) / "out.f32"
        x.astype(np.float32).tofile(src)
        run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", str(src),
             "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11", "-ar", str(SR), "-f", "f32le", str(dst)])
        y = np.fromfile(dst, dtype=np.float32).reshape(-1, 2)
    return y[: len(x)] if len(y) >= len(x) else np.pad(y, ((0, len(x) - len(y)), (0, 0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sfx", type=Path, help="folder of raw takes named <sound>_<n>.mp3")
    ap.add_argument("--music", action="append", default=[], help="name=path to a song (base or fight)")
    a = ap.parse_args()
    (OUT / "sfx").mkdir(parents=True, exist_ok=True)
    (OUT / "music").mkdir(parents=True, exist_ok=True)
    mpath = OUT / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {"sfx": {}, "music": {}}

    if a.sfx:
        groups = {}
        for f in sorted(a.sfx.glob("*.mp3")):
            mt = re.match(r"(.+)_(\d+)$", f.stem)
            if mt:
                groups.setdefault(mt.group(1), []).append(f)
        manifest["sfx"] = {}
        for name, files in sorted(groups.items()):
            names = []
            for i, f in enumerate(files, 1):
                stem = f"sfx/{name}_{i}"
                encode(prepare_sfx(f, name in LOOPS), OUT / stem)
                names.append(stem)
            manifest["sfx"][name] = {"files": names, "gain": GAIN.get(name, 0.8)}
            print(f"{name}: {len(names)} take(s)")

    for spec in a.music:
        name, path = spec.split("=", 1)
        x = decode(path)
        looped, ls, le, bpm = find_loop(x)
        encode(loudnorm(looped), OUT / f"music/music_{name}", "128k", "192k")
        manifest["music"][name] = {"file": f"music/music_{name}", "loopStart": round(ls, 5), "loopEnd": round(le, 5), "gain": 1.0}
        print(f"music {name}: ~{bpm:.1f} BPM, loop {ls:.2f}s to {le:.2f}s")

    mpath.write_text(json.dumps(manifest, indent=1))
    print("wrote", mpath)


if __name__ == "__main__":
    main()

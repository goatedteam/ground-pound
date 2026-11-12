"""Prepare game audio: trim, level and encode sound effects; find loop points in songs.

    python game/tools/prepare_audio.py --sfx <dir of raw takes> [--music base=<song.mp3>] [--music fight=<song.mp3>]

Raw sound-effect takes are named <sound>_<take>.mp3 (reel_stop_1.mp3, reel_stop_2.mp3 ...), as listed
in the audio prompts doc. Each take is trimmed of leading and trailing silence (loops are left whole),
levelled to a common loudness, faded at the tail and written as .webm (Opus) and .mp3 under
game/client/public/assets/audio/. Songs get a loop region that starts after the intro and ends where the music
matches it, with a level ramp and a short crossfade baked in so the loop has no audible seam.
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


def band_frames(m, hop=1024):
    """Log-spectrum in 48 bands per frame, each frame normalised: what the music sounds like, not how loud."""
    n = (len(m) - 2048) // hop
    fr = np.lib.stride_tricks.sliding_window_view(m, 2048)[::hop][:n] * np.hanning(2048)
    sp = np.abs(np.fft.rfft(fr, axis=1))
    edges = np.unique(np.geomspace(2, 1024, 48).astype(int))
    f = np.log1p(10 * np.add.reduceat(sp, edges, axis=1))
    f -= f.mean(1, keepdims=True)
    return f / (np.linalg.norm(f, axis=1, keepdims=True) + 1e-9), SR / hop


def rms_db(m, a, b):
    return db(float(np.sqrt((m[int(a * SR):int(b * SR)] ** 2).mean())))


def find_loop(x):
    """Pick a loop start after the intro and a loop end near the finish where the 8 seconds around both match.

    Every start/end pair is scored by how alike the music sounds 4 s either side of each point. Among pairs
    scoring within 0.03 of the best, the longest loop wins, so the player hears as much of the song as
    possible before it repeats. A slow gain ramp across the loop evens out a song that builds, so the
    level does not drop at the seam, and an 80 ms crossfade is baked in at the end.
    """
    m = x.mean(1)
    dur = len(m) / SR
    F, fps = band_frames(m)
    W = int(4 * fps)
    i0, i1 = int(8 * fps), int(min(45, dur / 3) * fps)
    j0, j1 = int(dur * 0.55 * fps), int((dur - 1.0) * fps) - W
    S = F[i0 - W:i1 + W] @ F[j0 - W:j1 + W].T
    acc = np.zeros((i1 - i0, j1 - j0))
    for k in range(-W, W + 1):
        acc += S[W + k:W + k + i1 - i0, W + k:W + k + j1 - j0]
    acc /= 2 * W + 1
    length = (j0 + np.arange(j1 - j0))[None, :] - (i0 + np.arange(i1 - i0))[:, None]
    ok = acc >= acc.max() - 0.03
    bi, bj = np.unravel_index(np.argmax(np.where(ok, length, -1)), acc.shape)
    score = float(acc[bi, bj])
    s0, e0 = int((i0 + bi) / fps * SR), int((j0 + bj) / fps * SR)
    ref = m[s0 - int(0.2 * SR):s0]
    span = int(0.025 * SR)
    e0 += max(range(-span, span + 1, 4), key=lambda j: float(np.dot(ref, m[e0 + j - len(ref):e0 + j])))
    ls, le = s0 / SR, e0 / SR
    drop = ((rms_db(m, le - 3, le) - rms_db(m, ls - 3, ls)) + (rms_db(m, le, le + 3) - rms_db(m, ls, ls + 3))) / 2
    out = x[:e0].copy()
    if abs(drop) > 0.5:
        ramp = 10 ** (-drop * np.linspace(0, 1, e0 - s0) / 20)
        out[s0:e0] *= ramp[:, None]
    xf = int(0.08 * SR)
    t = np.linspace(0, 1, xf)[:, None]
    out[e0 - xf:e0] = out[e0 - xf:e0] * np.cos(t * np.pi / 2) + x[s0 - xf:s0] * np.sin(t * np.pi / 2)
    return out, ls, le, score, drop


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
        looped, ls, le, score, drop = find_loop(x)
        encode(loudnorm(looped), OUT / f"music/music_{name}", "128k", "192k")
        manifest["music"][name] = {"file": f"music/music_{name}", "loopStart": round(ls, 5), "loopEnd": round(le, 5), "gain": 1.0}
        print(f"music {name}: loop {ls:.2f}s to {le:.2f}s ({le - ls:.0f}s), seam match {score:.2f}, level ramp {drop:+.1f} dB")

    mpath.write_text(json.dumps(manifest, indent=1))
    print("wrote", mpath)


if __name__ == "__main__":
    main()

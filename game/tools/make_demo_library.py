"""Pre-draw a library of round records with the maths engine for the static demo build.

The static demo has no server, so it plays rounds that the engine drew ahead of time.
Outcomes still come only from math/nudgemath; the client picks one record at random.
A finite library is NOT a faithful RTP sample. Demo use only.

    python game/tools/make_demo_library.py --base 6000 --standard 150 --super 100
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "math"))
from nudgemath.config import game, load  # noqa: E402
from nudgemath.rounds import base_round, buy_round  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--base", type=int, default=6000)
ap.add_argument("--standard", type=int, default=150)
ap.add_argument("--super", type=int, default=100)
ap.add_argument("--seed", type=int, default=20261110)
ap.add_argument("--out", default=str(ROOT / "game" / "client" / "public" / "demo-rounds.json"))
a = ap.parse_args()
cfg = load(str(ROOT / "math" / "game_config.json"))
g = game(cfg, "96")
rng = np.random.default_rng(a.seed)
lib = {
    "note": "Pre-drawn by math/nudgemath for the static demo. Not an RTP-faithful sample.",
    "variant": "96",
    "base": [base_round(g, rng) for _ in range(a.base)],
    "buy_standard": [buy_round(g, rng, "standard", cfg["buy"]["standard"]["price"]) for _ in range(a.standard)],
    "buy_super": [buy_round(g, rng, "super", cfg["buy"]["super"]["price"]) for _ in range(a.super)],
}
Path(a.out).write_text(json.dumps(lib, separators=(",", ":")))
n = a.base
print(f"{a.out}: {Path(a.out).stat().st_size / 1e6:.1f} MB; base RTP in library {sum(r['win'] for r in lib['base']) / n:.3f}, "
      f"bonus triggers {sum(1 for r in lib['base'] if r['free_spins'])}")

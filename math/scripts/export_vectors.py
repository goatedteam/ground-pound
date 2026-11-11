"""Export golden vectors: complete round records for checking any port.

    python scripts/export_vectors.py            # writes golden/*.json

Re-run this whenever game_config.json changes. Each file holds a header with
the SHA-256 of the config it was made from; a port must use that same config.

Files:
  golden/base.json        random base rounds plus extra nudge-chain rounds
  golden/free_spins.json  base rounds that triggered free spins
  golden/buys.json        standard and super buys, including a 5,000x cap round
"""

import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nudgemath.config import game, load  # noqa: E402
from nudgemath.rounds import base_round, buy_round  # noqa: E402


def main(config="game_config.json", variant="96", out_dir="golden"):
    cfg = load(config)
    g = game(cfg, variant)
    with open(config, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    header = {"config": config, "config_sha256": digest, "variant": variant,
              "units": "multiples of total stake",
              "symbols": cfg["symbols"]}
    rng = np.random.default_rng(20261109)
    os.makedirs(out_dir, exist_ok=True)

    base = [base_round(g, rng) for _ in range(300)]
    chains = []
    while len(chains) < 100:
        r = base_round(g, rng)
        if len(r["base_spin"]["steps"]) > 1:
            chains.append(r)
    triggered = []
    while len(triggered) < 25:
        r = base_round(g, rng)
        if r["free_spins"]:
            triggered.append(r)

    std_price = cfg["buy"]["standard"]["price"]
    sup_price = cfg["buy"]["super"]["price"]
    buys = [buy_round(g, rng, "standard", std_price) for _ in range(40)]
    buys += [buy_round(g, rng, "super", sup_price) for _ in range(25)]
    while True:
        r = buy_round(g, rng, "super", sup_price)
        if r["capped"]:
            buys.append(r)
            break

    for name, rounds in [("base", base + chains), ("free_spins", triggered), ("buys", buys)]:
        path = os.path.join(out_dir, f"{name}.json")
        with open(path, "w") as f:
            json.dump({**header, "rounds": rounds}, f, separators=(",", ":"))
        print(f"{path}: {len(rounds)} rounds, {os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

"""Print a spin step by step.

    python scripts/trace.py                       # first base spin with a nudge chain
    python scripts/trace.py --bonus               # a whole free-spins round
    python scripts/trace.py --bonus --super       # a super-buy round
    python scripts/trace.py --seed 42 --min-win 20

Letters: a-d = low1-low4, E-H = high1-high4, * = scatter. The right-hand grid
shows each cell's multiplier mark (. = unmarked).
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nudgemath import engine as E  # noqa: E402
from nudgemath.config import game, load  # noqa: E402
from nudgemath.trace import trace_chain  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="game_config.json")
    ap.add_argument("--variant", default="96")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bonus", action="store_true")
    ap.add_argument("--super", action="store_true")
    ap.add_argument("--min-win", type=float, default=0.0,
                    help="keep searching until a spin/round wins at least this")
    args = ap.parse_args()

    g = game(load(args.config), args.variant)
    rng = np.random.default_rng(args.seed)
    for attempt in range(1, 1_000_000):
        mult = np.zeros((6, 6), dtype=np.int32)
        if args.bonus:
            text, total = bonus_round(g, rng, mult, args.super)
        else:
            text, total, chained = base(g, rng, mult)
            if not chained:
                continue
        if total >= args.min_win:
            print(text)
            print(f"\n(found on attempt {attempt}, seed {args.seed})")
            return


def spin(strips, lengths, rng):
    stops = np.array([rng.integers(lengths[c]) for c in range(6)], dtype=np.int64)
    grid = np.zeros((6, 6), dtype=np.int8)
    E.fill_grid(strips, lengths, stops, grid)
    return grid, stops


def base(g, rng, mult):
    grid, stops = spin(g.base_strips, g.base_lengths, rng)
    roll = rng.random() < g.p_nudge
    total, scatters, text = trace_chain(grid, g.base_strips, g.base_lengths, stops,
                                        mult, g.paytable, False, roll,
                                        g.upgrade_before_pay, g.cap)
    return "BASE SPIN\n" + text, total, roll and total > 0


def bonus_round(g, rng, mult, super_buy):
    lines, total = [], 0.0
    if super_buy:
        values = list(g.preheat_values)
        probs = np.diff(np.concatenate([[0.0], g.preheat_cum]))
        cells = rng.choice(36, size=g.preheat_cells, replace=False)
        for i in cells:
            mult[i // 6, i % 6] = rng.choice(values, p=probs / probs.sum())
        lines.append("SUPER BUY: starting marks placed")
    u = rng.random() * g.buy_cum[-1]
    left = int(g.buy_spins[np.searchsorted(g.buy_cum, u, side="right")])
    lines.append(f"FREE SPINS: {left} to play")
    n = 0
    while left > 0:
        left -= 1
        n += 1
        grid, stops = spin(g.bonus_strips, g.bonus_lengths, rng)
        win, scatters, text = trace_chain(grid, g.bonus_strips, g.bonus_lengths, stops,
                                          mult, g.paytable, True, True,
                                          g.upgrade_before_pay, g.cap - total)
        total += win
        lines.append(f"\nFREE SPIN {n}  (round so far {total:.2f})\n{text}")
        if total >= g.cap:
            break
        if scatters >= 3:
            left += g.retrigger_spins
            lines.append(f"  RETRIGGER +{g.retrigger_spins} spins")
    lines.append(f"\nROUND TOTAL {total:.2f}x")
    return "\n".join(lines), total


if __name__ == "__main__":
    main()

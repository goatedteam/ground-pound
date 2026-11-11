"""Reel-strip generator.

Strips are generated from a few shape parameters and a seed, then stored in
the game config as plain symbol lists. The stored lists are the real reel
strips (what a test lab certifies); the parameters are kept only so a strip
set can be regenerated or re-tuned.

Shape parameters per strip set (base or bonus):
    length          paying symbols per reel before scatters are inserted
    weights         relative frequency of symbols 0..7 (0 = lowest pay)
    run_mean        average length of a run of one symbol (stacking)
    run_max         longest run allowed
    scatters        scatters inserted per reel (list of 6 ints)
    seed            base seed; reel c uses seed + c
"""

import numpy as np

SCATTER = 8
N_PAYING = 8
MIN_SCATTER_GAP = 6  # = rows, so a reel never shows two scatters at once


def make_strip(length, weights, run_mean, run_max, n_scatters, seed):
    rng = np.random.default_rng(seed)
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    p_end = 1.0 / max(run_mean, 1.0)

    symbols = []
    prev = -1
    while len(symbols) < length:
        s = int(rng.choice(N_PAYING, p=w))
        if s == prev:
            continue
        run = min(int(rng.geometric(p_end)), run_max)
        symbols.extend([s] * run)
        prev = s
    symbols = symbols[:length]

    if n_scatters:
        spacing = length / n_scatters
        if spacing < MIN_SCATTER_GAP:
            raise ValueError("too many scatters for this strip length")
        offset = rng.uniform(0, spacing)
        positions = sorted(int(offset + i * spacing) for i in range(n_scatters))
        for p in reversed(positions):
            symbols.insert(p, SCATTER)
    check_scatter_gap(symbols)
    return symbols


def check_scatter_gap(strip, gap=MIN_SCATTER_GAP):
    """Raise if two scatters are closer than `gap` positions (circularly)."""
    pos = [i for i, s in enumerate(strip) if s == SCATTER]
    n = len(strip)
    for a, b in zip(pos, pos[1:] + pos[:1]):
        if len(pos) > 1 and (b - a) % n < gap:
            raise ValueError(f"scatters at {a} and {b} are closer than {gap}")


def make_strip_set(params):
    return [
        make_strip(params["length"], params["weights"], params["run_mean"],
                   params["run_max"], params["scatters"][c], params["seed"] + c)
        for c in range(6)
    ]


def describe(strips):
    """Symbol counts per reel, for reports."""
    counts = np.zeros((len(strips), 9), dtype=int)
    for c, strip in enumerate(strips):
        for s in strip:
            counts[c, s] += 1
    return counts

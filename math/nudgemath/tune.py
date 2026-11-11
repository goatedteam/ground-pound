"""Calibration: turn shape parameters into a tuned config.

Steps (each can be re-run on its own after a design change):

    1. fit_bonus_run   bisect the bonus strips' run_mean until a natural bonus
                       is worth target_bonus_mean
    2. solve_variants  for each RTP variant, solve the base nudge probability
                       so base RTP + bonus RTP hits the target. Variants only
                       change this base-game value, so the bonus and both buys
                       are identical in every variant.
    3. price_buys      standard buy = natural bonus, priced so buy RTP is the
                       top variant's RTP; super buy priced the same way

Precision: these use the decomposed method (base spins + bonus rounds), which
is much faster than full-game runs. scripts/simulate.py then checks the result
with full-game spins.
"""

import copy

from . import sim
from .build import make_config
from .config import game


def natural_bonus(cfg, variant, n_base, seed=101):
    b = sim.base(game(cfg, variant), n_base, seed=seed)
    start = {int(k): round(float(v), 5) for k, v in b["natural_start_spins"].items()}
    return b, start


def fit_bonus_run(params, target_mean, start_spins, lo, hi, n_rounds=150_000,
                  iterations=7, log=print):
    p = copy.deepcopy(params)
    best = None
    for _ in range(iterations):
        mid = round((lo + hi) / 2, 4)
        p["bonus_strips"]["run_mean"] = mid
        f = sim.bonus(game(make_config(p), next(iter(p["variants"]))), n_rounds,
                      start_spins=start_spins, seed=202)
        log(f"  bonus run_mean {mid:.4f}: mean {f['mean']:.1f} +/- {f['mean_ci95']:.1f}")
        if best is None or abs(f["mean"] - target_mean) < abs(best[1] - target_mean):
            best = (mid, f["mean"])
        if f["mean"] > target_mean:
            hi = mid
        else:
            lo = mid
    p["bonus_strips"]["run_mean"] = best[0]
    return p, best


def solve_variants(cfg, targets, bonus_mean, n_base, log=print, seed=303):
    """Solve base_nudge_probability for each {variant: target_rtp}.

    Total RTP(p) = base_rtp(p) + trigger_rate(p) * bonus_mean, which is close
    to linear in p. Two runs on common random numbers give the slope; a third
    run confirms the solution.
    """
    out = {}
    for variant, target in targets.items():
        c = copy.deepcopy(cfg)
        p0 = float(c["variants"][str(variant)]["base_nudge_probability"])
        pts = []
        for p in (p0 * 0.8, p0 * 1.2):
            c["variants"][str(variant)]["base_nudge_probability"] = p
            b = sim.base(game(c, variant), n_base, seed=seed)
            pts.append((p, b["rtp"] + b["trigger_rate"] * bonus_mean))
        (pa, ra), (pb, rb) = pts
        p_star = pa + (target - ra) * (pb - pa) / (rb - ra)
        c["variants"][str(variant)]["base_nudge_probability"] = round(p_star, 5)
        b = sim.base(game(c, variant), n_base, seed=seed)
        total = b["rtp"] + b["trigger_rate"] * bonus_mean
        log(f"  variant {variant}: p_nudge {p_star:.5f} -> {total:.4%} "
            f"(base {b['rtp']:.4%}, bonus 1 in {b['trigger_one_in']:.0f})")
        out[str(variant)] = {"base_nudge_probability": round(p_star, 5)}
    return out


def price(mean, rtp):
    return round(mean / rtp)

"""Calibrate tuned_params.json into game_config.json.

    python scripts/calibrate.py                 # standard precision (~10 min on 2 cores)
    python scripts/calibrate.py --quick         # rough pass for experiments
    python scripts/calibrate.py --scale 7.5     # release precision (~20 min on 2 cores)
    python scripts/calibrate.py --fit-bonus     # also re-fit bonus strip stacking

What it does:
  1. builds the reel strips from the shape parameters
  2. measures the natural free-spins start distribution (10/12/15/20 spins)
  3. measures what a natural bonus is worth
  4. solves the base nudge probability for each RTP variant
  5. prices the standard buy (= a natural bonus) and the super buy so both
     return the top variant's RTP
and writes game_config.json plus calibration.json with every measurement.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nudgemath import sim, tune  # noqa: E402
from nudgemath.build import make_config  # noqa: E402
from nudgemath.config import game, save  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="tuned_params.json")
    ap.add_argument("--out", default="game_config.json")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--fit-bonus", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="multiply all sample sizes (7.5 = release precision)")
    args = ap.parse_args()

    scale = 0.1 if args.quick else args.scale
    n_base = int(20_000_000 * scale)
    n_bonus = int(1_000_000 * scale)
    n_super = int(300_000 * scale)

    with open(args.params) as f:
        params = json.load(f)
    targets = params.pop("targets")
    top = max(targets["rtp"], key=lambda v: targets["rtp"][v])
    t0 = time.time()
    log = []

    def say(msg):
        print(msg, flush=True)
        log.append(msg)

    cfg = make_config(params)
    say("1. Natural free-spins start distribution")
    b, natural = tune.natural_bonus(cfg, top, n_base // 4)
    say(f"   {natural}  (bonus 1 in {b['trigger_one_in']:.0f})")
    params["buy"]["standard"]["start_spins"] = {str(k): v for k, v in natural.items()}

    if args.fit_bonus:
        target_mean = targets["standard_buy_price"] * targets["rtp"][top]
        say(f"   fitting bonus stacking to {target_mean:.1f}x")
        params, _ = tune.fit_bonus_run(params, target_mean, natural, 1.25, 1.45, log=say)

    cfg = make_config(params)
    say("2. Natural bonus value")
    fs = sim.bonus(game(cfg, top), n_bonus, start_spins=natural, seed=505)
    say(f"   mean {fs['mean']:.2f}x +/- {fs['mean_ci95']:.2f}, sd {fs['sd']:.0f}, "
        f"retrigger {fs['retrigger_rate']:.2%}, capped 1 in {fs['capped_one_in']:.0f}")

    say("3. Base nudge probability per variant")
    cfg["variants"] = tune.solve_variants(cfg, targets["rtp"], fs["mean"], n_base, log=say)
    params["variants"] = cfg["variants"]

    say("4. Buy prices")
    sup = sim.bonus(game(cfg, top), n_super, preheat=True, seed=606)
    std_price = tune.price(fs["mean"], targets["rtp"][top])
    sup_price = tune.price(sup["mean"], targets["rtp"][top])
    params["buy"]["standard"]["price"] = std_price
    params["buy"]["super"]["price"] = sup_price
    cfg["buy"] = params["buy"]
    say(f"   standard {std_price}x (bonus worth {fs['mean']:.1f}x, buy RTP {fs['mean']/std_price:.2%})")
    say(f"   super    {sup_price}x (bonus worth {sup['mean']:.1f}x, buy RTP {sup['mean']/sup_price:.2%}, "
        f"capped 1 in {sup['capped_one_in']:.0f})")

    save(cfg, args.out)
    params["targets"] = targets
    with open(args.params, "w") as f:
        json.dump(params, f, indent=1)
    with open("calibration.json", "w") as f:
        json.dump({"log": log, "natural_bonus": fs, "super_bonus": sup,
                   "base_spins": n_base, "bonus_rounds": n_bonus,
                   "seconds": round(time.time() - t0)}, f, indent=1, default=float)
    say(f"Wrote {args.out} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

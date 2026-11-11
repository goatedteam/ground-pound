"""Full-game verification of game_config.json.

    python scripts/simulate.py                      # all variants, 100M spins each
    python scripts/simulate.py --spins 1e9 --variant 96
    python scripts/simulate.py --spins 2e7          # quick look

Every spin is a complete round: base spin, any bonus it triggers, and the
5,000x cap on the whole round. Also measures base-game detail and both buys.
Writes results.json and RESULTS.md.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nudgemath import sim  # noqa: E402
from nudgemath.config import game, load  # noqa: E402


def one_in(x):
    return "never" if x == float("inf") else f"1 in {x:,.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="game_config.json")
    ap.add_argument("--spins", type=float, default=1e8)
    ap.add_argument("--variant", action="append")
    ap.add_argument("--buys", type=float, default=1e6, help="rounds per buy type")
    args = ap.parse_args()

    cfg = load(args.config)
    variants = args.variant or sorted(cfg["variants"], reverse=True)
    n = int(args.spins)
    out = {"config": args.config, "spins_per_variant": n, "variants": {}}
    t0 = time.time()

    for v in variants:
        g = game(cfg, v)
        full = sim.full(g, n, seed=int(v) * 17)
        base = sim.base(g, min(n, 50_000_000), seed=int(v) * 19)
        out["variants"][v] = {"full": full, "base": base,
                              "p_nudge": g.p_nudge}
        print(f"variant {v}: RTP {full['rtp']:.4%} +/- {full['rtp_ci95']:.4%} "
              f"(base {full['base_rtp']:.2%}, bonus {full['bonus_rtp']:.2%}), "
              f"bonus {one_in(full['bonus_one_in'])}, max win {one_in(full['capped_one_in'])}, "
              f"sd {full['sd']:.1f}  [{time.time() - t0:.0f}s]", flush=True)

    g = game(cfg, variants[0])
    std = sim.bonus(g, int(args.buys), seed=707)
    sup = sim.bonus(g, int(args.buys), preheat=True, seed=808)
    out["buys"] = {
        "standard": {"price": cfg["buy"]["standard"]["price"], **std},
        "super": {"price": cfg["buy"]["super"]["price"], **sup},
    }
    for name, r in out["buys"].items():
        print(f"{name} buy {r['price']}x: worth {r['mean']:.1f}x +/- {r['mean_ci95']:.1f}, "
              f"RTP {r['mean'] / r['price']:.2%}, max win {one_in(r['capped_one_in'])}")

    out["seconds"] = round(time.time() - t0)
    with open("results.json", "w") as f:
        json.dump(out, f, indent=1, default=float)
    write_markdown(cfg, out)
    print(f"Wrote results.json and RESULTS.md in {out['seconds']}s")


def write_markdown(cfg, out):
    L = []
    L.append(f"# Simulation results: {cfg['name']}\n")
    L.append(f"{out['spins_per_variant']:,} full-game spins per RTP variant. "
             "All figures are multiples of total stake.\n")
    L.append("## Whole game\n")
    L.append("| | " + " | ".join(f"{v}% variant" for v in out["variants"]) + " |")
    L.append("| --- |" + " --- |" * len(out["variants"]))
    rows = [
        ("RTP", lambda f, b, p: f"{f['rtp']:.3%} ± {f['rtp_ci95']:.3%}"),
        ("Base game RTP", lambda f, b, p: f"{f['base_rtp']:.2%}"),
        ("Free spins RTP", lambda f, b, p: f"{f['bonus_rtp']:.2%}"),
        ("Hit rate (any win)", lambda f, b, p: f"{f['hit_rate']:.2%}"),
        ("Free spins frequency", lambda f, b, p: one_in(f["bonus_one_in"])),
        ("Average free spins win", lambda f, b, p: f"{f['avg_bonus']:.1f}x"),
        ("5,000x max win", lambda f, b, p: one_in(f["capped_one_in"])),
        ("Standard deviation per spin", lambda f, b, p: f"{f['sd']:.1f}"),
        ("Base nudge probability", lambda f, b, p: f"{p:.4f}"),
        ("Base wins that start a nudge chain", lambda f, b, p: f"{b['nudge_share_of_wins']:.1%}"),
        ("Average nudges per base chain", lambda f, b, p: f"{b['avg_nudges_per_chain']:.2f}"),
    ]
    for label, fn in rows:
        cells = [fn(r["full"], r["base"], r["p_nudge"]) for r in out["variants"].values()]
        L.append(f"| {label} | " + " | ".join(cells) + " |")

    L.append("\n## Bonus buys\n")
    L.append("| | Standard | Super |")
    L.append("| --- | --- | --- |")
    s, u = out["buys"]["standard"], out["buys"]["super"]
    for label, fn in [
        ("Price", lambda r: f"{r['price']}x"),
        ("Average win", lambda r: f"{r['mean']:.1f}x ± {r['mean_ci95']:.1f}"),
        ("Buy RTP", lambda r: f"{r['mean'] / r['price']:.2%}"),
        ("Rounds under 20x", lambda r: f"{r['share_under_20x']:.1%}"),
        ("Rounds with a retrigger", lambda r: f"{r['retrigger_rate']:.1%}"),
        ("Average free spins played", lambda r: f"{r['avg_spins']:.2f}"),
        ("5,000x max win", lambda r: one_in(r["capped_one_in"])),
    ]:
        L.append(f"| {label} | {fn(s)} | {fn(u)} |")

    L.append("\n## Win distribution, top variant (share of spins)\n")
    top = next(iter(out["variants"].values()))["full"]
    n = out["spins_per_variant"]
    L.append("| Round win | Share of spins | About |")
    L.append("| --- | --- | --- |")
    for label, count in zip(sim.BUCKET_LABELS, top["win_hist"]):
        if count:
            L.append(f"| {label} | {count / n:.5%} | {one_in(n / count)} |")
    with open("RESULTS.md", "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()

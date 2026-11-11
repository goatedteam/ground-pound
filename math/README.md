# Cluster Nudge maths engine and simulator

Maths model for a 6x6 cluster-pays slot with a nudge chain and grid-position
multipliers, built from the design spec ("Sugar Supreme Powernudge: Mechanics
Teardown & Design Blueprint", Design decisions table). It is a tuning tool:
every rule and number lives in one config file, and the simulator measures
what that config does.

Latest tuned results are in **RESULTS.md**.

## Quick start

```bash
pip install numpy numba pytest
python -m pytest -q tests                 # rule tests on hand-built grids
python scripts/simulate.py --spins 2e7    # quick full-game check (~1 min)
python scripts/trace.py --min-win 10      # watch one base spin step by step
python scripts/trace.py --bonus           # watch a whole free-spins round
python scripts/calibrate.py --quick       # re-tune after changing tuned_params.json
python scripts/export_vectors.py          # regenerate golden vectors after any maths change
```

Speed on a 2-core machine: about 1.5 million full-game spins a second
across both cores. It uses every core it finds; set `NUDGE_WORKERS` to limit
that.

## Files

| File | What it is |
| --- | --- |
| `game_config.json` | The game: paytable, rules, real reel strips, nudge probability per RTP variant, buy prices. The engine reads only this. |
| `tuned_params.json` | The compact tuning inputs that `calibrate.py` turns into `game_config.json` |
| `nudgemath/engine.py` | The rules: cluster detection, pay, marks, nudge, base spin, free spins |
| `nudgemath/sim.py` | Monte Carlo simulators (base only, bonus only, full game) |
| `nudgemath/strips.py` | Reel-strip generator |
| `nudgemath/tune.py` | Calibration steps |
| `nudgemath/rounds.py` | Round records: the full step-by-step result of a bet as JSON (the server's output format) |
| `scripts/calibrate.py` | Builds strips, solves each RTP variant, prices both buys |
| `scripts/simulate.py` | Full-game verification; writes `results.json` and `RESULTS.md` |
| `scripts/trace.py` | Prints a spin or bonus round step by step |
| `scripts/export_vectors.py` | Writes `golden/*.json`, reference rounds any server, client or port must reproduce |
| `tests/test_rules.py` | Rule tests, including the stacked-symbol worked example and record replay |
| `golden/` | Golden vectors made from the current `game_config.json` (its SHA-256 is in each file) |

## How the spec maps to the code

| Decision | Where | How |
| --- | --- | --- |
| 1. Reading B | `engine.evaluate` | Pay uses marks as they stood before the evaluation; every winning cell gets +1 after the pay. `upgrade_before_pay: true` switches to reading A for comparison. |
| 2. No per-cell cap | `engine.evaluate` | Marks grow without limit; only `max_win` (5,000x) stops a round |
| 3. Reel strips, separate bonus set | `base_strips`, `bonus_strips` | A nudge reveals the next symbol up the strip |
| 4. One scatter per reel, counted across the chain | `strips.py`, `engine.play_chain` | Scatters sit at least 6 apart on every strip; landing scatters plus each one that enters during the chain are counted once; 6+ pays the 20-spin tier |
| 5. Standard + super buy, three RTP versions | `buy`, `variants` | Standard buy = a natural bonus (same start-spin mix); super buy pre-marks every cell; variants change only the base nudge probability |
| 6. Reference paytable | `paytable` | Unchanged; symbols renamed low1-low4, high1-high4 |
| 7. High volatility | measured | SD per spin is reported by `simulate.py` |
| 8. Lower base rate, richer bonus | `variants`, `bonus_strips` | Bonus worth about 114x, standard buy 119x. The base nudge landed at about 1 in 8 base wins rather than 1 in 10: with the reference paytable, a win without a nudge returns only about 17% RTP, so the nudge carries most of the base game. Stickier base strips or bigger small-cluster pays would bring it down. |

## The tuning levers

Change `tuned_params.json`, run `python scripts/calibrate.py`, then
`python scripts/simulate.py`.

| To change | Edit | Notes |
| --- | --- | --- |
| Free spins frequency | `base_strips.scatters` or `base_strips.length` | More scatters per reel or shorter strips = more often |
| Retrigger frequency | `bonus_strips.scatters` | Currently 2 per reel |
| How much a bonus is worth | `bonus_strips.run_mean` (stacking) or `weights` | Small steps: 1.35 to 1.40 roughly doubles the bonus. `calibrate.py --fit-bonus` re-fits it to `targets.standard_buy_price` |
| Base hit rate | `base_strips.run_mean` and `weights` | Stickier strips raise hit rate and the value of each chain |
| Base nudge rate | solved automatically | `calibrate.py` picks it per variant to hit the target RTP |
| Super buy | `buy.super.preheat_cells`, `preheat_values` | Price follows automatically |
| Paytable | add a `"paytable"` block to `tuned_params.json` | Defaults to the reference paytable |

Strips are regenerated from the shape parameters and a seed every time you
calibrate, so small parameter changes can move results a little unevenly.
Once you are happy, treat the strips in `game_config.json` as fixed data.

## Precision

The calibration uses 150 million base spins and 7.5 million bonus rounds,
which puts RTP within about ±0.1 percentage points. `simulate.py` gives an
independent full-game check; its ±figure is a 95% interval. A test lab will
expect its own runs, typically a billion spins or more per variant:
`python scripts/simulate.py --spins 1e9 --variant 96` (about 15 minutes on 2 cores,
proportionally less with more).

## Not included yet

- A certified RNG. The simulator uses numpy's generator, which is fine for
  maths work but is not what you ship.
- Game-cycle timing, GB rules (no buy, £5/£2 stake caps) and other per-market
  settings; those belong to the game client and the market builds.

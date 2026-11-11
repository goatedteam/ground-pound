# Cluster Nudge (working title): slot game build

We are building a 6x6 cluster-pays slot whose wins make the winning reels
slide down one row and pay again, with per-cell multiplier marks that grow
+1 per win. The design is done and the maths is tuned; the job now is to
build the game around them.

## Read first

1. `docs/GAME_DESIGN.md`: the game rules, numbers, presentation,
   compliance and IP rules. This is the spec.
2. `docs/BUILD_PLAN.md`: architecture, round record format, milestones and
   acceptance criteria. Follow it in order.
3. `math/README.md`: the maths engine, simulator and tools.

Background only (not the spec): the research teardown linked at the end of
`docs/GAME_DESIGN.md`. Its numbers describe the reference game, not ours.

## Layout

```
math/                  tuned Python maths (engine, simulator, golden vectors)
  game_config.json     single source of truth for every number
  nudgemath/engine.py  the rules, as code
  nudgemath/rounds.py  produces round records (the server's output format)
  golden/*.json        reference rounds every component must reproduce
  RESULTS.md           measured RTP, hit rate, bonus frequency, buys
docs/                  design spec and build plan
game/                  everything you build (server, client, schema, markets)
```

## Rules that must never break

- **Outcomes come only from the maths engine** (`math/nudgemath`). The client
  animates round records and never decides, computes or alters an outcome.
- **Never edit `math/game_config.json`, reel strips or `math/golden/` by
  hand**, and never hard-code maths values in game code. Maths changes go
  through the pipeline in `docs/BUILD_PLAN.md` section 8, and only when the
  user asks for them.
- **Reading B:** a cluster's multiplier is the sum of its cells' marks
  *before* the evaluation (1 if the sum is 0); every winning cell gets +1
  *after* the pay.
- **Only reels with a winning cell slide.** Marks stay on cells; they do not
  move with symbols.
- **Base game:** one random roll per spin decides whether the chain runs;
  marks are cleared after the spin. **Free spins:** every win slides; marks
  persist all round.
- **Scatters** count once each: landing grid plus each one that enters during
  the chain.
- **5,000x cap** per round, checked after every evaluation; it ends the round
  immediately.
- **Money is integers**: hundredths of stake inside the game, minor units for
  currency. No floats for money anywhere.
- **Market rules are configuration** (`game/markets/*.json`), never `if gb`
  branches scattered through code.
- **IP:** never use "Powernudge"/"PowerNudge", any Pragmatic Play name or
  asset, or a candy theme. Placeholder art until the user picks a theme.
- **No real-money claims.** The dev RNG is not certified; say so wherever it
  matters.

## Commands

```bash
# maths (from math/)
pip install numpy numba pytest
python -m pytest -q tests                  # 19 rule tests
python scripts/trace.py --min-win 10       # watch one base spin step by step
python scripts/trace.py --bonus            # watch a free-spins round
python scripts/simulate.py --spins 2e7     # quick full-game check
python scripts/export_vectors.py           # regenerate golden vectors
```

```bash
# server (from the repo root); serves the built client at /
python game/server/app.py --port 8000 [--seed 123]
python -m pytest -q game/server/tests

# client (from game/client/)
npm install && npm run build      # production build into dist/
npm run dev                       # dev server on 5173, proxies /api to 8000
npm test                          # timeline tests against golden rounds

# static demo data (re-run after any maths change)
python game/tools/make_demo_library.py
```

## How to work

- Start at M0 in `docs/BUILD_PLAN.md`. Confirm the stack with the user before
  scaffolding, then build one milestone at a time and run its acceptance
  checks before moving on.
- Use `math/golden/*.json` as the test oracle for anything that touches round
  data, and replay mode to check animations by eye.
- If the spec is ambiguous, check `math/nudgemath/engine.py` (the code is the
  final word on rules), then ask the user. Do not guess on anything that
  changes what a player is paid.
- Ask the user before deciding: game name, theme and art direction, the
  mechanic's name, target markets and bet ladders, or any maths change.
- Keep `docs/DECISIONS.md` as a short dated log of decisions the user makes.

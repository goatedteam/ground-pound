# Build plan

How to turn `docs/GAME_DESIGN.md` and the tuned maths in `math/` into a
playable game. Work milestone by milestone; each has acceptance criteria that
must pass before moving on.

Scope: a complete, playable game with a server-authoritative architecture
that could later sit behind a real remote game server (RGS). It is **not**
real-money ready: that needs a certified RNG, lab certification and an
operator integration, which are out of scope.

## 1. Architecture

```
math/            existing Python maths: engine, simulator, round records (do not fork)
game/server/     Python HTTP service that wraps math/nudgemath and returns round records
game/client/     TypeScript browser client that animates round records
game/schema/     JSON Schema for round records + generated TypeScript types
game/markets/    market presets (default, gb, ...)
```

Default stack (confirm with the user in M0 before scaffolding):

- **Server:** Python 3.11+, FastAPI, importing `math/nudgemath` directly. This
  reuses the tested engine, so there is no second implementation to keep in
  step.
- **Client:** TypeScript, Vite, PixiJS for rendering, Vitest for tests.
- If the user wants a different stack, or an engine port (for example to
  TypeScript), the port must pass every golden vector in `math/golden/`
  before anything else is built on it.

Data flow: `game_config.json` -> engine -> **round record** -> client. The
client never decides outcomes, never has the reel strips' weights in its
logic, and never computes pays; it only animates records.

## 2. The round record

Produced by `math/nudgemath/rounds.py` (`base_round`, `buy_round`). Examples
in `math/golden/*.json`. Write `game/schema/round.schema.json` from this
description and validate every record the server returns in tests.

```
Round
  mode          "base" | "buy_standard" | "buy_super"
  cost          stake multiples charged (1 for a spin, 119 or 505 for buys)
  base_spin     Spin | null          (null for buys)
  free_spins    FreeSpins | null
  win           round total, multiples of stake, capped at 5000
  capped        true if the round hit 5,000x

FreeSpins
  awarded       spins awarded at the start (10, 12, 15 or 20)
  start_marks   6x6 marks before spin 1 (all 0, or super-buy values)
  spins         Spin[]  (each also has retrigger: bool, spins_left: int)
  retriggers    count
  win           free-spins total
  capped        bool

Spin
  reel_set      "base" | "bonus"
  stops         6 stop indices (landing position of each reel)
  nudge_roll    base: the pre-drawn roll (bool); free spins: null
  steps         Step[]   one per evaluation, in order
  scatters      scatters counted across the whole chain
  win           spin total
  capped        bool

Step
  grid          6x6 symbol ids, [row][reel], row 0 = top, as evaluated
  marks_before  6x6 marks used for this evaluation's pays
  clusters      [{symbol, size, cells: [[row, reel]...], base_pay, multiplier, pay}]
  win           sum of cluster pays in this step
  marks_after   6x6 marks after the +1s
  nudged_reels  reels that slid after this step (absent on the last step)
  entered       symbol that entered row 0 of each nudged reel, same order
  new_scatters  scatters among the entered symbols
  capped        present and true if this step reached the cap
```

A spin's last step either has no clusters (the chain ended on a non-win) or
ends the chain for another reason (base roll failed, or capped).

## 3. Money

- Hold all game values as **integer hundredths of stake** (pays are
  multiples of 0.05, multipliers are integers, so this is exact). Never use
  floats for money in server or client.
- Currency amounts are integer minor units: `win_minor = hundredths x bet_minor / 100`.
  This is a whole number whenever the bet is a multiple of 20 minor units
  (0.20, 0.40, ... in a 2-decimal currency). The server must reject bets
  that are not on the market's bet ladder, and every ladder value must be a
  multiple of 20 minor units.

## 4. Server (game/server)

- Endpoints:
  - `GET  /api/config?market=...` -> name, symbols, paytable, rules, award
    table, bet ladder, buys (only if the market allows them) with prices,
    RTP version, timing rules from the market preset
  - `POST /api/session {market, variant}` -> `{session_id, balance_minor}`
    (play-money wallet, in memory)
  - `POST /api/spin {session_id, bet_minor}` -> `{round_id, round, bet_minor,
    win_minor, balance_minor}`
  - `POST /api/buy {session_id, bet_minor, kind: "standard"|"super"}` -> same;
    403 when the market disables buys
  - `GET  /api/rounds/{round_id}` -> the stored record (for replay and QA)
- RNG behind an interface. Dev: `numpy.random.default_rng` seeded from
  `os.urandom` per session; a `--seed` flag for reproducible QA. Mark the
  production RNG as a TODO; do not claim certification.
- Debit the cost, then credit the win, atomically per round; store every
  round with its record.
- Enforce the market's minimum interval between rounds server-side too.

## 5. Client (game/client)

States: `idle -> landing -> chain steps -> (free-spins intro -> spins -> outro) -> idle`.

- Render the 6x6 grid from `step.grid`; draw marks from `marks_before` /
  `marks_after`.
- Per step: highlight each cluster's cells, show `base_pay x multiplier`,
  add `pay` to the win meter, animate marks to `marks_after` (+1 pops), then
  slide `nudged_reels` down one row with `entered` symbols coming in at the
  top. Build this as a pure function `record -> timeline` so it can be unit
  tested without rendering.
- Free spins: intro with `awarded`, a spins-left counter (`spins_left`),
  retrigger callout, marks always visible, outro with the total. Super buy:
  reveal `start_marks` before spin 1.
- HUD: balance, bet selector (market ladder), last win, spin button; buy
  menu with confirmation (hidden when the market disables buys); net position
  and session timer when the market requires them; sound toggle.
- Rules and paytable screens generated from `/api/config`.
- Wins <= stake: plain feedback only. Big-win tiers only above stake (suggest
  10x / 25x / 50x, configurable).
- Timing values (step durations, slide speed) in one config object. Turbo and
  skip only if the market allows them. Autoplay only if the market allows it.
- **Replay mode** (`?replay=<file>`): loads a golden vector file or a stored
  round and plays it, with a debug overlay showing the current step's data.
- Placeholder art: simple distinct shapes and colours per symbol, clearly
  labelled low1...high4 and scatter. No candy theme. Responsive down to
  phone portrait.

## 6. Market presets (game/markets)

JSON per market: `buys`, `bet_ladder_minor`, `min_cycle_ms`, `turbo`,
`autoplay`, `show_net_position`, `show_session_time`, `max_stake_minor`.
Ship `default.json` (buys on, no cycle minimum) and `gb.json` (buys off,
2,500 ms minimum cycle, no turbo, no autoplay, net position and session time
on, max stake £5). Values come from `docs/GAME_DESIGN.md` section 13.

## 7. Milestones

**M0 Setup**
- Read `docs/GAME_DESIGN.md`, this file and `math/README.md`.
- `cd math && pip install numpy numba pytest && python -m pytest -q tests`
  (19 tests must pass).
- Confirm the stack with the user, and ask the section 12 design questions
  in GAME_DESIGN.md that block work (placeholders are fine for art).
- Done when: tests pass and the stack is confirmed.

**M1 Schema and server**
- Write the JSON Schema and TypeScript types for the round record.
- Build the server from section 4.
- Tests: every golden vector validates against the schema; 10,000 server
  rounds validate; balance arithmetic is exact; buys return 403 under `gb`;
  off-ladder bets are rejected; a seeded server reproduces the same rounds.
- Sanity check: 200,000 server spins give a base-game hit rate of 31.7% ±
  0.4 and free spins between 1 in 220 and 1 in 310.

**M2 Client: base game**
- Grid, HUD, spin flow and the full chain animation from records.
- Replay mode working on `math/golden/base.json`.
- Tests: the timeline builder's final win equals `round.win` for every golden
  base round; marks shown after each step equal `marks_after`.

**M3 Client: free spins and buys**
- Free-spins flow, retriggers, cap ending, buy menu and super-buy start
  marks.
- Replay of `math/golden/free_spins.json` and `buys.json` (includes a
  5,000x cap round) with no errors; final totals match.

**M4 Markets, rules and polish**
- Market presets applied end to end; rules/paytable screens; sub-stake
  feedback rule; big-win tiers; sound hooks; phone layout.
- Under `gb`: no buy UI, no turbo, no autoplay, cycles never shorter than
  2.5 s, net position and session time visible.

**M5 QA**
- Soak test: 10,000 rounds through server and client with no errors.
- Every golden vector replays correctly.
- Short QA report in `game/QA.md`: what was tested, known gaps.

## 8. Changing the maths

Never edit `game_config.json`, the strips or the golden vectors by hand, and
never put maths in game code. To change the maths:

```bash
cd math
# edit tuned_params.json (see math/README.md "The tuning levers")
python scripts/calibrate.py          # re-solves variants and buy prices
python scripts/simulate.py           # verifies; updates RESULTS.md
python scripts/export_vectors.py     # regenerates golden/*.json
python -m pytest -q tests
```

Then update the numbers in `docs/GAME_DESIGN.md` sections 8-10 and re-run all
game tests.

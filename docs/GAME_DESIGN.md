# Game design: Cluster Nudge (working title)

This is the design for **our** game. It was derived from a research teardown of
a reference game (linked at the end) and then tuned with our own maths in
`math/`. Where this file and the teardown differ, **this file wins**; the
teardown's numbers describe the reference game, not ours.

Source of truth for every number: `math/game_config.json`. The tables below
are copies for reading; if they ever disagree with the config, the config
wins and this file should be corrected.

## 1. Overview

A 6x6 cluster-pays slot. Instead of tumbling, a win makes **only the reels
that contain winning symbols slide down one row**; one new symbol enters at
the top of each of those reels and the grid pays again. This repeats until a
slide produces no win. Every cell that wins is **marked** with a multiplier
that grows by +1 each time it wins again; a cluster's pay is multiplied by
the sum of the marks under it.

- **Base game:** the slide chain only starts on a random roll when a spin
  wins (about 1 in 8 winning spins). Marks are wiped when the spin ends.
- **Free spins:** every win slides, and marks stay for the whole round, so
  the board heats up spin by spin. This is where the big wins live.

## 2. Grid, symbols and paytable

- 6 reels x 6 rows. Rows are numbered 0 (top) to 5 (bottom).
- 8 paying symbols (`low1`-`low4`, `high1`-`high4`, ids 0-7) and a scatter
  (id 8). No wild.
- Final symbol art and names are not decided (see section 12).

Pays are multiples of **total stake**. A cluster is 5 or more identical
symbols joined horizontally or vertically (not diagonally). Clusters of 15 or
more pay the 15+ value. Several clusters can pay in the same evaluation.

| Cluster | low1 | low2 | low3 | low4 | high1 | high2 | high3 | high4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 0.10 | 0.15 | 0.20 | 0.30 | 0.40 | 0.50 | 0.75 | 1.00 |
| 6 | 0.15 | 0.20 | 0.25 | 0.35 | 0.45 | 0.60 | 1.00 | 1.25 |
| 7 | 0.20 | 0.25 | 0.30 | 0.40 | 0.50 | 0.75 | 1.25 | 1.50 |
| 8 | 0.30 | 0.40 | 0.50 | 0.60 | 0.75 | 1.00 | 1.50 | 2.00 |
| 9 | 0.40 | 0.50 | 0.60 | 0.75 | 1.00 | 1.50 | 2.00 | 2.50 |
| 10 | 0.50 | 0.60 | 0.75 | 1.00 | 1.50 | 2.00 | 2.50 | 3.00 |
| 11 | 0.75 | 1.00 | 1.25 | 1.50 | 2.50 | 3.00 | 4.00 | 5.00 |
| 12 | 1.00 | 1.25 | 1.50 | 2.00 | 3.00 | 4.00 | 6.00 | 7.50 |
| 13 | 2.00 | 2.50 | 3.00 | 4.00 | 6.00 | 8.00 | 12.00 | 15.00 |
| 14 | 3.00 | 4.00 | 5.00 | 6.00 | 8.00 | 10.00 | 15.00 | 20.00 |
| 15+ | 10.00 | 15.00 | 20.00 | 30.00 | 40.00 | 50.00 | 75.00 | 100.00 |

Every value is a multiple of 0.05, which keeps money arithmetic exact.

## 3. Reel strips

Outcomes come from **reel strips** (fixed symbol sequences in
`game_config.json`), not independent symbol draws. There are two sets:
`base_strips` and the stackier `bonus_strips`. A spin picks one stop per reel,
uniformly. Reel `c` shows `strip[c][(stop + row) % length]` in rows 0-5.

Scatters sit at least 6 apart on every strip, so a reel never shows two at
once.

## 4. The nudge chain

1. The spin lands. Every cluster of 5+ is found and paid (section 5).
2. If nothing won, the spin ends.
3. **Base game only:** on the spin's first win, a single random roll decides
   whether the chain runs (`base_nudge_probability`, about 0.128 in the 96%
   version). If it fails, the win pays and the spin ends.
4. Every reel holding at least one cell of any winning cluster slides down
   one row: its stop decreases by 1, the bottom symbol leaves the grid and
   `strip[c][stop]` enters at the top. Reels with no winning cell stay still.
5. The grid is evaluated again with the current marks. Go back to step 4
   while it keeps winning.
6. Base game: all marks are cleared. Free spins: marks stay.

Because every reel under a cluster moves together, a cluster usually slides
down intact and pays again until it falls off the bottom row. Tall clusters
land mostly on their own already-marked cells, so they heat fastest.

## 5. Marks (position multipliers)

Marks belong to **grid cells**, not symbols. They do not move when reels
slide.

- Cluster pay = `paytable[symbol][size] x M`, where **M is the sum of the marks
  on the cluster's cells as they were before this evaluation**. If that sum
  is 0, M = 1.
- **After** the pay, every cell of every winning cluster gets +1 (an unmarked
  cell becomes 1). This is "reading B": a mark never boosts the win that
  created or upgraded it.
- No per-cell cap. Only the 5,000x round cap limits value.

**Worked example.** Five `high3` stacked in rows 0-4 of one reel pay 0.75 and
mark those five cells x1. The reel slides; the stack now fills rows 1-5. Rows
1-4 carry x1 each, row 5 is unmarked, so M = 4 and the pay is 0.75 x 4 =
3.00. Afterwards rows 1-4 are x2 and row 5 is x1. The next slide leaves only
four `high3`, so the chain ends. Total 3.75. (This exact case is a unit test.)

## 6. Scatters and free spins

- A spin's scatter count = scatters on the landing grid **plus** each scatter
  that enters at the top during its chain. Each scatter counts once, even
  after it slides off the bottom.
- At the end of a base spin, 3+ scatters award free spins:

| Scatters | Free spins |
| --- | --- |
| 3 | 10 |
| 4 | 12 |
| 5 | 15 |
| 6 or more | 20 |

- Free spins use the bonus strips. Every win slides. Marks start empty and
  persist across every free spin until the round ends.
- 3+ scatters in a single free spin (counted across its chain) add 10 spins.
  No limit on retriggers.
- The scatter pays nothing itself.

## 7. Max win

A round (the base spin plus any free spins it triggers, or a whole bought
bonus) is capped at **5,000x total stake**. The cap is checked after every
evaluation; reaching it pays exactly 5,000x and ends the round at once, with
remaining free spins forfeited. A base spin that reaches the cap does not go
on to free spins.

## 8. Bonus buys

| | Standard buy | Super buy |
| --- | --- | --- |
| Price | 119x total stake | 505x total stake |
| What you get | Free spins with the same start mix as a natural trigger (10 spins 95.2%, 12 spins 4.7%, 15 spins 0.1%) | The same, plus every cell starts marked: x5 (50%), x10 (30%) or x15 (20%) |
| RTP | about 96% | about 96% |

There is no base spin on a buy. Buys must be switchable off per market (they
are off in Great Britain). There is no ante bet.

## 9. RTP versions

Three versions differ **only** in `base_nudge_probability`; strips, paytable,
free spins and buys are identical.

| Version | Base nudge probability | Measured RTP (300M spins) |
| --- | --- | --- |
| 96% | 0.12808 | 96.10% ± 0.18 |
| 95% | 0.12468 | 95.04% ± 0.18 |
| 94% | 0.12126 | 94.18% ± 0.18 |

## 10. Tuned results (96% version)

From `math/RESULTS.md`:

- Base game 52.7% RTP, free spins 43.4%
- Hit rate 31.7% of spins; base chain starts on 12.8% of winning base spins
  and averages 3.4 slides
- Free spins 1 in 263 spins, average 114x, retrigger in 5% of rounds
- 5,000x max win about 1 in 1.2 million spins
- High volatility: standard deviation 15.7 per spin
- 23% of spins return less than the stake; treat these as losses in
  presentation (section 11)

## 11. Presentation requirements

- Show every cell's mark on the grid at all times in free spins, and animate
  each +1 so the board's heat reads at a glance. In the base game, show marks
  during a chain.
- Sequence per evaluation: highlight clusters -> show each cluster's pay and
  its M -> add to the win meter -> apply the +1 marks -> slide the reels.
- The chain should feel quick. Every step is in the round record, so the
  client only animates; it never computes outcomes.
- Wins less than or equal to the total stake get plain, non-celebratory
  feedback (no fanfare, no "win" banners).
- Free spins: intro with spins awarded, spin counter, retrigger callout,
  outro with the total. Super buy shows the starting marks before spin 1.
- Buy menu: price in currency, a clear description, and a confirmation step.
- Paytable and rules screens are generated from the config and must describe
  the chain, marks (reading B), scatter counting and the cap precisely.

## 12. Open design items (ask the user)

- Game name, theme, symbol art, sound. Placeholders until decided.
- Name for the slide mechanic (not "Powernudge"; see section 14).
- Whether to keep the base nudge at about 1 in 8 wins or retune toward 1 in
  10 (needs stickier base strips or bigger small-cluster pays; done in
  `math/`, never in game code).
- Target markets and their bet ladders.

## 13. Market and compliance requirements

Make these configuration, not code. A market preset sets: buys on/off,
min and max stake and bet ladder, autoplay on/off, turbo/skip on/off,
minimum game-cycle time, and whether to show net position and session time.

Great Britain preset (from the research doc; verify with counsel before
launch):

| Rule | Requirement |
| --- | --- |
| RTS 14D | At least 2.5 s between game cycles; each cycle needs its own start action. The whole nudge chain sits inside one cycle. |
| RTS 14E | No turbo, quick spin or slam stop in the base game |
| RTS 14F | No celebrating a return less than or equal to total stake |
| RTS 8C | No autoplay |
| RTS 2E, 13C | Show net position and elapsed session time |
| Stake limits | Max £5 per spin (£2 for ages 18-24) |
| Feature buy | Not offered |

Everywhere: the base nudge probability is fixed and documented; it must never
adapt to a player's results.

## 14. Intellectual property

- Never use "Powernudge"/"PowerNudge" or any Pragmatic Play name, logo,
  symbol art, sounds or layout. Pragmatic presents the name as a trademark.
- Avoid a candy theme that could be confused with Sugar Rush, Sugar Supreme
  or Sweet Bonanza.
- The maths in `math/` is our own (own strips, own tuning). Keep it that way.
- The user should get IP counsel to review name, art and a patent
  freedom-to-operate check before launch.

## Reference

Research teardown of the reference game (background, not the spec):
"Sugar Supreme Powernudge: Mechanics Teardown & Design Blueprint",
https://claude.ai/artifact/FTp3ir9Sach9xw9quCfLoi

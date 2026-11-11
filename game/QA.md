# QA report

Development build, play money only. Not real-money ready: the RNG is not certified.

## What was tested

| Area | Check | Result |
| --- | --- | --- |
| Maths | `math/tests` rule tests | 19 passed |
| Schema | All 491 golden rounds validate against `game/schema/round.schema.json` | Passed |
| Server | 3,000 seeded spins validate; balance arithmetic exact in integer minor units | Passed |
| Server | Buys work on `default`, return 403 on `gb`; super buy start marks are 5, 10 or 15 | Passed |
| Server | Off-ladder bets rejected (422); GB 2.5 s cycle enforced (429); seeded server repeats rounds | Passed |
| Server | 200,000 spins: hit rate 31.7% ± 0.4, free spins between 1 in 220 and 1 in 310 | Passed |
| Client | Timeline total equals the record win for every golden round; marks equal `marks_after` | Passed |
| Client | 6,250 pre-drawn engine rounds build timelines with matching totals and consistent slides | Passed |
| Browser | Base spins, a Grudge Match buy, a full Title Fight, tier panel, outro, rules screen | Ran with no console errors |
| Browser | GB preset: no buy sign, no autoplay, no speed-up, net position and session time shown | Confirmed |
| Browser | Replay of `golden/free_spins.json` and static demo mode | Ran with no errors |

| Browser | Title Fight played at each violence level (0, 1, 2) after the dark restyle | Ran with no console errors |

## Known gaps

- No sound yet. Every hook is wired in `game/client/src/audio.ts`; the sounds are the next pass.
- Landscape only. The stage scales to fit, so a phone held upright shows a small letterboxed game. A portrait layout is not designed.
- The full 10,000-round soak through the browser was not run. The timeline soak covers 6,250 rounds; the browser run covers a few dozen.
- The Knockout (5,000x) ending is covered by timeline tests on the golden cap round but was not watched in the browser.
- No scatter fly-to-belt animation and no multiplier-reveal beat; the belt count bumps instead.
- Autoplay is a fixed 25 spins with no settings panel.
- Session wallet and round store are in memory and reset when the server restarts.
- Fonts are stand-ins (Kanit, Barlow) loaded from Google Fonts.
- The static demo picks from a finite library of pre-drawn rounds, so its return is not a faithful RTP sample.

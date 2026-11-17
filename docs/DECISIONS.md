# Decisions

Short dated log of decisions the owner has made.

| Date | Decision |
| --- | --- |
| 2026-11-10 | Game name: Goated Ground & Pound, with Goated branding in the title |
| 2026-11-10 | Mechanic names: Takedown (slide), Ground & Pound (chain), Damage (marks), Title Fight (free spins) |
| 2026-11-10 | Buys named Main Event (standard, 119x) and Grudge Match (super, 505x) |
| 2026-11-10 | Tech stack: kit default. Python FastAPI server importing math/nudgemath; TypeScript, Vite, PixiJS client |
| 2026-11-10 | Bet ladder: 0.20, 0.40, 0.60, 0.80, 1, 2, 4, 5, 10, 20, 50, 100 |
| 2026-11-10 | Base chain frequency stays at about 1 in 8 winning spins (no maths change) |
| 2026-11-10 | Build on the default market preset. GB preset exists but is not the launch target |
| 2026-11-10 | Layout mirrors the reference recording: logo and buy sign left, grid centre, belt right, one control bar |
| 2026-11-10 | Symbols: low = red glove, blue glove, taped fist, MMA glove; high = medal, title belt, stopwatch, ring; scatter = star belt |
| 2026-11-10 | Themed UI pieces: ring frame, tall title belt, fight contract, round card, bell spin button |
| 2026-11-10 | Logo: option D (navy and gold fight badge) with the official Goated lockup on a plaque |
| 2026-11-10 | Host character removed for now |
| 2026-11-10 | Sound effects and music come after the playable build |
| 2026-11-11 | Art direction changed to a darker, "deadly" look: near-black arena, steel cage frame, battle-worn symbols, cracked Damage tiles |
| 2026-11-11 | Three violence levels, set per market (`gore` in the market preset): 0 Menacing (no blood), 1 Bloodied, 2 Brutal (adds blood spray). Default preset 1, GB preset 0 |
| 2026-11-11 | High symbols changed: medal -> chain, stopwatch -> cracked mouthguard, ring -> cage |
| 2026-11-11 | Win tiers renamed Rocked, Brutal, Savage, GOATED Win; the cap stays Knockout |
| 2026-11-12 | Audio: Suno songs (Main Riff for the base game, Title Fight for the bonus) and 28 ElevenLabs sound effects; repeated sounds rotate between takes |
| 2026-11-12 | Base song starts on the loading screen; the arena crowd murmur plays low underneath it |
| 2026-11-12 | Win tier panels hold 1.5 s longer; a finished base-game chain stays on screen 1 s longer |
| 2026-11-12 | Buy prices follow + and - while the buy screen is open; the spin button sits above overlays |
| 2026-11-12 | Title Fight: the spin button toggles normal and turbo speed, with a NORMAL / TURBO label and a glow for turbo |
| 2026-11-12 | Opening Round 1 bell and ring card after "Press anywhere to play" |
| 2026-11-16 | Rules screen written for players: no development-build or RNG notes, no violence-level preview buttons |
| 2026-11-16 | Buy sign reads "Buy Free Spins"; buy buttons read "Buy Main Event Spins" and "Buy Grudge Match Spins"; info screen has a Scatter section |
| 2026-11-17 | Handed off to the development team |

Open: licensed fonts (Kanit and Barlow are stand-ins), layout-similarity legal review, target markets,
trademark search on the name, whether the title-belt high symbol is too close to the scatter.

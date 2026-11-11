# Goated Ground & Pound

A 6x6 cluster-pays slot. Wins slide the winning reels down a row and pay again (Takedown), and every
winning cell gains a stacking Damage multiplier. Three or more star belts start the Title Fight.

Development build with a play-money balance. Not real-money ready: the RNG is not certified.

## Run it

```bash
pip install numpy numba fastapi "uvicorn[standard]" pytest jsonschema httpx
cd game/client && npm install && npm run build && cd ../..
python game/server/app.py --port 8000        # then open http://localhost:8000
```

URL options: `?market=gb` (Great Britain preset), `?variant=95`, `?demo=1` (no server, pre-drawn rounds),
`?replay=golden/buys.json` (play stored rounds in order). Space spins, speeds up a running spin and dismisses panels.

## Deploy the demo to Vercel

The client deploys as a static site. With no game server behind it, it runs in demo mode on rounds the
maths engine drew in advance (`public/demo-rounds.json`), so it is for showing the game, not for measuring RTP.

```bash
cd game/client
npx vercel            # preview deployment; follow the login and link prompts
npx vercel --prod     # production, once the preview looks right
```

From the Vercel dashboard instead: import the Git repository and set the project's Root Directory to
`game/client`. `vercel.json` there supplies the rest.

## Test it

```bash
cd math && python -m pytest -q tests                  # 19 rule tests
cd .. && python -m pytest -q game/server/tests         # schema, money, markets, seeded repeat, hit rate
cd game/client && npm test                             # timeline against golden rounds, 6,250-round soak
```

## Layout

```
math/            maths engine, simulator, golden rounds (do not edit by hand)
game/server/     FastAPI service wrapping the engine; returns round records
game/client/     TypeScript + PixiJS client; animates round records only
game/schema/     JSON Schema for round records
game/markets/    market presets (default, gb)
game/theme.json  names and art for symbols, mechanics and win tiers
game/tools/      make_demo_library.py pre-draws rounds for the static demo
docs/            game design, build plan, decisions
```

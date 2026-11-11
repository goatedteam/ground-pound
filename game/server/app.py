"""Game server: wraps the maths engine (math/nudgemath) and returns round records.

The client never decides an outcome. Every spin and buy is produced here by
nudgemath.rounds and returned as a round record.

NOT REAL-MONEY READY: the RNG below is numpy's generator, which is not a
certified RNG, and the wallet is play money held in memory.
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "math"))

from nudgemath.config import game, load  # noqa: E402
from nudgemath.rounds import base_round, buy_round  # noqa: E402

CONFIG_PATH = ROOT / "math" / "game_config.json"
MARKETS_DIR = ROOT / "game" / "markets"
THEME_PATH = ROOT / "game" / "theme.json"
CLIENT_DIST = ROOT / "game" / "client" / "dist"
START_BALANCE_MINOR = 1_000_000

CFG = load(str(CONFIG_PATH))
THEME = json.loads(THEME_PATH.read_text())
GAMES = {v: game(CFG, v) for v in CFG["variants"]}
MARKETS = {p.stem: json.loads(p.read_text()) for p in sorted(MARKETS_DIR.glob("*.json"))}
SEED = os.environ.get("GAME_SEED")


def new_rng(index):
    """Dev RNG. TODO: replace with a certified RNG before any real-money use."""
    if SEED is not None:
        return np.random.default_rng([int(SEED), index])
    return np.random.default_rng(int.from_bytes(os.urandom(16), "little"))


def hundredths(x):
    """Stake multiples to integer hundredths of stake. Exact: pays are multiples of 0.05."""
    return int(round(x * 100))


def to_minor(x, bet_minor):
    """Stake multiples to integer minor units. Whole for every ladder bet (multiples of 20)."""
    value = hundredths(x) * bet_minor
    assert value % 100 == 0, "bet must be a multiple of 20 minor units"
    return value // 100


class Store:
    def __init__(self):
        self.sessions, self.rounds, self.count = {}, {}, 0


STORE = Store()
app = FastAPI(title="Goated Ground & Pound game server (dev, play money)")


class SessionIn(BaseModel):
    market: str = "default"
    variant: str = "96"


class SpinIn(BaseModel):
    session_id: str
    bet_minor: int


class BuyIn(SpinIn):
    kind: str


def market_or_404(name):
    if name not in MARKETS:
        raise HTTPException(404, f"unknown market '{name}'")
    return MARKETS[name]


@app.get("/api/config")
def get_config(market: str = "default", variant: str = "96"):
    m = market_or_404(market)
    if variant not in GAMES:
        raise HTTPException(404, f"unknown variant '{variant}'")
    buys = None
    if m["buys"]:
        buys = {k: {"price": CFG["buy"][k]["price"], "name": THEME["buys"][k]} for k in ("standard", "super")}
        buys["standard"]["start_spins"] = CFG["buy"]["standard"]["start_spins"]
        buys["super"]["preheat_values"] = CFG["buy"]["super"]["preheat_values"]
    return {
        "name": THEME["name"], "theme": THEME, "market": m, "variant": variant,
        "rtp_target": f"{variant}%", "symbols": CFG["symbols"], "paytable": CFG["paytable"],
        "rules": CFG["rules"], "base_nudge_probability": CFG["variants"][variant]["base_nudge_probability"],
        "buys": buys, "certified": False,
        "notice": "Development build. Play money only. The RNG is not certified.",
    }


@app.post("/api/session")
def post_session(body: SessionIn):
    market_or_404(body.market)
    if body.variant not in GAMES:
        raise HTTPException(404, f"unknown variant '{body.variant}'")
    sid = uuid.uuid4().hex
    STORE.sessions[sid] = {"market": body.market, "variant": body.variant, "balance_minor": START_BALANCE_MINOR,
                           "rng": new_rng(len(STORE.sessions)), "last_round": 0.0, "staked_minor": 0, "won_minor": 0,
                           "started": time.time()}
    return {"session_id": sid, "balance_minor": START_BALANCE_MINOR}


def play(sid, bet_minor, make_round, cost_x):
    s = STORE.sessions.get(sid)
    if s is None:
        raise HTTPException(404, "unknown session")
    m = MARKETS[s["market"]]
    if bet_minor not in m["bet_ladder_minor"]:
        raise HTTPException(422, "bet is not on this market's bet ladder")
    now = time.monotonic()
    if m["min_cycle_ms"] and (now - s["last_round"]) * 1000 < m["min_cycle_ms"]:
        raise HTTPException(429, "minimum game-cycle time not reached")
    cost_minor = to_minor(cost_x, bet_minor)
    if s["balance_minor"] < cost_minor:
        raise HTTPException(402, "insufficient balance")
    record = make_round(GAMES[s["variant"]], s["rng"])
    win_minor = to_minor(record["win"], bet_minor)
    # one atomic step per round: debit the cost, credit the win
    s["balance_minor"] += win_minor - cost_minor
    s["staked_minor"] += cost_minor
    s["won_minor"] += win_minor
    s["last_round"] = now
    STORE.count += 1
    rid = f"r{STORE.count:08d}"
    out = {"round_id": rid, "round": record, "bet_minor": bet_minor, "cost_minor": cost_minor,
           "win_minor": win_minor, "balance_minor": s["balance_minor"],
           "net_position_minor": s["won_minor"] - s["staked_minor"]}
    STORE.rounds[rid] = out
    return out


@app.post("/api/spin")
def post_spin(body: SpinIn):
    return play(body.session_id, body.bet_minor, base_round, 1)


@app.post("/api/buy")
def post_buy(body: BuyIn):
    s = STORE.sessions.get(body.session_id)
    if s is None:
        raise HTTPException(404, "unknown session")
    if not MARKETS[s["market"]]["buys"]:
        raise HTTPException(403, "bonus buys are not offered in this market")
    if body.kind not in ("standard", "super"):
        raise HTTPException(422, "kind must be 'standard' or 'super'")
    price = CFG["buy"][body.kind]["price"]
    return play(body.session_id, body.bet_minor, lambda g, rng: buy_round(g, rng, body.kind, price), price)


@app.get("/api/rounds/{round_id}")
def get_round(round_id: str):
    if round_id not in STORE.rounds:
        raise HTTPException(404, "unknown round")
    return STORE.rounds[round_id]


if CLIENT_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(CLIENT_DIST), html=True), name="client")


if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=None, help="reproducible rounds for QA")
    a = ap.parse_args()
    if a.seed is not None:
        SEED = str(a.seed)
    uvicorn.run(app, host="0.0.0.0", port=a.port)

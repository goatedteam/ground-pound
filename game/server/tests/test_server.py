import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "game" / "server"))
os.environ["GAME_SEED"] = "12345"
import app as server  # noqa: E402

SCHEMA = json.loads((ROOT / "game" / "schema" / "round.schema.json").read_text())
VALID = Draft202012Validator(SCHEMA)
client = TestClient(server.app)


def session(market="default"):
    return client.post("/api/session", json={"market": market, "variant": "96"}).json()["session_id"]


@pytest.mark.parametrize("name", ["base", "free_spins", "buys"])
def test_golden_vectors_match_schema(name):
    data = json.loads((ROOT / "math" / "golden" / f"{name}.json").read_text())
    for r in data["rounds"]:
        VALID.validate(r)


def test_server_rounds_validate_and_money_is_exact():
    sid = session()
    balance = server.START_BALANCE_MINOR
    for i in range(3000):
        out = client.post("/api/spin", json={"session_id": sid, "bet_minor": 60}).json()
        VALID.validate(out["round"])
        assert out["cost_minor"] == 60
        assert out["win_minor"] == round(out["round"]["win"] * 100) * 60 // 100
        balance += out["win_minor"] - out["cost_minor"]
        assert out["balance_minor"] == balance
        if balance < 60:
            break


def test_buys_work_and_are_blocked_in_gb():
    sid = session()
    out = client.post("/api/buy", json={"session_id": sid, "bet_minor": 20, "kind": "standard"})
    assert out.status_code == 200
    body = out.json()
    VALID.validate(body["round"])
    assert body["cost_minor"] == 119 * 20 and body["round"]["mode"] == "buy_standard"
    sup = client.post("/api/buy", json={"session_id": sid, "bet_minor": 20, "kind": "super"}).json()
    assert sup["cost_minor"] == 505 * 20
    assert all(v in (5, 10, 15) for row in sup["round"]["free_spins"]["start_marks"] for v in row)
    gb = session("gb")
    assert client.post("/api/buy", json={"session_id": gb, "bet_minor": 20, "kind": "standard"}).status_code == 403
    assert client.get("/api/config?market=gb").json()["buys"] is None


def test_off_ladder_bet_rejected():
    sid = session()
    assert client.post("/api/spin", json={"session_id": sid, "bet_minor": 30}).status_code == 422
    assert client.post("/api/spin", json={"session_id": sid, "bet_minor": 7}).status_code == 422


def test_gb_cycle_time_enforced():
    gb = session("gb")
    assert client.post("/api/spin", json={"session_id": gb, "bet_minor": 100}).status_code == 200
    assert client.post("/api/spin", json={"session_id": gb, "bet_minor": 100}).status_code == 429


def test_seeded_server_reproduces_rounds():
    server.STORE.sessions.clear()
    a = session()
    first = [client.post("/api/spin", json={"session_id": a, "bet_minor": 100}).json()["round"] for _ in range(50)]
    server.STORE.sessions.clear()
    b = session()
    second = [client.post("/api/spin", json={"session_id": b, "bet_minor": 100}).json()["round"] for _ in range(50)]
    assert first == second


def test_stored_round_can_be_fetched():
    sid = session()
    out = client.post("/api/spin", json={"session_id": sid, "bet_minor": 100}).json()
    assert client.get(f"/api/rounds/{out['round_id']}").json() == out


def test_hit_rate_and_bonus_frequency_sanity():
    g = server.GAMES["96"]
    import numpy as np
    from nudgemath.rounds import base_round
    rng = np.random.default_rng(7)
    n, hits, bonus = 200_000, 0, 0
    for _ in range(n):
        r = base_round(g, rng)
        hits += r["base_spin"]["steps"][0]["win"] > 0
        bonus += r["free_spins"] is not None
    assert abs(hits / n - 0.3168) < 0.004
    assert 220 <= n / bonus <= 310

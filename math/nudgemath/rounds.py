"""Round records: the complete, step-by-step result of one bet as plain JSON.

A round record is the contract between the maths and everything else:
  - the game server returns one record per bet,
  - the client only animates a record and never decides an outcome,
  - golden vectors are records, so any port of the engine can be checked.

Every random draw is resolved into the record (reel stops, the base nudge
roll, free-spin start count, super-buy starting marks), so a record can be
replayed exactly without an RNG.

Wins are multiples of total stake, rounded to 2 decimals. Every pay in the
paytable is a multiple of 0.05 and multipliers are whole numbers, so the
values are exact; ports should hold money as integer hundredths of stake.
"""

import numpy as np

from . import engine as E


def _grid(a):
    return [[int(x) for x in row] for row in a]


def spin_record(reel_set, strips, lengths, stops, mult, paytable, always_nudge,
                nudge_roll, upgrade_before_pay, cap_left):
    """One spin (base or free) from given stops. mult is updated in place."""
    label, csize, csym, cells, stack, winmask, reelmask = E.new_work()[3:]
    stops = np.array(stops, dtype=np.int64)
    landing = [int(s) for s in stops]
    grid = np.zeros((6, 6), dtype=np.int8)
    E.fill_grid(strips, lengths, stops, grid)
    scatters = E.count_scatters(grid)
    steps, total, nudging, first, capped = [], 0.0, always_nudge, True, False
    while True:
        step = {"grid": _grid(grid), "marks_before": _grid(mult)}
        clusters = []
        for k in range(E.find_clusters(grid, label, csize, csym, cells, stack)):
            if csize[k] < E.MIN_CLUSTER:
                continue
            rc = sorted([int(i) // 6, int(i) % 6] for i in cells[k, :csize[k]])
            if upgrade_before_pay:
                m = sum(mult[r, c] + 1 for r, c in rc if mult[r, c] > 0)
            else:
                m = sum(mult[r, c] for r, c in rc)
            factor = int(m) if m > 0 else 1
            base_pay = float(paytable[csym[k], min(int(csize[k]), 15)])
            clusters.append({"symbol": int(csym[k]), "size": int(csize[k]), "cells": rc,
                             "base_pay": round(base_pay, 2), "multiplier": factor,
                             "pay": round(base_pay * factor, 2)})
        win, any_win = E.evaluate(grid, mult, paytable, upgrade_before_pay,
                                  label, csize, csym, cells, stack, winmask, reelmask)
        step["clusters"] = clusters
        step["win"] = round(win, 2)
        step["marks_after"] = _grid(mult)
        if not any_win:
            steps.append(step)
            break
        assert abs(sum(c["pay"] for c in clusters) - win) < 1e-6
        total += win
        if total >= cap_left:
            step["capped"] = True
            steps.append(step)
            total, capped = cap_left, True
            break
        if first:
            first = False
            if not always_nudge:
                nudging = bool(nudge_roll)
        if not nudging:
            steps.append(step)
            break
        reels = [c for c in range(6) if reelmask[c]]
        new = E.nudge(grid, strips, lengths, stops, reelmask)
        step["nudged_reels"] = reels
        step["entered"] = [int(grid[0, c]) for c in reels]
        step["new_scatters"] = int(new)
        scatters += new
        steps.append(step)
    return {"reel_set": reel_set, "stops": landing,
            "nudge_roll": None if always_nudge else bool(nudge_roll),
            "steps": steps, "scatters": int(scatters), "win": round(total, 2),
            "capped": capped}


def free_spins_record(g, rng, awarded, mult, cap_left):
    start_marks = _grid(mult)
    spins, total, left, retriggers, capped = [], 0.0, awarded, 0, False
    while left > 0:
        left -= 1
        stops = [int(rng.integers(g.bonus_lengths[c])) for c in range(6)]
        rec = spin_record("bonus", g.bonus_strips, g.bonus_lengths, stops, mult,
                          g.paytable, True, None, g.upgrade_before_pay, cap_left - total)
        total += rec["win"]
        rec["retrigger"] = (not rec["capped"]) and rec["scatters"] >= 3
        if rec["capped"]:
            total, capped = cap_left, True
        elif rec["retrigger"]:
            left += g.retrigger_spins
            retriggers += 1
        rec["spins_left"] = left
        spins.append(rec)
        if capped:
            break
    return {"awarded": int(awarded), "start_marks": start_marks, "spins": spins,
            "retriggers": retriggers, "win": round(total, 2), "capped": capped}


def base_round(g, rng):
    stops = [int(rng.integers(g.base_lengths[c])) for c in range(6)]
    roll = bool(rng.random() < g.p_nudge)
    mult = np.zeros((6, 6), dtype=np.int32)
    spin = spin_record("base", g.base_strips, g.base_lengths, stops, mult, g.paytable,
                       False, roll, g.upgrade_before_pay, g.cap)
    rec = {"mode": "base", "cost": 1, "base_spin": spin, "free_spins": None}
    total = spin["win"]
    if not spin["capped"] and spin["scatters"] >= 3:
        awarded = int(g.award[min(spin["scatters"], 63)])
        fs = free_spins_record(g, rng, awarded, np.zeros((6, 6), dtype=np.int32),
                               g.cap - total)
        rec["free_spins"] = fs
        total += fs["win"]
    rec["win"] = round(min(total, g.cap), 2)
    rec["capped"] = rec["win"] >= g.cap
    return rec


def buy_round(g, rng, kind, price):
    u = rng.random() * g.buy_cum[-1]
    awarded = int(g.buy_spins[np.searchsorted(g.buy_cum, u, side="right")])
    mult = np.zeros((6, 6), dtype=np.int32)
    if kind == "super":
        probs = np.diff(np.concatenate([[0.0], g.preheat_cum]))
        for i in rng.choice(36, size=g.preheat_cells, replace=False):
            mult[i // 6, i % 6] = int(rng.choice(g.preheat_values, p=probs / probs.sum()))
    fs = free_spins_record(g, rng, awarded, mult, g.cap)
    return {"mode": f"buy_{kind}", "cost": price, "base_spin": None, "free_spins": fs,
            "win": fs["win"], "capped": fs["capped"]}

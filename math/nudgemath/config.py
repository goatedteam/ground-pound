"""Game configuration: load, save and convert to arrays for the engine.

The config is one JSON file holding every tunable value: paytable, rules,
reel strips, the base-game nudge probability for each RTP variant, and the
bonus-buy settings.
"""

import json
from dataclasses import dataclass

import numpy as np

SYMBOL_NAMES = ["low1", "low2", "low3", "low4", "high1", "high2", "high3", "high4"]

# Reference paytable (x total stake), cluster sizes 5..14 and 15+.
# Rows = cluster size, columns = symbols low1..high4.
REFERENCE_PAYTABLE = {
    "5":  [0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00],
    "6":  [0.15, 0.20, 0.25, 0.35, 0.45, 0.60, 1.00, 1.25],
    "7":  [0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.25, 1.50],
    "8":  [0.30, 0.40, 0.50, 0.60, 0.75, 1.00, 1.50, 2.00],
    "9":  [0.40, 0.50, 0.60, 0.75, 1.00, 1.50, 2.00, 2.50],
    "10": [0.50, 0.60, 0.75, 1.00, 1.50, 2.00, 2.50, 3.00],
    "11": [0.75, 1.00, 1.25, 1.50, 2.50, 3.00, 4.00, 5.00],
    "12": [1.00, 1.25, 1.50, 2.00, 3.00, 4.00, 6.00, 7.50],
    "13": [2.00, 2.50, 3.00, 4.00, 6.00, 8.00, 12.00, 15.00],
    "14": [3.00, 4.00, 5.00, 6.00, 8.00, 10.00, 15.00, 20.00],
    "15+": [10.00, 15.00, 20.00, 30.00, 40.00, 50.00, 75.00, 100.00],
}


def load(path):
    with open(path) as f:
        return json.load(f)


def save(cfg, path):
    with open(path, "w") as f:
        json.dump(cfg, f, indent=1)
        f.write("\n")


def paytable_array(cfg):
    pt = np.zeros((8, 16), dtype=np.float64)
    for key, row in cfg["paytable"].items():
        size = 15 if key == "15+" else int(key)
        pt[:, size] = row
    return pt


def strips_array(strips):
    lengths = np.array([len(s) for s in strips], dtype=np.int64)
    arr = np.zeros((6, lengths.max()), dtype=np.int8)
    for c, s in enumerate(strips):
        arr[c, : len(s)] = s
    return arr, lengths


def award_array(cfg):
    """Free spins by scatter count; counts above the table use the top tier."""
    table = {int(k): v for k, v in cfg["rules"]["free_spins_award"].items()}
    top = max(table)
    out = np.zeros(64, dtype=np.int64)
    for k in range(64):
        out[k] = table.get(k, table[top] if k > top else 0)
    return out


def weighted(table):
    """{"value": weight} -> (values, cumulative weights) for the engine."""
    values = np.array([int(k) for k in table], dtype=np.int64)
    cum = np.cumsum([float(v) for v in table.values()])
    return values, cum


@dataclass
class Game:
    base_strips: np.ndarray
    base_lengths: np.ndarray
    bonus_strips: np.ndarray
    bonus_lengths: np.ndarray
    paytable: np.ndarray
    p_nudge: float
    upgrade_before_pay: bool
    cap: float
    retrigger_spins: int
    award: np.ndarray
    buy_spins: np.ndarray
    buy_cum: np.ndarray
    preheat_cells: int
    preheat_values: np.ndarray
    preheat_cum: np.ndarray


def game(cfg, variant):
    bs, bl = strips_array(cfg["base_strips"])
    fs, fl = strips_array(cfg["bonus_strips"])
    buy_spins, buy_cum = weighted(cfg["buy"]["standard"]["start_spins"])
    sup = cfg["buy"]["super"]
    pv, pc = weighted(sup["preheat_values"])
    return Game(
        base_strips=bs, base_lengths=bl, bonus_strips=fs, bonus_lengths=fl,
        paytable=paytable_array(cfg),
        p_nudge=float(cfg["variants"][str(variant)]["base_nudge_probability"]),
        upgrade_before_pay=bool(cfg["rules"]["upgrade_before_pay"]),
        cap=float(cfg["rules"]["max_win"]),
        retrigger_spins=int(cfg["rules"]["retrigger_spins"]),
        award=award_array(cfg),
        buy_spins=buy_spins, buy_cum=buy_cum,
        preheat_cells=int(sup["preheat_cells"]), preheat_values=pv, preheat_cum=pc,
    )

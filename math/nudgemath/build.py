"""Build a full game config from strip shape parameters.

`make_config(params)` turns the compact tuning parameters into the complete
JSON config the engine and simulator read (paytable, rules, generated reel
strips, variants, buys). The tuned parameters live in tuned_params.json.
"""

import copy

from .config import REFERENCE_PAYTABLE, SYMBOL_NAMES
from .strips import make_strip_set

DEFAULT_PARAMS = {
    "base_strips": {"length": 200, "weights": [12, 10, 8, 7, 5, 4, 3, 2],
                    "run_mean": 1.6, "run_max": 5, "scatters": [2, 2, 2, 2, 2, 2],
                    "seed": 1000},
    "bonus_strips": {"length": 200, "weights": [12, 10, 8, 7, 5, 4, 3, 2],
                     "run_mean": 2.2, "run_max": 6, "scatters": [1, 1, 1, 1, 1, 1],
                     "seed": 2000},
    "variants": {"96": {"base_nudge_probability": 0.10},
                 "95": {"base_nudge_probability": 0.07},
                 "94": {"base_nudge_probability": 0.04}},
    "buy": {
        "standard": {"price": 120, "start_spins": {"10": 1.0}},
        "super": {"price": 480, "preheat_cells": 8,
                  "preheat_values": {"2": 5, "3": 3, "5": 2}},
    },
}


def make_config(params, name="Cluster Nudge (working title)"):
    p = copy.deepcopy(params)
    return {
        "name": name,
        "notes": "All pays and wins are multiples of total stake. Symbol 8 is the scatter.",
        "symbols": SYMBOL_NAMES + ["scatter"],
        "paytable": copy.deepcopy(p.get("paytable", REFERENCE_PAYTABLE)),
        "rules": {
            "grid": [6, 6],
            "min_cluster": 5,
            "upgrade_before_pay": False,
            "max_win": 5000,
            "free_spins_award": {"3": 10, "4": 12, "5": 15, "6": 20},
            "retrigger_spins": 10,
            "one_scatter_per_reel": True,
            "scatters_count_across_chain": True,
        },
        "variants": p["variants"],
        "buy": p["buy"],
        "strip_params": {"base": p["base_strips"], "bonus": p["bonus_strips"]},
        "base_strips": make_strip_set(p["base_strips"]),
        "bonus_strips": make_strip_set(p["bonus_strips"]),
    }

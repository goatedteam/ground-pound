"""Monte Carlo simulators.

Three simulations, all run in parallel worker processes:

    sim_base   base-game spins only: base RTP, hit rate, nudge rate,
               scatter counts and therefore bonus frequency
    sim_bonus  free-spins rounds only, from a start-spin distribution and an
               optional preheat (super buy): bonus value and its spread
    sim_full   the whole game, base spins plus any bonus they trigger, with
               the 5,000x cap applied to the full round

The base + bonus split is the fast way to tune. sim_full is the check.
Every win is in multiples of total stake.
"""

import math
import multiprocessing as mp
import os

import numpy as np
from numba import njit

from . import engine as E

# Win buckets for distribution tables (x stake). The last bucket is the cap.
EDGES = np.array([0.0, 1e-12, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000])
BUCKET_LABELS = ["0", "under 1x", "1-2x", "2-5x", "5-10x", "10-20x", "20-50x",
                 "50-100x", "100-200x", "200-500x", "500-1,000x",
                 "1,000-2,000x", "2,000-5,000x", "5,000x cap"]


@njit(cache=True)
def bucket(x):
    return np.searchsorted(EDGES, x, side="right") - 1


# ---------------------------------------------------------------------------
# Kernels
# ---------------------------------------------------------------------------


@njit(cache=True)
def sim_base_kernel(n, seed, strips, lengths, paytable, p_nudge, ubp, cap):
    np.random.seed(seed)
    grid, mult, stops, label, csize, csym, cells, stack, winmask, reelmask = E.new_work()
    s = np.zeros(12)
    scat_hist = np.zeros(16, dtype=np.int64)
    win_hist = np.zeros(len(EDGES), dtype=np.int64)
    for _ in range(n):
        win, sc, nudges, capped = E.base_spin(
            strips, lengths, paytable, p_nudge, ubp, cap,
            grid, mult, stops, label, csize, csym, cells, stack, winmask, reelmask)
        s[0] += win
        s[1] += win * win
        if win > 0:
            s[2] += 1
        if nudges > 0:
            s[3] += 1
            s[4] += nudges
            s[5] += win
        if capped:
            s[6] += 1
        if win > s[7]:
            s[7] = win
        if sc >= 3:
            s[8] += 1
        if win > 0 or sc >= 3:
            s[9] += 1
        scat_hist[min(sc, 15)] += 1
        win_hist[bucket(win)] += 1
    return s, scat_hist, win_hist


@njit(cache=True)
def sim_bonus_kernel(n, seed, strips, lengths, paytable, ubp, cap, retrig,
                     start_values, start_cum, pre_n, pre_values, pre_cum):
    np.random.seed(seed)
    grid, mult, stops, label, csize, csym, cells, stack, winmask, reelmask = E.new_work()
    s = np.zeros(10)
    win_hist = np.zeros(len(EDGES), dtype=np.int64)
    for _ in range(n):
        u = np.random.random() * start_cum[-1]
        start = start_values[np.searchsorted(start_cum, u, side="right")]
        E.clear_mult(mult)
        if pre_n > 0:
            E.preheat(mult, pre_n, pre_values, pre_cum)
        win, played, retriggers, capped = E.play_bonus(
            start, strips, lengths, paytable, ubp, cap, retrig,
            grid, mult, stops, label, csize, csym, cells, stack, winmask, reelmask)
        s[0] += win
        s[1] += win * win
        s[2] += played
        s[3] += retriggers
        if retriggers > 0:
            s[4] += 1
        if capped:
            s[5] += 1
        if win > s[6]:
            s[6] = win
        if win < 20:
            s[7] += 1
        win_hist[bucket(win)] += 1
    return s, win_hist


@njit(cache=True)
def sim_full_kernel(n, seed, bstrips, blengths, fstrips, flengths, paytable,
                    p_nudge, ubp, cap, retrig, award):
    np.random.seed(seed)
    grid, mult, stops, label, csize, csym, cells, stack, winmask, reelmask = E.new_work()
    s = np.zeros(12)
    win_hist = np.zeros(len(EDGES), dtype=np.int64)
    for _ in range(n):
        win, sc, nudges, capped = E.base_spin(
            bstrips, blengths, paytable, p_nudge, ubp, cap,
            grid, mult, stops, label, csize, csym, cells, stack, winmask, reelmask)
        total = win
        if not capped and sc >= 3:
            E.clear_mult(mult)
            bw, played, retriggers, capped = E.play_bonus(
                award[min(sc, 63)], fstrips, flengths, paytable, ubp, cap - win,
                retrig, grid, mult, stops, label, csize, csym, cells, stack,
                winmask, reelmask)
            total = win + bw
            s[5] += 1
            s[3] += bw
            s[8] += bw * bw
        s[0] += total
        s[1] += total * total
        s[2] += win
        if total > 0:
            s[4] += 1
        if capped:
            s[6] += 1
        if total > s[7]:
            s[7] = total
        win_hist[bucket(total)] += 1
    return s, win_hist


# ---------------------------------------------------------------------------
# Parallel runner
# ---------------------------------------------------------------------------

_KERNELS = {"base": sim_base_kernel, "bonus": sim_bonus_kernel, "full": sim_full_kernel}
WORKERS = int(os.environ.get("NUDGE_WORKERS", os.cpu_count() or 1))


def _job(args):
    name, n, seed, rest = args
    return _KERNELS[name](n, seed, *rest)


def _warm():
    """Compile every kernel once in the parent so forked workers reuse it."""
    from .config import REFERENCE_PAYTABLE  # noqa: F401
    strips = np.zeros((6, 12), dtype=np.int8)
    for c in range(6):
        strips[c] = (np.arange(12) + c) % 8
    lengths = np.full(6, 12, dtype=np.int64)
    pt = np.ones((8, 16))
    one = np.array([10], dtype=np.int64)
    cum = np.array([1.0])
    sim_base_kernel(10, 1, strips, lengths, pt, 0.5, False, 5000.0)
    sim_bonus_kernel(2, 1, strips, lengths, pt, False, 5000.0, 10, one, cum, 1, one, cum)
    sim_full_kernel(10, 1, strips, lengths, strips, lengths, pt, 0.5, False, 5000.0, 10,
                    np.full(64, 10, dtype=np.int64))


_warmed = False


def run(name, n, seed, *rest, workers=None, chunks_per_worker=2):
    """Split n draws across worker processes and add up their results."""
    global _warmed
    if not _warmed:
        _warm()
        _warmed = True
    workers = workers or WORKERS
    k = max(1, min(n, workers * chunks_per_worker))
    sizes = [n // k + (1 if i < n % k else 0) for i in range(k)]
    jobs = [(name, sizes[i], seed * 1_000_003 + i * 7919, rest) for i in range(k)]
    if workers == 1 or k == 1:
        results = [_job(j) for j in jobs]
    else:
        with mp.get_context("fork").Pool(workers) as pool:
            results = pool.map(_job, jobs)
    return [_combine([r[i] for r in results], i == 0 and _MAX_SLOT[name])
            for i in range(len(results[0]))]


# Index of the "largest win" slot in each kernel's first stats array: chunks
# are added together except this slot, which takes the largest value.
_MAX_SLOT = {"base": 7, "bonus": 6, "full": 7}


def _combine(parts, max_slot):
    total = sum(parts)
    if max_slot:
        total[max_slot] = max(p[max_slot] for p in parts)
    return total


# ---------------------------------------------------------------------------
# Friendly wrappers returning dicts
# ---------------------------------------------------------------------------


def base(g, n, seed=1):
    s, scat, hist = run("base", n, seed, g.base_strips, g.base_lengths, g.paytable,
                        g.p_nudge, g.upgrade_before_pay, g.cap)
    mean = s[0] / n
    sd = math.sqrt(max(s[1] / n - mean * mean, 0.0))
    trig = scat[3:].sum()
    natural = {int(g.award[k]): 0.0 for k in range(3, 16)}
    for k in range(3, 16):
        natural[int(g.award[k])] += scat[k]
    natural = {k: v / trig for k, v in natural.items() if v} if trig else {}
    return {
        "spins": n,
        "rtp": mean,
        "rtp_ci95": 1.96 * sd / math.sqrt(n),
        "sd": sd,
        "hit_rate": s[2] / n,
        "hit_rate_incl_trigger": s[9] / n,
        "nudge_rate": s[3] / n,
        "nudge_share_of_wins": s[3] / s[2] if s[2] else 0.0,
        "avg_nudges_per_chain": s[4] / s[3] if s[3] else 0.0,
        "chain_rtp": s[5] / n,
        "capped": s[6],
        "max_win": s[7],
        "trigger_rate": s[8] / n,
        "trigger_one_in": n / s[8] if s[8] else float("inf"),
        "scatter_hist": scat.tolist(),
        "natural_start_spins": natural,
        "win_hist": hist.tolist(),
    }


def bonus(g, n, start_spins=None, preheat=False, seed=2):
    """start_spins: {spins: weight}; defaults to the standard buy table."""
    if start_spins is None:
        values, cum = g.buy_spins, g.buy_cum
    else:
        values = np.array(list(start_spins), dtype=np.int64)
        cum = np.cumsum([float(v) for v in start_spins.values()])
    pre_n = g.preheat_cells if preheat else 0
    s, hist = run("bonus", n, seed, g.bonus_strips, g.bonus_lengths, g.paytable,
                  g.upgrade_before_pay, g.cap, g.retrigger_spins, values, cum,
                  pre_n, g.preheat_values, g.preheat_cum)
    mean = s[0] / n
    sd = math.sqrt(max(s[1] / n - mean * mean, 0.0))
    return {
        "rounds": n,
        "mean": mean,
        "mean_ci95": 1.96 * sd / math.sqrt(n),
        "sd": sd,
        "second_moment": s[1] / n,
        "avg_spins": s[2] / n,
        "retrigger_rate": s[4] / n,
        "capped": s[5],
        "capped_one_in": n / s[5] if s[5] else float("inf"),
        "max_win": s[6],
        "share_under_20x": s[7] / n,
        "win_hist": hist.tolist(),
    }


def full(g, n, seed=3):
    s, hist = run("full", n, seed, g.base_strips, g.base_lengths, g.bonus_strips,
                  g.bonus_lengths, g.paytable, g.p_nudge, g.upgrade_before_pay,
                  g.cap, g.retrigger_spins, g.award)
    mean = s[0] / n
    sd = math.sqrt(max(s[1] / n - mean * mean, 0.0))
    return {
        "spins": n,
        "rtp": mean,
        "rtp_ci95": 1.96 * sd / math.sqrt(n),
        "sd": sd,
        "base_rtp": s[2] / n,
        "bonus_rtp": s[3] / n,
        "hit_rate": s[4] / n,
        "bonuses": s[5],
        "bonus_one_in": n / s[5] if s[5] else float("inf"),
        "avg_bonus": s[3] / s[5] if s[5] else 0.0,
        "capped": s[6],
        "capped_one_in": n / s[6] if s[6] else float("inf"),
        "max_win": s[7],
        "win_hist": hist.tolist(),
    }


def combine(b, fs):
    """Whole-game RTP and volatility from a base run and a natural-bonus run."""
    rtp = b["rtp"] + b["trigger_rate"] * fs["mean"]
    second = (b["sd"] ** 2 + b["rtp"] ** 2) + b["trigger_rate"] * fs["second_moment"]
    sd = math.sqrt(max(second - rtp * rtp, 0.0))
    ci = math.sqrt(b["rtp_ci95"] ** 2 + (b["trigger_rate"] * fs["mean_ci95"]) ** 2)
    return {"rtp": rtp, "rtp_ci95": ci, "base_rtp": b["rtp"],
            "bonus_rtp": b["trigger_rate"] * fs["mean"], "sd": sd}

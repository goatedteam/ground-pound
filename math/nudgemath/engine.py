"""Core maths engine for a 6x6 cluster-pays slot with a nudge chain and
grid-position multipliers.

Everything in this file is compiled with numba so the simulator can run
millions of spins quickly. The functions are plain Python underneath, so the
rules can be read top to bottom:

    play_chain   one spin's evaluate -> pay -> mark -> nudge loop
    base_spin    a base-game spin (nudge starts only on a random trigger)
    play_bonus   a free-spins round (every win nudges, marks persist)

Grid coordinates: grid[row, reel], row 0 is the TOP row, row 5 the bottom.
Reel c shows strips[c, (stops[c] + row) % length]. A nudge moves the reel
DOWN one row: the bottom symbol leaves and strips[c, stop - 1] enters at the
top.

Symbols 0..7 pay (0 = lowest, 7 = top symbol). Symbol 8 is the scatter.
Multipliers live on grid cells: 0 = unmarked, k >= 1 = marked with value xk.
"""

import numpy as np
from numba import njit

ROWS = 6
REELS = 6
NCELL = ROWS * REELS
SCATTER = 8
MIN_CLUSTER = 5
MAX_SIZE_INDEX = 15  # clusters of 15 or more pay the 15+ column
MAX_CHAIN = 2000  # safety stop for a single nudge chain
MAX_FREE_SPINS = 5000  # safety stop for a single free-spins round


# ---------------------------------------------------------------------------
# Work buffers (allocated once per simulation, reused every spin)
# ---------------------------------------------------------------------------


@njit(cache=True)
def new_work():
    grid = np.zeros((ROWS, REELS), dtype=np.int8)
    mult = np.zeros((ROWS, REELS), dtype=np.int32)
    stops = np.zeros(REELS, dtype=np.int64)
    label = np.zeros((ROWS, REELS), dtype=np.int16)
    csize = np.zeros(NCELL, dtype=np.int16)
    csym = np.zeros(NCELL, dtype=np.int8)
    cells = np.zeros((NCELL, NCELL), dtype=np.int16)
    stack = np.zeros(NCELL, dtype=np.int16)
    winmask = np.zeros((ROWS, REELS), dtype=np.bool_)
    reelmask = np.zeros(REELS, dtype=np.bool_)
    return grid, mult, stops, label, csize, csym, cells, stack, winmask, reelmask


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------


@njit(cache=True)
def fill_grid(strips, lengths, stops, grid):
    for c in range(REELS):
        length = lengths[c]
        for r in range(ROWS):
            grid[r, c] = strips[c, (stops[c] + r) % length]


@njit(cache=True)
def random_stops(lengths, stops):
    for c in range(REELS):
        stops[c] = np.random.randint(0, lengths[c])


@njit(cache=True)
def count_scatters(grid):
    n = 0
    for r in range(ROWS):
        for c in range(REELS):
            if grid[r, c] == SCATTER:
                n += 1
    return n


@njit(cache=True)
def clear_mult(mult):
    for r in range(ROWS):
        for c in range(REELS):
            mult[r, c] = 0


# ---------------------------------------------------------------------------
# Cluster detection: orthogonal flood fill, scatters never join clusters
# ---------------------------------------------------------------------------


@njit(cache=True)
def find_clusters(grid, label, csize, csym, cells, stack):
    """Label every connected group of identical paying symbols.

    Returns the number of groups. Group k has csize[k] cells of symbol
    csym[k]; its cell indices (row * REELS + reel) are cells[k, :csize[k]].
    Groups smaller than MIN_CLUSTER are returned too; callers skip them.
    """
    for r in range(ROWS):
        for c in range(REELS):
            label[r, c] = -1
    n = 0
    for r in range(ROWS):
        for c in range(REELS):
            if label[r, c] != -1:
                continue
            s = grid[r, c]
            if s == SCATTER:
                continue
            label[r, c] = n
            top = 0
            stack[0] = r * REELS + c
            size = 0
            while top >= 0:
                idx = stack[top]
                top -= 1
                cells[n, size] = idx
                size += 1
                rr = idx // REELS
                cc = idx - rr * REELS
                if rr > 0 and label[rr - 1, cc] == -1 and grid[rr - 1, cc] == s:
                    label[rr - 1, cc] = n
                    top += 1
                    stack[top] = idx - REELS
                if rr < ROWS - 1 and label[rr + 1, cc] == -1 and grid[rr + 1, cc] == s:
                    label[rr + 1, cc] = n
                    top += 1
                    stack[top] = idx + REELS
                if cc > 0 and label[rr, cc - 1] == -1 and grid[rr, cc - 1] == s:
                    label[rr, cc - 1] = n
                    top += 1
                    stack[top] = idx - 1
                if cc < REELS - 1 and label[rr, cc + 1] == -1 and grid[rr, cc + 1] == s:
                    label[rr, cc + 1] = n
                    top += 1
                    stack[top] = idx + 1
            csize[n] = size
            csym[n] = s
            n += 1
    return n


# ---------------------------------------------------------------------------
# One evaluation: find wins, pay them, mark the cells
# ---------------------------------------------------------------------------


@njit(cache=True)
def evaluate(grid, mult, paytable, upgrade_before_pay,
             label, csize, csym, cells, stack, winmask, reelmask):
    """Pay every cluster of 5+ and update the position multipliers.

    Pay rule: cluster pay = paytable[symbol, min(size, 15)] x M, where M is
    the sum of the multipliers on the cluster's cells that were already
    marked before this evaluation (M = 1 if none were).

    Reading B (upgrade_before_pay = False, the decided spec): every winning
    cell gets +1 AFTER the pay, so a repeat cell's +1 counts from the next
    pay. A fresh cell goes 0 -> 1.

    Reading A (upgrade_before_pay = True, kept for comparison): winning
    cells that were already marked get +1 BEFORE the pay; fresh cells are
    marked x1 after it.

    Returns (win, any_win). winmask and reelmask are filled for the nudge.
    """
    n = find_clusters(grid, label, csize, csym, cells, stack)
    for c in range(REELS):
        reelmask[c] = False
    for r in range(ROWS):
        for c in range(REELS):
            winmask[r, c] = False

    any_win = False
    for k in range(n):
        size = csize[k]
        if size < MIN_CLUSTER:
            continue
        any_win = True
        for j in range(size):
            idx = cells[k, j]
            r = idx // REELS
            c = idx - r * REELS
            winmask[r, c] = True
            reelmask[c] = True
    if not any_win:
        return 0.0, False

    if upgrade_before_pay:
        for r in range(ROWS):
            for c in range(REELS):
                if winmask[r, c] and mult[r, c] > 0:
                    mult[r, c] += 1

    win = 0.0
    for k in range(n):
        size = csize[k]
        if size < MIN_CLUSTER:
            continue
        msum = 0
        for j in range(size):
            idx = cells[k, j]
            r = idx // REELS
            c = idx - r * REELS
            msum += mult[r, c]
        factor = msum if msum > 0 else 1
        col = size if size < MAX_SIZE_INDEX else MAX_SIZE_INDEX
        win += paytable[csym[k], col] * factor

    for r in range(ROWS):
        for c in range(REELS):
            if winmask[r, c]:
                if upgrade_before_pay:
                    if mult[r, c] == 0:
                        mult[r, c] = 1
                else:
                    mult[r, c] += 1
    return win, True


# ---------------------------------------------------------------------------
# The nudge
# ---------------------------------------------------------------------------


@njit(cache=True)
def nudge(grid, strips, lengths, stops, reelmask):
    """Move every reel flagged in reelmask down one row.

    The bottom symbol leaves the grid and the next strip symbol enters at the
    top. Returns how many scatters entered, so each scatter is counted once.
    """
    new_scatters = 0
    for c in range(REELS):
        if reelmask[c]:
            length = lengths[c]
            stops[c] = (stops[c] - 1 + length) % length
            for r in range(ROWS - 1, 0, -1):
                grid[r, c] = grid[r - 1, c]
            grid[0, c] = strips[c, stops[c]]
            if grid[0, c] == SCATTER:
                new_scatters += 1
    return new_scatters


# ---------------------------------------------------------------------------
# One spin's chain
# ---------------------------------------------------------------------------


@njit(cache=True)
def play_chain(grid, strips, lengths, stops, mult, paytable,
               always_nudge, p_nudge, upgrade_before_pay, cap_left,
               label, csize, csym, cells, stack, winmask, reelmask):
    """Evaluate the grid already on screen and run the nudge chain.

    In the base game (always_nudge False) the chain starts only if a random
    draw below p_nudge succeeds on the spin's first win. In free spins every
    win nudges.

    Returns (win, scatters, nudges, capped). Scatters are counted on the
    landing grid plus every scatter that enters during the chain, each once.
    """
    scatters = count_scatters(grid)
    total = 0.0
    nudges = 0
    nudging = always_nudge
    first = True
    while True:
        win, any_win = evaluate(grid, mult, paytable, upgrade_before_pay,
                                label, csize, csym, cells, stack, winmask, reelmask)
        if not any_win:
            break
        total += win
        if total >= cap_left:
            return cap_left, scatters, nudges, True
        if first:
            first = False
            if not always_nudge:
                nudging = np.random.random() < p_nudge
        if not nudging:
            break
        scatters += nudge(grid, strips, lengths, stops, reelmask)
        nudges += 1
        if nudges >= MAX_CHAIN:
            break
    return total, scatters, nudges, False


# ---------------------------------------------------------------------------
# Base spin and free-spins round
# ---------------------------------------------------------------------------


@njit(cache=True)
def base_spin(strips, lengths, paytable, p_nudge, upgrade_before_pay, cap,
              grid, mult, stops, label, csize, csym, cells, stack, winmask, reelmask):
    random_stops(lengths, stops)
    fill_grid(strips, lengths, stops, grid)
    clear_mult(mult)
    result = play_chain(grid, strips, lengths, stops, mult, paytable,
                        False, p_nudge, upgrade_before_pay, cap,
                        label, csize, csym, cells, stack, winmask, reelmask)
    clear_mult(mult)  # base-game marks never outlive the spin
    return result


@njit(cache=True)
def preheat(mult, n_cells, values, cum_weights):
    """Super buy: mark n_cells distinct random cells before the first spin."""
    order = np.arange(NCELL)
    for i in range(n_cells):
        j = i + np.random.randint(0, NCELL - i)
        tmp = order[i]
        order[i] = order[j]
        order[j] = tmp
        u = np.random.random() * cum_weights[-1]
        v = values[np.searchsorted(cum_weights, u, side="right")]
        r = order[i] // REELS
        c = order[i] - r * REELS
        mult[r, c] = v


@njit(cache=True)
def play_bonus(n_start, strips, lengths, paytable, upgrade_before_pay, cap_left,
               retrigger_spins, grid, mult, stops, label, csize, csym, cells,
               stack, winmask, reelmask):
    """Play a free-spins round. mult must already be set (zero or preheated).

    Every win nudges and every mark persists for the whole round. 3+ scatters
    in one free spin (counted across its chain) add retrigger_spins.

    Returns (win, spins_played, retriggers, capped).
    """
    left = n_start
    total = 0.0
    played = 0
    retriggers = 0
    capped = False
    while left > 0:
        left -= 1
        played += 1
        random_stops(lengths, stops)
        fill_grid(strips, lengths, stops, grid)
        win, scatters, nudges, hit_cap = play_chain(
            grid, strips, lengths, stops, mult, paytable,
            True, 1.0, upgrade_before_pay, cap_left - total,
            label, csize, csym, cells, stack, winmask, reelmask)
        total += win
        if hit_cap:
            total = cap_left
            capped = True
            break
        if scatters >= 3:
            left += retrigger_spins
            retriggers += 1
        if played >= MAX_FREE_SPINS:
            break
    return total, played, retriggers, capped

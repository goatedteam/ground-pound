"""Rule tests on hand-built grids.

Each test builds a 6x6 screen directly, plus the symbols that will enter at
the top of each reel when it nudges, and checks the engine against values
worked out by hand.
"""

import numpy as np
import pytest

from nudgemath import engine as E
from nudgemath import sim
from nudgemath.config import REFERENCE_PAYTABLE, award_array, paytable_array
from nudgemath.strips import SCATTER, check_scatter_gap, make_strip

PT = paytable_array({"paytable": REFERENCE_PAYTABLE})
STRIP_LEN = 12
LOW1, LOW2, HIGH1, HIGH2, HIGH3, HIGH4 = 0, 1, 4, 5, 6, 7


def filler():
    """A screen with no two orthogonal neighbours alike, so no clusters."""
    g = np.zeros((6, 6), dtype=np.int8)
    for r in range(6):
        for c in range(6):
            g[r, c] = (r + 2 * c) % 4
    return g


def rig(grid, incoming=None):
    """Strips that show `grid` at stop 0.

    incoming[c] lists the symbols that enter reel c on its 1st, 2nd, ...
    nudge (strip positions L-1, L-2, ...).
    """
    strips = np.zeros((6, STRIP_LEN), dtype=np.int8)
    for c in range(6):
        strips[c, :6] = grid[:, c]
        strips[c, 6:] = (np.arange(6) + c) % 4  # unused filler
        for i, s in enumerate((incoming or {}).get(c, [])):
            strips[c, STRIP_LEN - 1 - i] = s
    lengths = np.full(6, STRIP_LEN, dtype=np.int64)
    stops = np.zeros(6, dtype=np.int64)
    work = E.new_work()
    g, mult = work[0], work[1]
    E.fill_grid(strips, lengths, stops, g)
    return strips, lengths, stops, g, mult, work[3:]


def chain(strips, lengths, stops, grid, mult, bufs, *, always=True, p=1.0,
          upgrade_before_pay=False, cap=5000.0):
    return E.play_chain(grid, strips, lengths, stops, mult, PT, always, p,
                        upgrade_before_pay, cap, *bufs)


def eval_once(grid):
    work = E.new_work()
    return E.evaluate(grid, work[1], PT, False, *work[3:])


# --- cluster detection ----------------------------------------------------


def test_l_shaped_cluster_pays_and_diagonals_do_not_join():
    g = filler()
    for r, c in [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]:
        g[r, c] = HIGH3
    g[3, 3] = HIGH3  # touches (2, 2) only diagonally
    win, any_win = eval_once(g)
    assert any_win and win == pytest.approx(0.75)


def test_four_is_not_a_win():
    g = filler()
    for r, c in [(0, 0), (1, 0), (2, 0), (2, 1)]:
        g[r, c] = HIGH3
    assert eval_once(g) == (0.0, False)


def test_scatter_breaks_a_cluster():
    g = filler()
    g[5, :] = [HIGH4, HIGH4, HIGH4, SCATTER, HIGH4, HIGH4]
    g[4, 0] = HIGH4
    g[4, 4] = HIGH4
    assert eval_once(g) == (0.0, False)


def test_fifteen_plus_uses_top_column():
    g = filler()
    g[:3, :] = LOW1  # 18 cells
    win, _ = eval_once(g)
    assert win == pytest.approx(10.0)


def test_two_clusters_pay_separately():
    g = filler()
    g[0, :5] = HIGH4      # 5 x high4 = 1.00
    g[5, 1:6] = LOW2      # 5 x low2  = 0.15
    g[5, 0] = HIGH1       # keeps the low2 cluster at exactly 5
    win, _ = eval_once(g)
    assert win == pytest.approx(1.15)


# --- nudge geometry --------------------------------------------------------


def test_nudge_moves_only_flagged_reels_down_one_row():
    g = filler()
    strips, lengths, stops, grid, mult, bufs = rig(g, {2: [HIGH2]})
    before = grid.copy()
    mask = np.zeros(6, dtype=np.bool_)
    mask[2] = True
    E.nudge(grid, strips, lengths, stops, mask)
    assert stops[2] == STRIP_LEN - 1 and stops[0] == 0
    assert grid[0, 2] == HIGH2
    assert (grid[1:, 2] == before[:5, 2]).all()
    assert (np.delete(grid, 2, axis=1) == np.delete(before, 2, axis=1)).all()


# --- the worked example: five stacked high3 symbols on reel 3 --------------


def stacked_example():
    g = filler()
    g[0:5, 2] = HIGH3
    return rig(g, {2: [HIGH2, HIGH1]})


def test_reading_b_worked_example():
    strips, lengths, stops, grid, mult, bufs = stacked_example()
    win, scatters, nudges, capped = chain(strips, lengths, stops, grid, mult, bufs)
    # 0.75 on the landing grid, then 0.75 x (four repeat cells at x1) = 3.00
    assert win == pytest.approx(3.75)
    assert nudges == 2 and not capped
    assert mult[:, 2].tolist() == [1, 2, 2, 2, 2, 1]
    assert mult[:, [0, 1, 3, 4, 5]].sum() == 0


def test_reading_a_for_comparison():
    strips, lengths, stops, grid, mult, bufs = stacked_example()
    win, *_ = chain(strips, lengths, stops, grid, mult, bufs, upgrade_before_pay=True)
    # repeat cells upgraded to x2 before the re-pay: 0.75 + 0.75 x 8
    assert win == pytest.approx(6.75)
    assert mult[:, 2].tolist() == [1, 2, 2, 2, 2, 1]


def test_fresh_mark_does_not_boost_the_win_that_made_it():
    strips, lengths, stops, grid, mult, bufs = stacked_example()
    win, _, _, _ = chain(strips, lengths, stops, grid, mult, bufs, always=False, p=0.0)
    assert win == pytest.approx(0.75)


def test_base_game_without_trigger_does_not_nudge():
    strips, lengths, stops, grid, mult, bufs = stacked_example()
    _, _, nudges, _ = chain(strips, lengths, stops, grid, mult, bufs, always=False, p=0.0)
    assert nudges == 0


def test_persisting_marks_multiply_the_next_free_spin():
    # Marks left on reel 3 from the example above boost a fresh landing.
    strips, lengths, stops, grid, mult, bufs = stacked_example()
    chain(strips, lengths, stops, grid, mult, bufs)
    strips, lengths, stops, grid, _, bufs = stacked_example()
    win, *_ = chain(strips, lengths, stops, grid, mult, bufs)
    # landing pays 0.75 x (1+2+2+2+2) = 6.75, the nudge pays 0.75 x (3+3+3+3+1)
    assert win == pytest.approx(6.75 + 9.75)


# --- scatters --------------------------------------------------------------


def test_each_scatter_is_counted_once_across_a_chain():
    g = filler()
    g[0:5, 0] = HIGH3
    g[5, 0] = SCATTER   # will slide off the bottom on the first nudge
    g[0, 4] = SCATTER   # stays put all chain
    strips, lengths, stops, grid, mult, bufs = rig(g, {0: [HIGH2, SCATTER]})
    _, scatters, nudges, _ = chain(strips, lengths, stops, grid, mult, bufs)
    assert nudges == 2
    assert scatters == 3  # two on landing + one that entered


def test_free_spin_awards():
    award = award_array({"rules": {"free_spins_award": {"3": 10, "4": 12, "5": 15, "6": 20}}})
    assert award[:8].tolist() == [0, 0, 0, 10, 12, 15, 20, 20]


def test_generated_strips_never_show_two_scatters():
    for seed in range(50):
        strip = make_strip(150, [8, 7, 6, 5, 4, 3, 2, 1], 2.0, 6, 3, seed)
        check_scatter_gap(strip)
        n = len(strip)
        for top in range(n):
            window = [strip[(top + r) % n] for r in range(6)]
            assert window.count(SCATTER) <= 1


# --- the cap ---------------------------------------------------------------


def test_chain_stops_at_the_cap():
    strips, lengths, stops, grid, mult, bufs = stacked_example()
    win, _, _, capped = chain(strips, lengths, stops, grid, mult, bufs, cap=2.0)
    assert capped and win == 2.0


def test_bonus_round_ends_exactly_at_5000x():
    strips = np.zeros((6, 12), dtype=np.int8)  # every cell low1: 36-cluster
    lengths = np.full(6, 12, dtype=np.int64)
    work = E.new_work()
    grid, mult, stops = work[0], work[1], work[2]
    mult[:, :] = 1000
    win, played, retriggers, capped = E.play_bonus(
        10, strips, lengths, PT, False, 5000.0, 10, grid, mult, stops, *work[3:])
    assert capped and win == 5000.0 and played == 1


# --- simulator plumbing ----------------------------------------------------


def test_simulation_is_reproducible():
    strips = np.zeros((6, 40), dtype=np.int8)
    for c in range(6):
        strips[c] = make_strip(40, [8, 7, 6, 5, 4, 3, 2, 1], 2.0, 5, 0, c)
    lengths = np.full(6, 40, dtype=np.int64)
    a = sim.sim_base_kernel(2000, 7, strips, lengths, PT, 0.3, False, 5000.0)
    b = sim.sim_base_kernel(2000, 7, strips, lengths, PT, 0.3, False, 5000.0)
    assert (a[0] == b[0]).all()


# --- the trace tool shows exactly what the engine pays ----------------------


def test_trace_matches_engine_on_random_bonus_spins():
    from nudgemath.trace import trace_chain
    rng = np.random.default_rng(5)
    strips = np.zeros((6, 60), dtype=np.int8)
    for c in range(6):
        strips[c] = make_strip(58, [8, 7, 6, 5, 4, 3, 2, 1], 1.6, 5, 2, 100 + c)
    lengths = np.full(6, 60, dtype=np.int64)
    m_engine = np.zeros((6, 6), dtype=np.int32)
    m_trace = np.zeros((6, 6), dtype=np.int32)
    for _ in range(300):
        stops = rng.integers(0, 60, size=6).astype(np.int64)
        work = E.new_work()
        g1 = work[0]
        E.fill_grid(strips, lengths, stops.copy(), g1)
        g2 = g1.copy()
        a = E.play_chain(g1, strips, lengths, stops.copy(), m_engine, PT, True, 1.0,
                         False, 1e9, *work[3:])
        b = trace_chain(g2, strips, lengths, stops.copy(), m_trace, PT, True, True,
                        False, 1e9)
        assert a[0] == pytest.approx(b[0]) and a[1] == b[1]
    assert (m_engine == m_trace).all()


# --- round records replay exactly through the engine -------------------------


def _replay_spin(g, spin, mult, cap):
    strips, lengths = ((g.base_strips, g.base_lengths) if spin["reel_set"] == "base"
                       else (g.bonus_strips, g.bonus_lengths))
    work = E.new_work()
    grid, stops = work[0], np.array(spin["stops"], dtype=np.int64)
    E.fill_grid(strips, lengths, stops, grid)
    always = spin["nudge_roll"] is None
    p = 1.0 if always or spin["nudge_roll"] else 0.0
    return E.play_chain(grid, strips, lengths, stops, mult, g.paytable, always, p,
                        g.upgrade_before_pay, cap, *work[3:])


def test_round_records_replay_through_the_engine():
    import json
    import os
    from nudgemath.build import make_config
    from nudgemath.config import game
    from nudgemath.rounds import base_round, buy_round
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, "tuned_params.json")) as f:
        params = json.load(f)
    params.pop("targets", None)
    g = game(make_config(params), "96")
    rng = np.random.default_rng(9)
    rounds = [base_round(g, rng) for _ in range(400)]
    rounds += [buy_round(g, rng, "standard", 119) for _ in range(5)]
    rounds += [buy_round(g, rng, "super", 505) for _ in range(5)]
    for rec in rounds:
        total = 0.0
        if rec["base_spin"]:
            mult = np.zeros((6, 6), dtype=np.int32)
            win, sc, _, _ = _replay_spin(g, rec["base_spin"], mult, g.cap)
            assert win == pytest.approx(rec["base_spin"]["win"])
            assert sc == rec["base_spin"]["scatters"]
            total += win
        fs = rec["free_spins"]
        if fs:
            mult = np.array(fs["start_marks"], dtype=np.int32)
            for spin in fs["spins"]:
                win, sc, _, _ = _replay_spin(g, spin, mult, g.cap - total)
                assert win == pytest.approx(spin["win"]) and sc == spin["scatters"]
                assert mult.tolist() == spin["steps"][-1]["marks_after"]
                total += win
        assert min(total, g.cap) == pytest.approx(rec["win"])

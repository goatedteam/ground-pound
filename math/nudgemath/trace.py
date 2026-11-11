"""Step-by-step trace of one spin, for checking rules by eye.

Uses the engine's own find_clusters / evaluate / nudge, so the totals shown
are exactly what the simulator pays.
"""

import numpy as np

from . import engine as E

LETTERS = "abcdEFGH*"  # low1-low4 = a-d, high1-high4 = E-H, scatter = *


def show(grid, mult):
    lines = []
    for r in range(6):
        syms = " ".join(LETTERS[grid[r, c]] for c in range(6))
        marks = " ".join(f"{mult[r, c]:>2}" if mult[r, c] else " ." for c in range(6))
        lines.append(f"    {syms}     {marks}")
    return "\n".join(lines)


def trace_chain(grid, strips, lengths, stops, mult, paytable, always_nudge,
                nudge_roll, upgrade_before_pay=False, cap_left=5000.0):
    """Returns (total, scatters, text). nudge_roll: True/False for base spins."""
    w = E.new_work()
    label, csize, csym, cells, stack, winmask, reelmask = w[3:]
    out = ["    symbols         marks"]
    scatters = E.count_scatters(grid)
    total = 0.0
    step = 0
    nudging = always_nudge
    while True:
        step += 1
        out.append(f"  step {step}")
        out.append(show(grid, mult))
        n = E.find_clusters(grid, label, csize, csym, cells, stack)
        pays = []
        for k in range(n):
            if csize[k] < E.MIN_CLUSTER:
                continue
            idx = cells[k, :csize[k]]
            m = int(sum(mult[i // 6, i % 6] for i in idx))
            base_pay = paytable[csym[k], min(csize[k], 15)]
            pays.append((csym[k], csize[k], base_pay, m))
        win, any_win = E.evaluate(grid, mult, paytable, upgrade_before_pay,
                                  label, csize, csym, cells, stack, winmask, reelmask)
        if not any_win:
            out.append("    no win")
            break
        for s, size, bp, m in pays:
            factor = f" x {m} (marks)" if m > 1 else ""
            out.append(f"    {size} x {LETTERS[s]}: {bp:.2f}{factor}")
        out.append(f"    pays {win:.2f}")
        total += win
        if total >= cap_left:
            out.append(f"    5,000x cap reached")
            return cap_left, scatters, "\n".join(out)
        if step == 1 and not always_nudge:
            nudging = nudge_roll
            out.append(f"    nudge triggered: {'yes' if nudging else 'no'}")
        if not nudging:
            break
        moved = [c + 1 for c in range(6) if reelmask[c]]
        new = E.nudge(grid, strips, lengths, stops, reelmask)
        scatters += new
        out.append(f"    nudge reels {moved}" + (f", {new} new scatter" if new else ""))
    out.append(f"  total {total:.2f}, scatters {scatters}")
    return total, scatters, "\n".join(out)

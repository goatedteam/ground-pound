// Pure function: round record -> ordered list of presentation events.
// It reads the record and never computes an outcome. All wins are integer hundredths of stake.
import type { Cluster, Grid, Round, Spin } from './types';
import { hundredths } from './money';

export const SCATTER = 8;
export type Ev =
  | { t: 'fs_intro'; awarded: number; startMarks: Grid; bought: boolean; preheated: boolean }
  | { t: 'spin_start'; kind: 'base' | 'free'; index: number; spinsLeft: number | null; marks: Grid }
  | { t: 'land'; grid: Grid; scatters: number }
  | { t: 'eval'; step: number; clusters: Cluster[]; stepWin: number; spinWin: number; roundWin: number; marksAfter: Grid; capped: boolean }
  | { t: 'slide'; hit: number; reels: number[]; entered: number[]; grid: Grid; newScatters: number; scatters: number }
  | { t: 'spin_end'; kind: 'base' | 'free'; spinWin: number; roundWin: number; scatters: number; retrigger: boolean; spinsLeft: number | null; capped: boolean; clearMarks: boolean }
  | { t: 'fs_outro'; win: number; spins: number; capped: boolean }
  | { t: 'round_end'; win: number; capped: boolean };

const countScatters = (g: Grid) => g.reduce((n, row) => n + row.filter(s => s === SCATTER).length, 0);

function spinEvents(spin: Spin, kind: 'base' | 'free', index: number, before: number, startMarks: Grid, out: Ev[]) {
  out.push({ t: 'spin_start', kind, index, spinsLeft: kind === 'free' ? spin.spins_left ?? 0 : null, marks: startMarks });
  let scatters = countScatters(spin.steps[0].grid);
  out.push({ t: 'land', grid: spin.steps[0].grid, scatters });
  const spinTotal = hundredths(spin.win);
  let run = 0;
  spin.steps.forEach((s, i) => {
    if (s.clusters.length) {
      run = Math.min(run + hundredths(s.win), spinTotal); // the record's spin.win already carries the 5,000x cap
      out.push({ t: 'eval', step: i, clusters: s.clusters, stepWin: hundredths(s.win), spinWin: run, roundWin: before + run, marksAfter: s.marks_after, capped: !!s.capped });
    }
    if (s.nudged_reels) {
      scatters += s.new_scatters ?? 0;
      out.push({ t: 'slide', hit: i + 1, reels: s.nudged_reels, entered: s.entered ?? [], grid: spin.steps[i + 1].grid, newScatters: s.new_scatters ?? 0, scatters });
    }
  });
  out.push({ t: 'spin_end', kind, spinWin: spinTotal, roundWin: before + spinTotal, scatters: spin.scatters, retrigger: !!spin.retrigger,
    spinsLeft: kind === 'free' ? spin.spins_left ?? 0 : null, capped: spin.capped, clearMarks: kind === 'base' });
  return spinTotal;
}

export function buildTimeline(round: Round): Ev[] {
  const out: Ev[] = [];
  const zero: Grid = Array.from({ length: 6 }, () => Array(6).fill(0));
  let total = 0;
  if (round.base_spin) total += spinEvents(round.base_spin, 'base', 0, 0, zero, out);
  const fs = round.free_spins;
  if (fs) {
    const preheated = fs.start_marks.some(r => r.some(v => v > 0));
    out.push({ t: 'fs_intro', awarded: fs.awarded, startMarks: fs.start_marks, bought: !round.base_spin, preheated });
    let marks = fs.start_marks;
    const base = total;
    let fsRun = 0;
    fs.spins.forEach((sp, i) => {
      fsRun += spinEvents(sp, 'free', i, base + fsRun, marks, out);
      marks = sp.steps[sp.steps.length - 1].marks_after;
    });
    out.push({ t: 'fs_outro', win: hundredths(fs.win), spins: fs.spins.length, capped: fs.capped });
  }
  out.push({ t: 'round_end', win: hundredths(round.win), capped: round.capped });
  return out;
}

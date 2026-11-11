import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { buildTimeline } from '../src/timeline';
import { hundredths } from '../src/money';
import type { Round } from '../src/types';

const load = (name: string): Round[] => JSON.parse(readFileSync(resolve(__dirname, '../../../math/golden', `${name}.json`), 'utf8')).rounds;

for (const name of ['base', 'free_spins', 'buys']) {
  describe(`golden ${name}`, () => {
    const rounds = load(name);
    it('final timeline win equals the record win for every round', () => {
      for (const r of rounds) {
        const tl = buildTimeline(r);
        const end = tl[tl.length - 1];
        expect(end.t).toBe('round_end');
        if (end.t === 'round_end') expect(end.win).toBe(hundredths(r.win));
        const lastSpinEnd = [...tl].reverse().find(e => e.t === 'spin_end');
        if (lastSpinEnd && lastSpinEnd.t === 'spin_end') expect(lastSpinEnd.roundWin).toBe(hundredths(r.win));
      }
    });
    it('marks shown after each evaluation equal marks_after, and running wins never exceed the cap', () => {
      for (const r of rounds) {
        const spins = [...(r.base_spin ? [r.base_spin] : []), ...(r.free_spins?.spins ?? [])];
        const evals = buildTimeline(r).filter(e => e.t === 'eval');
        const steps = spins.flatMap(s => s.steps.filter(st => st.clusters.length));
        expect(evals.length).toBe(steps.length);
        evals.forEach((e, i) => {
          if (e.t !== 'eval') return;
          expect(e.marksAfter).toEqual(steps[i].marks_after);
          expect(e.roundWin).toBeLessThanOrEqual(500000);
        });
      }
    });
    it('each free spin starts from the marks the previous one ended on', () => {
      for (const r of rounds) {
        if (!r.free_spins) continue;
        const starts = buildTimeline(r).filter(e => e.t === 'spin_start' && e.kind === 'free');
        starts.forEach((e, i) => { if (e.t === 'spin_start') expect(e.marks).toEqual(r.free_spins!.spins[i].steps[0].marks_before); });
      }
    });
  });
}

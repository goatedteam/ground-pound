// Soak: every pre-drawn demo round (6,250 engine rounds) must build a timeline whose totals match the record.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { buildTimeline } from '../src/timeline';
import { hundredths } from '../src/money';
import type { Round } from '../src/types';

describe('demo library soak', () => {
  const lib = JSON.parse(readFileSync(resolve(__dirname, '../public/demo-rounds.json'), 'utf8'));
  const rounds: Round[] = [...lib.base, ...lib.buy_standard, ...lib.buy_super];
  it('builds every timeline with matching totals and consistent slides', () => {
    expect(rounds.length).toBeGreaterThan(6000);
    for (const r of rounds) {
      const tl = buildTimeline(r);
      const end = tl[tl.length - 1];
      expect(end.t === 'round_end' && end.win).toBe(hundredths(r.win));
      for (const e of tl) if (e.t === 'slide') { expect(e.reels.length).toBe(e.entered.length); e.reels.forEach((c, k) => expect(e.grid[0][c]).toBe(e.entered[k])); }
    }
  });
});

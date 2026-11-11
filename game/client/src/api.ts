// Two backends with one interface. Outcomes always come from the maths engine:
//  - ServerBackend asks the game server (game/server), which runs the engine per bet.
//  - DemoBackend plays records the engine drew ahead of time (static demo, no server).
import type { GameConfig, PlayResult, Round } from './types';
import { hundredths, toMinor } from './money';

export interface Backend {
  readonly demo: boolean;
  config(): Promise<GameConfig>;
  start(): Promise<number>;
  spin(betMinor: number): Promise<PlayResult>;
  buy(betMinor: number, kind: 'standard' | 'super'): Promise<PlayResult>;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Request failed (${res.status})`);
  return res.json();
}

export class ServerBackend implements Backend {
  readonly demo = false;
  private sid = '';
  constructor(private market: string, private variant: string) {}
  config() { return fetch(`api/config?market=${this.market}&variant=${this.variant}`).then(r => json<GameConfig>(r)); }
  async start() {
    const s = await fetch('api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ market: this.market, variant: this.variant }) })
      .then(r => json<{ session_id: string; balance_minor: number }>(r));
    this.sid = s.session_id;
    return s.balance_minor;
  }
  private post(path: string, body: object) {
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: this.sid, ...body }) }).then(r => json<PlayResult>(r));
  }
  spin(betMinor: number) { return this.post('api/spin', { bet_minor: betMinor }); }
  buy(betMinor: number, kind: 'standard' | 'super') { return this.post('api/buy', { bet_minor: betMinor, kind }); }
}

interface Library { base: Round[]; buy_standard: Round[]; buy_super: Round[] }

export class DemoBackend implements Backend {
  readonly demo = true;
  private lib!: Library;
  private cfg!: GameConfig;
  private balance = 1_000_000;
  private staked = 0;
  private won = 0;
  private n = 0;
  async config() {
    const [cfg, lib] = await Promise.all([
      fetch('demo-config.json').then(r => json<GameConfig>(r)),
      fetch('demo-rounds.json').then(r => json<Library>(r)),
    ]);
    this.cfg = cfg; this.lib = lib;
    return cfg;
  }
  async start() { return this.balance; }
  private pick<T>(list: T[]): T {
    const u = new Uint32Array(1); crypto.getRandomValues(u);
    return list[u[0] % list.length];
  }
  private settle(round: Round, betMinor: number): PlayResult {
    const cost = toMinor(hundredths(round.cost), betMinor), win = toMinor(hundredths(round.win), betMinor);
    if (this.balance < cost) throw new Error('Insufficient balance');
    this.balance += win - cost; this.staked += cost; this.won += win;
    return { round_id: `demo${++this.n}`, round, bet_minor: betMinor, cost_minor: cost, win_minor: win, balance_minor: this.balance, net_position_minor: this.won - this.staked };
  }
  async spin(betMinor: number) { return this.settle(this.pick(this.lib.base), betMinor); }
  async buy(betMinor: number, kind: 'standard' | 'super') {
    if (!this.cfg.buys) throw new Error('Bonus buys are not offered in this market');
    return this.settle(this.pick(kind === 'super' ? this.lib.buy_super : this.lib.buy_standard), betMinor);
  }
}

/** Replays a fixed list of records in order (QA): ?replay=golden/base.json */
export class ReplayBackend extends DemoBackend {
  private i = 0;
  constructor(private rounds: Round[]) { super(); }
  private next(betMinor: number) { return (this as any).settle(this.rounds[this.i++ % this.rounds.length], betMinor) as PlayResult; }
  async spin(betMinor: number) { return this.next(betMinor); }
  async buy(betMinor: number) { return this.next(betMinor); }
}

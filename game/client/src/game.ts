// Round controller. Sends bets to the backend, then animates the returned round record
// event by event. It never computes a pay or alters an outcome.
import gsap from 'gsap';
import type { Backend } from './api';
import { audio } from './audio';
import { GridView } from './grid';
import { formatMoney, toMinor } from './money';
import { buildTimeline, type Ev } from './timeline';
import type { Cluster, GameConfig, Grid, PlayResult } from './types';

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const wait = (s: number) => new Promise<void>(r => gsap.delayedCall(s, r));
const ZERO: Grid = Array.from({ length: 6 }, () => Array(6).fill(0));
// Display-only board shown before the first spin. Never paid; holds no cluster and no scatter.
const IDLE: Grid = [[7, 0, 4, 5, 7, 3], [4, 2, 4, 6, 6, 2], [1, 5, 0, 0, 1, 5], [7, 2, 3, 6, 7, 2], [4, 5, 5, 5, 4, 5], [7, 0, 7, 1, 1, 0]];
export const PACE = { evalHold: 0.42, perCluster: 0.5, afterMarks: 0.22, afterSlide: 0.1, endOfSpin: 0.3, betweenFreeSpins: 0.35, tierMs: 2600 };

export class Game {
  private grid = new GridView();
  private cfg!: GameConfig;
  private balance = 0;
  private betIndex = 0;
  private busy = false;
  private fight = false;
  private auto = 0;
  private fast = false;
  private lastStart = 0;
  private sessionStart = Date.now();
  private net = 0;
  private dismiss: (() => void) | null = null;
  private stage = $('stage');
  private gore = 1;
  private sym(i: number) { return `./assets/symbols/${this.gore === 0 ? 'worn' : 'blood'}/${this.cfg.theme.symbols[i].asset}`; }

  constructor(private backend: Backend) {}

  private get bet() { return this.cfg.market.bet_ladder_minor[this.betIndex]; }
  private money(minor: number) { return formatMoney(minor, this.cfg.market.currency); }
  private fromH(h: number) { return this.money(toMinor(h, this.bet)); }

  async init() {
    this.cfg = await this.backend.config();
    this.balance = await this.backend.start();
    const m = this.cfg.market;
    this.betIndex = Math.max(0, m.bet_ladder_minor.indexOf(m.default_bet_minor));
    await document.fonts.ready.catch(() => {});
    await this.grid.init($('grid'), ['worn', 'blood'].map(set => this.cfg.theme.symbols.map(s => `./assets/symbols/${set}/${s.asset}`)));
    const q = new URLSearchParams(location.search).get('gore');
    this.setGore(q !== null && /^[012]$/.test(q) ? Number(q) : m.gore ?? 1);
    this.grid.onReelStop = (_c, scatter) => audio.play(scatter ? 'scatterLand' : 'reelStop');
    this.grid.setGrid(IDLE);
    $('buySign').hidden = !this.cfg.buys;
    $('btnAuto').hidden = !m.autoplay;
    $('notice').textContent = this.backend.demo ? 'Demo: play money, pre-drawn rounds' : 'Play money. RNG not certified';
    this.bind();
    this.refresh();
    this.strip(m.turbo ? 'Hold space for turbo spin' : 'Place your bet', '');
    if (m.show_session_time || m.show_net_position) setInterval(() => this.extras(), 1000);
    this.extras();
    $('loading').hidden = true;
  }

  private bind() {
    $('btnSpin').addEventListener('click', () => (this.busy ? this.speedUp() : this.spin()));
    $('btnMinus').addEventListener('click', () => this.changeBet(-1));
    $('btnPlus').addEventListener('click', () => this.changeBet(1));
    $('buySign').addEventListener('click', () => this.openBuy());
    $('btnInfo').addEventListener('click', () => this.openRules());
    $('btnRules').addEventListener('click', () => this.openRules());
    $('btnAuto').addEventListener('click', () => this.toggleAuto());
    $('btnSound').addEventListener('click', () => {
      audio.setEnabled(!audio.enabled);
      $('btnSound').setAttribute('aria-pressed', String(audio.enabled));
      $('btnSound').setAttribute('aria-label', audio.enabled ? 'Sound on' : 'Sound off');
    });
    $('overlay').addEventListener('click', ev => { if (!(ev.target as HTMLElement).closest('button')) this.dismiss?.(); });
    window.addEventListener('keydown', ev => {
      if (!$('modal').hidden) { if (ev.key === 'Escape') this.closeModal(); return; }
      if (ev.code !== 'Space' || (ev.target as HTMLElement).tagName === 'BUTTON') return;
      ev.preventDefault();
      if (this.dismiss) this.dismiss(); else if (this.busy) this.speedUp(); else if ($('overlay').hidden) this.spin();
    });
    window.addEventListener('keyup', ev => { if (ev.code === 'Space') this.fast = false; });
  }

  // ---------- display helpers ----------
  private refresh() {
    $('credit').textContent = this.money(this.balance);
    $('bet').textContent = this.money(this.bet);
    if (this.cfg.buys) $('buyPrice').textContent = this.money(this.cfg.buys.standard.price * this.bet);
    const idle = !this.busy;
    const ladder = this.cfg.market.bet_ladder_minor;
    ($('btnMinus') as HTMLButtonElement).disabled = !idle || this.betIndex === 0;
    ($('btnPlus') as HTMLButtonElement).disabled = !idle || this.betIndex === ladder.length - 1;
    ($('buySign') as HTMLButtonElement).disabled = !idle;
    $('btnSpin').classList.toggle('busy', this.busy);
    $('btnSpin').setAttribute('aria-label', this.busy ? 'Speed up' : 'Spin');
    ($('btnSpin') as HTMLButtonElement).disabled = this.busy && !this.cfg.market.turbo;
    $('btnAuto').classList.toggle('on', this.auto > 0);
    $('btnAuto').textContent = this.auto > 0 ? `Stop (${this.auto})` : 'Autoplay';
  }
  private extras() {
    const m = this.cfg.market, lines: string[] = [];
    if (m.show_net_position) lines.push(`Net ${this.money(this.net)}`);
    if (m.show_session_time) { const s = Math.floor((Date.now() - this.sessionStart) / 1000); lines.push(`Time ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`); }
    $('extra').innerHTML = lines.map(l => `<span>${l}</span>`).join('');
  }
  private strip(line1: string, line2: string) { $('strip1').innerHTML = line1; $('strip2').innerHTML = line2; }
  private showWin(h: number) { $('strip1').innerHTML = `<b>Win</b> ${this.fromH(h)}`; }
  private belts(n: number, bump = true) {
    $('beltCount').textContent = `${Math.min(n, 9)}/3`;
    const el = document.querySelector('.belt')!;
    el.classList.toggle('lit', n >= 3);
    if (bump && n > 0) { el.classList.remove('bump'); void (el as HTMLElement).offsetWidth; el.classList.add('bump'); audio.play('beltCount'); }
  }
  private toast(text: string, hold = 0.9) {
    const t = $('toast'); t.textContent = text;
    return gsap.timeline().fromTo(t, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.22, ease: 'back.out(2)' }).to(t, { opacity: 0, duration: 0.25 }, `+=${hold}`);
  }
  /** Violence level is presentation only; a market preset sets it. */
  private setGore(level: number) {
    this.gore = level; this.grid.setGore(level);
    this.stage.classList.remove('gore0', 'gore1', 'gore2'); this.stage.classList.add(`gore${level}`);
  }
  private flash() { gsap.fromTo($('flash'), { opacity: 0.55 }, { opacity: 0, duration: 0.3, ease: 'power2.out' }); }
  private changeBet(d: number) {
    if (this.busy) return;
    this.betIndex = Math.min(this.cfg.market.bet_ladder_minor.length - 1, Math.max(0, this.betIndex + d));
    audio.play('click'); this.refresh();
  }
  private speedUp() { if (this.cfg.market.turbo) { this.fast = true; gsap.globalTimeline.timeScale(3); } }
  private setBusy(b: boolean) { this.busy = b; if (!b) { this.fast = false; gsap.globalTimeline.timeScale(1); } this.refresh(); }

  /** Shows a panel over the stage; resolves on click/Space, or after autoMs when given. */
  private panel(html: string, opts: { red?: boolean; autoMs?: number } = {}): Promise<void> {
    const ov = $('overlay');
    ov.className = `overlay${opts.red ? ' red' : ''}`; ov.innerHTML = html; ov.hidden = false;
    gsap.fromTo(ov, { opacity: 0 }, { opacity: 1, duration: 0.2 });
    return new Promise(res => {
      let timer = 0;
      const done = () => { if (!this.dismiss) return; this.dismiss = null; clearTimeout(timer); ov.hidden = true; ov.innerHTML = ''; res(); };
      this.dismiss = done;
      const auto = opts.autoMs ?? (this.auto > 0 ? 2200 : 0);
      if (auto) timer = window.setTimeout(done, auto);
    });
  }

  // ---------- bets ----------
  private async cycleGuard() {
    const gap = this.cfg.market.min_cycle_ms - (performance.now() - this.lastStart);
    if (this.lastStart && gap > 0) await new Promise(r => setTimeout(r, gap));
    this.lastStart = performance.now();
  }

  async spin() {
    if (this.busy || !$('overlay').hidden) return;
    if (this.balance < this.bet) { this.strip('Not enough credit', ''); audio.play('error'); this.auto = 0; this.refresh(); return; }
    this.setBusy(true);
    try {
      await this.cycleGuard();
      this.balance -= this.bet; this.refresh();
      this.strip('Fight!', ''); audio.play('spin');
      const res = await this.backend.spin(this.bet);
      await this.play(res);
    } catch (e) { this.fail(e); }
    this.setBusy(false);
    if (this.auto > 0) { this.auto--; this.refresh(); if (this.auto > 0) setTimeout(() => this.spin(), 250); }
  }

  private fail(e: unknown) {
    console.error(e);
    this.auto = 0;
    this.strip('Something went wrong', String((e as Error)?.message ?? e).slice(0, 60));
    audio.play('error');
  }

  private toggleAuto() {
    if (this.auto > 0) { this.auto = 0; this.refresh(); return; }
    this.auto = 25; this.refresh();
    if (!this.busy) this.spin();
  }

  private openBuy() {
    if (this.busy || !this.cfg.buys) return;
    const b = this.cfg.buys, bet = this.bet;
    const price = (k: 'standard' | 'super') => this.money(b[k].price * bet);
    const ov = $('overlay');
    ov.className = 'overlay';
    ov.innerHTML = `<div class="contract"><img src="./assets/ui/contract_large.webp" alt=""><div class="contract-in">
      <h1 class="d">Buy <span>Title Fight</span></h1>
      <div class="opts">
        <div class="opt"><span class="k">${b.standard.name}</span><span class="d p">${price('standard')}</span><p>Straight to the Title Fight. The canvas starts clean.</p><button class="btn" data-kind="standard">Sign for ${b.standard.name}</button></div>
        <div class="opt"><span class="k">${b.super.name}</span><span class="d p">${price('super')}</span><p>Every cell starts with x5, x10 or x15 Damage.</p><button class="btn red" data-kind="super">Sign for ${b.super.name}</button></div>
      </div>
      <button class="btn ghost" data-kind="cancel">Walk away</button></div></div>`;
    ov.hidden = false;
    let armed = '';
    const close = () => { ov.hidden = true; ov.innerHTML = ''; this.dismiss = null; };
    this.dismiss = close;
    ov.querySelectorAll<HTMLButtonElement>('button').forEach(btn => btn.addEventListener('click', () => {
      const kind = btn.dataset.kind!;
      audio.play('click');
      if (kind === 'cancel') return close();
      const k = kind as 'standard' | 'super';
      if (this.balance < b[k].price * bet) { btn.textContent = 'Not enough credit'; btn.disabled = true; return; }
      if (armed !== kind) { // second tap confirms
        armed = kind;
        ov.querySelectorAll<HTMLButtonElement>('button[data-kind]').forEach(o => { if (o.dataset.kind !== 'cancel') { o.classList.remove('confirm'); o.textContent = `Sign for ${b[o.dataset.kind as 'standard' | 'super'].name}`; } });
        btn.classList.add('confirm'); btn.textContent = `Confirm ${price(k)}`;
        return;
      }
      close(); this.buy(k);
    }));
  }

  private async buy(kind: 'standard' | 'super') {
    this.setBusy(true);
    try {
      await this.cycleGuard();
      const cost = this.cfg.buys![kind].price * this.bet;
      this.balance -= cost; this.refresh();
      this.strip('Fight booked', ''); this.belts(0, false);
      const res = await this.backend.buy(this.bet, kind);
      await this.play(res);
    } catch (e) { this.fail(e); }
    this.setBusy(false);
  }

  // ---------- playing a round record ----------
  private async play(res: PlayResult) {
    const bet = res.bet_minor;
    let spinsLeft = 0;
    for (const ev of buildTimeline(res.round)) {
      if (this.fast && this.cfg.market.turbo) gsap.globalTimeline.timeScale(3);
      switch (ev.t) {
        case 'spin_start':
          this.grid.showMarks(ev.marks);
          if (ev.kind === 'free') { spinsLeft--; this.setSpinsLeft(spinsLeft); this.belts(0, false); audio.play('spin'); }
          else this.belts(0, false);
          break;
        case 'land':
          await this.grid.spinTo(ev.grid);
          if (ev.scatters) this.belts(ev.scatters);
          break;
        case 'eval':
          await this.evaluate(ev);
          break;
        case 'slide':
          audio.play('takedown', { intensity: ev.hit });
          await this.grid.slide(ev.reels, ev.entered, ev.grid);
          this.grid.shake(this.stage, Math.min(2.2, 0.8 + ev.hit * 0.25)); if (ev.hit >= 3) this.flash();
          if (ev.newScatters) this.belts(ev.scatters);
          await wait(PACE.afterSlide);
          break;
        case 'spin_end':
          this.grid.clearHighlight();
          $('strip2').innerHTML = this.fight ? `Spins left ${Math.max(ev.spinsLeft ?? 0, 0)}` : '';
          if (ev.clearMarks) this.grid.showMarks(ZERO);
          if (ev.kind === 'free') {
            if (ev.retrigger) { audio.play('retrigger'); await this.toast(`+${this.cfg.rules.retrigger_spins} spins`); }
            spinsLeft = ev.spinsLeft ?? 0; this.setSpinsLeft(spinsLeft);
            if (!ev.capped && ev.spinWin >= 2500) await this.tier(ev.spinWin, 1700);
            await wait(PACE.betweenFreeSpins);
          } else await wait(ev.spinWin > 0 ? PACE.endOfSpin : 0.05);
          break;
        case 'fs_intro':
          spinsLeft = ev.awarded;
          await this.fightIntro(ev);
          break;
        case 'fs_outro':
          audio.play('outro');
          if (!ev.capped) await this.panel(`<h1 class="d ov-h">Title Fight <span>over</span></h1><span class="d ov-s">You have won</span><div class="d ov-total">${this.fromH(ev.win)}</div><span class="d ov-s">in ${ev.spins} free spins</span><span class="ov-hint">Press anywhere to continue</span>`, { red: true });
          break;
        case 'round_end':
          if (ev.capped) { audio.play('knockout'); await this.panel(`<h1 class="d ov-h big">${this.cfg.theme.cap_name}!</h1><div class="d ov-total">${this.fromH(ev.win)}</div><span class="d ov-s">Lights out. Max win.</span><span class="ov-hint">Press anywhere to continue</span>`, { red: true }); }
          else if (!res.round.free_spins && ev.win >= 1000) await this.tier(ev.win, PACE.tierMs);
          if (this.fight) this.setFight(false);
          this.balance = res.balance_minor; this.net = res.net_position_minor;
          if (ev.win > 0) { this.showWin(ev.win); $('strip2').innerHTML = res.round.free_spins ? 'Title Fight over' : ''; }
          else this.strip(this.cfg.market.turbo ? 'Hold space for turbo spin' : 'Place your bet', '');
          void bet;
          break;
      }
    }
  }

  private async evaluate(ev: Extract<Ev, { t: 'eval' }>) {
    audio.play('clusterWin', { intensity: ev.clusters.length });
    if (ev.capped) gsap.globalTimeline.timeScale(0.35); // the finishing blow lands in slow motion
    if (ev.stepWin >= 500) this.flash();
    const pulse = this.grid.highlight(ev.clusters);
    const big = ev.stepWin > 100; // more than the stake: allowed a little more show
    for (const cl of ev.clusters) {
      this.popup(cl);
      $('strip2').innerHTML = `<img src="${this.sym(cl.symbol)}" alt="${this.cfg.theme.symbols[cl.symbol].name}"><span>x${cl.size} pays ${this.fromH(Math.round(cl.pay * 100))}</span>`;
      await wait(ev.clusters.length > 1 ? PACE.perCluster : PACE.evalHold + (big ? 0.15 : 0));
    }
    await pulse;
    if (ev.capped) gsap.globalTimeline.timeScale(1);
    gsap.to($('popup'), { opacity: 0, duration: 0.15 });
    this.showWin(ev.roundWin);
    this.grid.showMarks(ev.marksAfter, true); audio.play('damage');
    await wait(PACE.afterMarks);
  }

  private popup(cl: Cluster) {
    const { x, y } = this.grid.cellCentre(cl.cells), p = $('popup');
    p.innerHTML = cl.multiplier > 1 ? `${this.fromH(Math.round(cl.base_pay * 100))} <b>x${cl.multiplier}</b>` : this.fromH(Math.round(cl.pay * 100));
    p.style.left = `${Math.min(560, Math.max(100, x))}px`; p.style.top = `${y}px`;
    gsap.fromTo(p, { opacity: 0, scale: 0.7 }, { opacity: 1, scale: 1, duration: 0.16, ease: 'back.out(2)' });
  }

  private setSpinsLeft(n: number) {
    $('spinsLabel').textContent = n === 0 ? 'Final' : 'Spins left';
    $('spinsLeft').textContent = n === 0 ? 'spin' : String(n);
    $('spinsLeft').style.fontSize = n === 0 ? '44px' : '';
  }

  private setFight(on: boolean) {
    this.fight = on;
    this.stage.classList.toggle('fight', on);
    $('buySign').hidden = on || !this.cfg.buys;
    $('spinsSign').hidden = !on;
    $('beltCap').textContent = on ? `3 belts in one spin add ${this.cfg.rules.retrigger_spins} spins` : 'Land 3 belts to start the Title Fight';
    if (!on) { this.grid.showMarks(ZERO); this.belts(0, false); }
    audio.music(on ? 'fight' : 'base');
  }

  private async fightIntro(ev: Extract<Ev, { t: 'fs_intro' }>) {
    if (!ev.bought) await wait(0.7);
    audio.play('fightIntro');
    await this.panel(`<h1 class="d ov-h">It's a <span>Title Fight</span></h1><span class="d ov-s">You have won</span><div class="ov-card"><img src="./assets/ui/roundcard.webp" alt=""><div class="d">${ev.awarded}</div></div><span class="d ov-s">Free spins</span><span class="ov-hint">Press anywhere to continue</span>`, { red: true });
    this.setFight(true);
    this.setSpinsLeft(ev.awarded);
    $('strip2').innerHTML = `Spins left ${ev.awarded}`;
    this.grid.clearHighlight();
    if (ev.preheated) { this.grid.showMarks(ev.startMarks, true); audio.play('damage'); await this.toast(this.cfg.buys?.super.name ?? 'Grudge Match', 1.0); }
    else this.grid.showMarks(ev.startMarks);
    await wait(0.35);
  }

  private async tier(h: number, ms: number) {
    const x = h / 100;
    const tiers = this.cfg.theme.win_tiers;
    let name = '';
    for (const t of tiers) if (x >= t.min) name = t.name;
    if (!name) return;
    audio.play('tier', { intensity: tiers.findIndex(t => t.name === name) + 1 });
    const p = this.panel(`<h1 class="d ov-h big">${name}!</h1><div class="ov-plate"><img src="./assets/ui/plate.webp" alt=""><div class="d" id="tierAmt"></div></div>`, { red: true, autoMs: ms });
    const o = { v: 0 }, el = document.getElementById('tierAmt')!;
    gsap.to(o, { v: h, duration: Math.min(1.6, ms / 1600), ease: 'power1.out', onUpdate: () => { el.textContent = this.fromH(Math.round(o.v / 5) * 5); } });
    await p;
  }

  // ---------- rules and paytable, generated from the config ----------
  private closeModal() { $('modal').hidden = true; $('modal').innerHTML = ''; }
  private openRules() {
    const c = this.cfg, t = c.theme, sizes = Object.keys(c.paytable);
    const head = t.symbols.slice(0, 8).map(s => `<th><img src="${this.sym(s.id)}" alt="${s.name}"></th>`).join('');
    const rows = sizes.map(k => `<tr><td>${k}</td>${c.paytable[k].map(v => `<td>${this.money(Math.round(v * 100) * this.bet / 100)}</td>`).join('')}</tr>`).join('');
    const award = Object.entries(c.rules.free_spins_award).map(([n, s]) => `${n === '6' ? '6 or more' : n} belts: ${s} spins`).join(' · ');
    const buys = c.buys ? `<h3 class="d">Buying the Title Fight</h3><ul>
      <li><b>${c.buys.standard.name}</b> costs ${c.buys.standard.price}x your bet and starts the Title Fight with 10, 12 or 15 spins.</li>
      <li><b>${c.buys.super.name}</b> costs ${c.buys.super.price}x your bet. It is the same, and every cell starts with x5, x10 or x15 Damage.</li>
      <li>A buy has no base spin. You confirm the price before it is charged.</li></ul>` : '';
    $('modal').innerHTML = `<div class="sheet" role="dialog" aria-label="Rules and paytable">
      <button class="btn close" id="closeModal">Close</button>
      <h2 class="d">${t.name}</h2>
      <p>${c.notice}</p>
      <h3 class="d">Violence level (preview setting)</h3>
      <div class="seg">${t.gore_levels.map((n, i) => `<button class="btn${i === this.gore ? ' confirm' : ''}" data-gore="${i}">${n}</button>`).join('')}</div>
      <p>Menacing has no blood. Bloodied adds blood to the gear and the canvas. Brutal adds blood spray on hits. Each market is set to one level.</p>
      <h3 class="d">Paytable at your current bet (${this.money(this.bet)})</h3>
      <div class="scroll-x"><table><thead><tr><th>Cluster</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>
      <p>A cluster is ${c.rules.min_cluster} or more of the same symbol joined side to side or up and down, not diagonally. Clusters of 15 or more pay the 15+ value. Several clusters can pay at once.</p>
      <h3 class="d">Takedown and Ground &amp; Pound</h3><ul>
        <li>When a spin wins, every reel that holds a winning symbol can slide down one row. The bottom symbol leaves and a new one enters at the top. Reels with no winning symbol stay still.</li>
        <li>The grid then pays again, and this repeats until a slide brings no win.</li>
        <li>In the base game, one random roll on the spin's first win decides whether the chain runs. The chance is fixed at ${(c.base_nudge_probability * 100).toFixed(1)}% and never changes with your results. In the Title Fight every win slides.</li></ul>
      <h3 class="d">Damage</h3><ul>
        <li>Damage belongs to grid cells. It does not move when the reels slide.</li>
        <li>A cluster's pay is multiplied by the total Damage under its cells as it stood before that pay. If the total is zero, the multiplier is 1.</li>
        <li>After the pay, every cell of every winning cluster gains +1 Damage. Damage never boosts the win that created it.</li>
        <li>In the base game Damage is cleared when the spin ends. In the Title Fight it stays for the whole round.</li></ul>
      <h3 class="d">Title Fight</h3><ul>
        <li>The star belt is the scatter. It pays nothing itself. Belts are counted on the landing grid plus every belt that enters during the chain; each counts once, even after it slides off.</li>
        <li>${award}.</li>
        <li>Three or more belts in one free spin add ${c.rules.retrigger_spins} spins, with no limit.</li></ul>
      ${buys}
      <h3 class="d">Maximum win</h3>
      <p>A round is capped at ${c.rules.max_win.toLocaleString('en-US')}x your bet. Reaching it is a ${t.cap_name}: the round pays exactly that amount and ends at once, and any remaining free spins are not played.</p>
      <h3 class="d">Return to player</h3>
      <p>This version is tuned to about ${c.rtp_target} return to player. Malfunction voids all pays and plays.</p></div>`;
    $('modal').hidden = false;
    $('closeModal').addEventListener('click', () => this.closeModal());
    $('modal').querySelectorAll<HTMLButtonElement>('[data-gore]').forEach(b => b.addEventListener('click', () => { this.setGore(Number(b.dataset.gore)); this.openRules(); }));
    $('modal').addEventListener('click', ev => { if (ev.target === $('modal')) this.closeModal(); }, { once: true });
  }
}

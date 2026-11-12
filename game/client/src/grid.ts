// Reel grid view. PixiJS draws the symbols (spin, slide, dim, pulse); two DOM layers hold what
// belongs to cells and never moves: the Damage tiles under the symbols and the badges and
// win outlines over them. It animates what it is given and decides nothing.
import 'pixi.js/unsafe-eval'; // no eval-based codegen, so the game runs under strict content-security policies
import { Application, Assets, Container, Graphics, Sprite, Texture } from 'pixi.js';
import gsap from 'gsap';
import type { Cluster, Grid } from './types';
import { SCATTER } from './timeline';

export const COLS = 6, ROWS = 6, W = 662, H = 484, CW = W / COLS, CH = H / ROWS;
export const TIMING = { dropOut: 0.2, dropIn: 0.34, reelStagger: 0.075, anticipation: 0.55, slide: 0.24, pulse: 0.34 };

const tierOf = (n: number) => (n >= 20 ? 5 : n >= 8 ? 4 : n >= 5 ? 3 : n >= 2 ? 2 : 1);

export class GridView {
  private app = new Application();
  private tex: Texture[][] = [[], []]; // [battle-worn, bloodied]
  private set = 0;
  private gore = 0;
  private fx = new Container();
  private cols: Container[] = [];
  private sprites: Sprite[][] = [];
  private tiles: HTMLElement[] = [];
  private cells: HTMLElement[] = [];
  private badges: HTMLElement[] = [];
  private marks: number[] = Array(36).fill(0);
  onReelStop: (col: number, scatter: boolean) => void = () => {};
  onAnticipation: () => void = () => {};

  async init(host: HTMLElement, sets: string[][]) {
    const tileLayer = document.createElement('div'); tileLayer.className = 'g-layer g-tiles';
    const cellLayer = document.createElement('div'); cellLayer.className = 'g-layer g-cells';
    for (let i = 0; i < 36; i++) {
      const t = document.createElement('div'); t.className = 'g-tile'; tileLayer.appendChild(t); this.tiles.push(t);
      const c = document.createElement('div'); c.className = 'g-cell';
      const b = document.createElement('span'); b.className = 'g-badge'; c.appendChild(b);
      cellLayer.appendChild(c); this.cells.push(c); this.badges.push(b);
    }
    Assets.setPreferences({ preferWorkers: false });
    await this.app.init({ width: W, height: H, backgroundAlpha: 0, antialias: true, resolution: 2, autoDensity: true });
    this.app.canvas.className = 'g-canvas';
    host.append(tileLayer, this.app.canvas, cellLayer);
    this.tex = await Promise.all(sets.map(set => Promise.all(set.map(a => Assets.load<Texture>(a)))));
    const root = new Container();
    const mask = new Graphics().rect(0, 0, W, H).fill(0xffffff);
    root.mask = mask;
    this.app.stage.addChild(root, mask);
    for (let c = 0; c < COLS; c++) {
      const col = new Container(); col.x = c * CW; root.addChild(col);
      this.cols.push(col); this.sprites.push([]);
    }
    root.addChild(this.fx);
  }

  /** 0 = no blood, 1 = bloodied gear and stained canvas, 2 = adds blood spray on hits. Visual only. */
  setGore(level: number) {
    this.gore = level; this.set = level === 0 ? 0 : 1;
    this.sprites.forEach(col => col.forEach(s => this.skin(s, (s as any).sym)));
  }

  private skin(s: Sprite, sym: number) {
    s.texture = this.tex[this.set][sym];
    const [mw, mh] = sym === SCATTER ? [106, 76] : [98, 72];
    const k = Math.min(mw / s.texture.width, mh / s.texture.height);
    s.scale.set(k); (s as any).baseScale = k; (s as any).sym = sym;
  }

  private spray(cells: [number, number][]) {
    for (const [r, c] of cells) for (let i = 0; i < 6; i++) {
      const d = new Graphics().circle(0, 0, 2 + Math.random() * 3.5).fill(0x8f0a14); // decoration only, not an outcome
      d.x = (c + 0.5) * CW + (Math.random() - 0.5) * 30; d.y = (r + 0.5) * CH + (Math.random() - 0.5) * 20;
      this.fx.addChild(d);
      const a = Math.random() * Math.PI * 2, v = 30 + Math.random() * 70;
      gsap.to(d, { x: d.x + Math.cos(a) * v, y: d.y + Math.sin(a) * v + 45, alpha: 0, duration: 0.55 + Math.random() * 0.25, ease: 'power2.out', onComplete: () => d.destroy() });
    }
  }

  private make(sym: number, row: number) {
    const s = new Sprite(this.tex[this.set][sym]);
    s.anchor.set(0.5);
    this.skin(s, sym);
    s.x = CW / 2; s.y = row * CH + CH / 2;
    return s;
  }

  setGrid(grid: Grid) {
    for (let c = 0; c < COLS; c++) {
      this.sprites[c].forEach(s => s.destroy());
      this.sprites[c] = [];
      for (let r = 0; r < ROWS; r++) { const s = this.make(grid[r][c], r); this.cols[c].addChild(s); this.sprites[c].push(s); }
    }
  }

  /** Old symbols drop out, new ones fall in, reels stop left to right. */
  spinTo(grid: Grid): Promise<void> {
    this.clearHighlight();
    const tl = gsap.timeline();
    let extra = 0, seen = 0;
    for (let c = 0; c < COLS; c++) {
      const old = this.sprites[c];
      const start = c * TIMING.reelStagger;
      old.forEach(s => tl.to(s, { y: s.y + H + 60, duration: TIMING.dropOut, ease: 'power2.in', onComplete: () => s.destroy() }, start));
      if (seen >= 2) { // two belts down: the remaining reels hang
        if (extra === 0) tl.call(() => this.onAnticipation(), [], start + TIMING.dropOut);
        extra += TIMING.anticipation;
      }
      const fresh: Sprite[] = [];
      const hasScatter = grid.some(row => row[c] === SCATTER);
      for (let r = 0; r < ROWS; r++) {
        const s = this.make(grid[r][c], r); const y = s.y;
        s.y = y - H - 60; this.cols[c].addChild(s); fresh.push(s);
        tl.to(s, { y, duration: TIMING.dropIn, ease: 'back.out(1.05)' }, start + TIMING.dropOut + extra + (ROWS - 1 - r) * 0.012);
      }
      tl.call(() => this.onReelStop(c, hasScatter), [], start + TIMING.dropOut + extra + TIMING.dropIn * 0.7);
      this.sprites[c] = fresh;
      if (hasScatter) seen++;
    }
    return new Promise(res => tl.eventCallback('onComplete', () => res()));
  }

  /** Damage marks belong to cells. pop = animate cells whose value went up. */
  showMarks(marks: Grid, pop = false) {
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const i = r * COLS + c, v = marks[r][c], was = this.marks[i];
      this.marks[i] = v;
      this.tiles[i].className = `g-tile${v > 0 ? ` on t${tierOf(v)}` : ''}`;
      const b = this.badges[i];
      b.textContent = v > 0 ? `x${v}` : '';
      b.className = `g-badge${v > 0 ? ` on t${tierOf(v)}` : ''}`;
      if (pop && v > was) { b.classList.remove('pop'); void b.offsetWidth; b.classList.add('pop'); }
    }
  }

  highlight(clusters: Cluster[]): Promise<void> {
    const win = new Set<number>();
    clusters.forEach(cl => cl.cells.forEach(([r, c]) => win.add(r * COLS + c)));
    const tl = gsap.timeline();
    if (this.gore === 2) clusters.forEach(cl => this.spray(cl.cells));
    for (let c = 0; c < COLS; c++) this.sprites[c].forEach((s, r) => {
      const hit = win.has(r * COLS + c);
      this.cells[r * COLS + c].classList.toggle('win', hit);
      s.alpha = hit ? 1 : 0.32;
      if (hit) { const k = (s as any).baseScale as number; tl.fromTo(s.scale, { x: k, y: k }, { x: k * 1.16, y: k * 1.16, duration: TIMING.pulse / 2, yoyo: true, repeat: 1, ease: 'power1.inOut' }, 0); }
    });
    return new Promise(res => tl.eventCallback('onComplete', () => res()));
  }

  clearHighlight() {
    this.cells.forEach(c => c.classList.remove('win'));
    this.sprites.forEach(col => col.forEach(s => { s.alpha = 1; }));
  }

  /** Takedown: the listed reels slide down one row; one symbol enters at the top of each. */
  slide(reels: number[], entered: number[], grid: Grid): Promise<void> {
    this.clearHighlight();
    const tl = gsap.timeline();
    reels.forEach((c, k) => {
      const incoming = this.make(entered[k], -1);
      this.cols[c].addChild(incoming);
      const all = [incoming, ...this.sprites[c]];
      all.forEach(s => tl.to(s, { y: s.y + CH, duration: TIMING.slide, ease: 'power3.in' }, 0));
      const gone = all[all.length - 1];
      tl.call(() => gone.destroy(), [], TIMING.slide);
      this.sprites[c] = all.slice(0, ROWS);
    });
    return new Promise(res => tl.eventCallback('onComplete', () => {
      // the record is the truth: if the view ever disagrees with it, redraw from the record
      const ok = this.sprites.every((col, c) => col.every((s, r) => (s as any).sym === grid[r][c]));
      if (!ok) { console.warn('grid view out of step with record; redrawn'); this.setGrid(grid); }
      res();
    }));
  }

  cellCentre(cells: [number, number][]) {
    const x = cells.reduce((a, [, c]) => a + (c + 0.5) * CW, 0) / cells.length;
    const y = cells.reduce((a, [r]) => a + (r + 0.5) * CH, 0) / cells.length;
    return { x, y };
  }

  shake(el: HTMLElement, power = 1) { gsap.fromTo(el, { x: 0, y: 0 }, { x: 3 * power, y: 6 * power, duration: 0.045, yoyo: true, repeat: 5, ease: 'power1.inOut', clearProps: 'transform' }); }
}

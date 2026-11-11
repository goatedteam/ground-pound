// Sound hooks. Every call site is wired; the sounds themselves are added in the audio pass.
export type Sfx = 'click' | 'spin' | 'reelStop' | 'scatterLand' | 'clusterWin' | 'damage' | 'takedown' | 'beltCount'
  | 'fightIntro' | 'retrigger' | 'tier' | 'knockout' | 'outro' | 'countTick' | 'error';
let enabled = true;
export const audio = {
  play(_name: Sfx, _opts?: { intensity?: number }) { if (!enabled) return; /* audio pass */ },
  music(_track: 'base' | 'fight' | null) { /* audio pass */ },
  setEnabled(on: boolean) { enabled = on; },
  get enabled() { return enabled; },
};

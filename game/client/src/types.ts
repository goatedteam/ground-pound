// Round record types. Mirror of game/schema/round.schema.json (the server's output format).
export type Grid = number[][];
export interface Cluster { symbol: number; size: number; cells: [number, number][]; base_pay: number; multiplier: number; pay: number }
export interface Step {
  grid: Grid; marks_before: Grid; clusters: Cluster[]; win: number; marks_after: Grid;
  nudged_reels?: number[]; entered?: number[]; new_scatters?: number; capped?: true;
}
export interface Spin {
  reel_set: 'base' | 'bonus'; stops: number[]; nudge_roll: boolean | null; steps: Step[];
  scatters: number; win: number; capped: boolean; retrigger?: boolean; spins_left?: number;
}
export interface FreeSpins { awarded: number; start_marks: Grid; spins: Spin[]; retriggers: number; win: number; capped: boolean }
export interface Round { mode: 'base' | 'buy_standard' | 'buy_super'; cost: number; base_spin: Spin | null; free_spins: FreeSpins | null; win: number; capped: boolean }
export interface PlayResult { round_id: string; round: Round; bet_minor: number; cost_minor: number; win_minor: number; balance_minor: number; net_position_minor: number }
export interface Market {
  id: string; currency: string; buys: boolean; bet_ladder_minor: number[]; default_bet_minor: number; max_stake_minor: number;
  min_cycle_ms: number; gore: 0 | 1 | 2; turbo: boolean; autoplay: boolean; show_net_position: boolean; show_session_time: boolean;
}
export interface ThemeSymbol { id: number; key: string; name: string; asset: string }
export interface GameConfig {
  name: string; market: Market; variant: string; rtp_target: string; symbols: string[];
  paytable: Record<string, number[]>; rules: { max_win: number; free_spins_award: Record<string, number>; retrigger_spins: number; min_cluster: number };
  base_nudge_probability: number;
  buys: null | { standard: { price: number; name: string }; super: { price: number; name: string } };
  theme: { name: string; symbols: ThemeSymbol[]; win_tiers: { min: number; name: string }[]; cap_name: string; gore_levels: string[] };
  certified: boolean; notice: string;
}

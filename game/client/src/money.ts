// Money is integers everywhere: hundredths of stake inside the game, minor units for currency.
export const hundredths = (stakeMultiple: number) => Math.round(stakeMultiple * 100);
/** Hundredths of stake to minor units. Whole for every ladder bet (multiples of 20 minor units). */
export const toMinor = (h: number, betMinor: number) => (h * betMinor) / 100;
export function formatMoney(minor: number, currency: string) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(minor / 100);
}

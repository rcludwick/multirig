/**
 * Amateur radio band definitions and utilities.
 */

export interface Band {
  label: string;
  lo: number;
  hi: number;
  default: number;
}

/**
 * Standard amateur radio bands.
 */
export const BANDS: Band[] = [
  { label: '160m', lo: 1800000, hi: 2000000, default: 1840000 },
  { label: '80m', lo: 3500000, hi: 4000000, default: 3573000 },
  { label: '60m', lo: 5330500, hi: 5405000, default: 5357000 },
  { label: '40m', lo: 7000000, hi: 7300000, default: 7074000 },
  { label: '30m', lo: 10100000, hi: 10150000, default: 10136000 },
  { label: '20m', lo: 14000000, hi: 14350000, default: 14074000 },
  { label: '17m', lo: 18068000, hi: 18168000, default: 18100000 },
  { label: '15m', lo: 21000000, hi: 21450000, default: 21074000 },
  { label: '12m', lo: 24890000, hi: 24990000, default: 24915000 },
  { label: '10m', lo: 28000000, hi: 29700000, default: 28074000 },
  { label: '6m', lo: 50000000, hi: 54000000, default: 50313000 },
  { label: '4m', lo: 70000000, hi: 70500000, default: 70200000 },
  { label: '2m', lo: 144000000, hi: 148000000, default: 144174000 },
  { label: '1.25m', lo: 219000000, hi: 225000000, default: 222100000 },
  { label: '70cm', lo: 420000000, hi: 450000000, default: 432200000 },
  { label: '23cm', lo: 1240000000, hi: 1300000000, default: 1296200000 },
];

/**
 * Quick band labels for default presets.
 */
export const QUICK_BAND_LABELS = ['40m', '20m', '15m', '10m', '6m', '2m', '70cm'];

/**
 * Find band for a given frequency.
 */
export function bandForHz(hz: number | null | undefined): Band | null {
  if (hz == null || isNaN(hz)) return null;
  return BANDS.find((b) => hz >= b.lo && hz <= b.hi) ?? null;
}

/**
 * Get band label for a frequency.
 */
export function bandLabelForHz(hz: number | null | undefined): string {
  const band = bandForHz(hz);
  return band?.label ?? '';
}

/**
 * Parse band label to meters value.
 * "20m" -> 20, "70cm" -> 0.7
 */
export function bandLabelToMeters(label: string): number | null {
  const match = label.match(/^([\d.]+)(m|cm)$/i);
  if (!match) return null;
  const num = parseFloat(match[1]);
  const unit = match[2].toLowerCase();
  return unit === 'cm' ? num / 100 : num;
}

/**
 * Sort band labels by wavelength (largest first).
 */
export function sortBandLabels(labels: string[]): string[] {
  return [...labels].sort((a, b) => {
    const ma = bandLabelToMeters(a);
    const mb = bandLabelToMeters(b);
    if (ma == null && mb == null) return 0;
    if (ma == null) return 1;
    if (mb == null) return -1;
    return mb - ma; // Larger wavelength first
  });
}

/**
 * Frequency formatting and parsing utilities.
 */

export interface FormattedFrequency {
  value: string;
  unit: string;
}

/**
 * Format frequency in Hz to human-readable string.
 */
export function formatFreq(hz: number | null | undefined): FormattedFrequency {
  if (hz == null || isNaN(hz)) {
    return { value: '---', unit: '' };
  }

  if (hz >= 1_000_000) {
    // MHz
    const mhz = hz / 1_000_000;
    return {
      value: mhz.toFixed(mhz >= 100 ? 2 : 3),
      unit: 'MHz',
    };
  } else if (hz >= 1000) {
    // kHz
    return {
      value: (hz / 1000).toFixed(1),
      unit: 'kHz',
    };
  } else {
    // Hz
    return {
      value: String(Math.round(hz)),
      unit: 'Hz',
    };
  }
}

/**
 * Format frequency with specific unit preference.
 */
export function formatFreqWithUnit(
  hz: number | null | undefined,
  unit: 'auto' | 'mhz' | 'khz' | 'hz'
): FormattedFrequency {
  if (hz == null || isNaN(hz)) {
    return { value: '---', unit: '' };
  }

  switch (unit) {
    case 'mhz':
      return {
        value: (hz / 1_000_000).toFixed(6),
        unit: 'MHz',
      };
    case 'khz':
      return {
        value: (hz / 1000).toFixed(3),
        unit: 'kHz',
      };
    case 'hz':
      return {
        value: String(Math.round(hz)),
        unit: 'Hz',
      };
    default:
      return formatFreq(hz);
  }
}

/**
 * Parse user frequency input to Hz.
 * Handles various formats:
 * - "14.074" -> 14074000 (assumes MHz for decimals)
 * - "14074" -> 14074000 (heuristic: > 30000 = Hz, else kHz)
 * - "14074000" -> 14074000
 * - "14.074 MHz" -> 14074000
 */
export function parseFrequencyInput(
  input: string,
  unit: 'auto' | 'mhz' | 'khz' | 'hz' = 'auto'
): number | null {
  const cleaned = input.trim().replace(/,/g, '').toLowerCase();

  // Extract number part
  const match = cleaned.match(/^([\d.]+)\s*(mhz?|khz?|hz?)?$/i);
  if (!match) return null;

  const numStr = match[1];
  const explicitUnit = match[2]?.toLowerCase();
  const num = parseFloat(numStr);

  if (isNaN(num) || num < 0) return null;

  // Determine unit
  let finalUnit = unit;
  if (explicitUnit) {
    if (explicitUnit.startsWith('m')) finalUnit = 'mhz';
    else if (explicitUnit.startsWith('k')) finalUnit = 'khz';
    else finalUnit = 'hz';
  }

  // Apply unit
  switch (finalUnit) {
    case 'mhz':
      return Math.round(num * 1_000_000);
    case 'khz':
      return Math.round(num * 1000);
    case 'hz':
      return Math.round(num);
    case 'auto':
    default:
      // Heuristics for auto mode
      if (numStr.includes('.')) {
        // Decimal = assume MHz
        return Math.round(num * 1_000_000);
      } else if (num > 30000) {
        // Large number = Hz
        return Math.round(num);
      } else if (num > 1000) {
        // Medium = kHz
        return Math.round(num * 1000);
      } else {
        // Small = MHz
        return Math.round(num * 1_000_000);
      }
  }
}

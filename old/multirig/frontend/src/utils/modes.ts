/**
 * Amateur radio mode utilities.
 */

/**
 * Mode descriptions for tooltips.
 */
export const MODE_MEANINGS: Record<string, string> = {
  USB: 'Upper Sideband',
  LSB: 'Lower Sideband',
  CW: 'Continuous Wave (Morse)',
  CWR: 'CW Reverse',
  AM: 'Amplitude Modulation',
  FM: 'Frequency Modulation',
  WFM: 'Wide FM',
  NFM: 'Narrow FM',
  RTTY: 'Radioteletype',
  RTTYR: 'RTTY Reverse',
  PSK: 'Phase Shift Keying',
  PKTUSB: 'Packet USB',
  PKTLSB: 'Packet LSB',
  PKTFM: 'Packet FM',
  ECSSUSB: 'ECSS Upper',
  ECSSLSB: 'ECSS Lower',
  FAX: 'Facsimile',
  SAM: 'Synchronous AM',
  SAL: 'SAM Lower',
  SAH: 'SAM Upper',
  DSB: 'Double Sideband',
  FMN: 'FM Narrow',
  FMW: 'FM Wide',
  AMS: 'AM Synchronous',
  SPEC: 'Spectrum',
  DATA: 'Data Mode',
  DATAUSB: 'Data USB',
  DATALSB: 'Data LSB',
  DIGITALVOICE: 'Digital Voice',
  DV: 'Digital Voice (D-Star)',
  C4FM: 'C4FM Fusion',
  DSTAR: 'D-Star',
  DMR: 'Digital Mobile Radio',
  P25: 'Project 25',
  NXDN: 'NXDN',
  FREEDV: 'FreeDV',
};

/**
 * Get mode description.
 */
export function getModeDescription(mode: string | null | undefined): string {
  if (!mode) return '';
  return MODE_MEANINGS[mode.toUpperCase()] ?? mode;
}

/**
 * Common modes sorted by typical usage.
 */
export const COMMON_MODES = ['USB', 'LSB', 'CW', 'FM', 'AM', 'RTTY', 'PSK', 'DATA'];

/**
 * Check if mode is a digital mode.
 */
export function isDigitalMode(mode: string | null | undefined): boolean {
  if (!mode) return false;
  const upper = mode.toUpperCase();
  return ['RTTY', 'RTTYR', 'PSK', 'PKTUSB', 'PKTLSB', 'PKTFM', 'DATA', 'DATAUSB', 'DATALSB'].includes(upper);
}

/**
 * Check if mode is a voice mode.
 */
export function isVoiceMode(mode: string | null | undefined): boolean {
  if (!mode) return false;
  const upper = mode.toUpperCase();
  return ['USB', 'LSB', 'FM', 'AM', 'NFM', 'WFM', 'DSB', 'DV', 'C4FM', 'DSTAR', 'DMR', 'P25'].includes(upper);
}

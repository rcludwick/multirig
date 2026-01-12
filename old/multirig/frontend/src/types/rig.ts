/**
 * Band preset configuration for quick frequency selection.
 */
export interface BandPreset {
  label: string;
  frequency_hz: number;
  enabled: boolean;
  lower_hz?: number;
  upper_hz?: number;
}

/**
 * Configuration for a single rig (persisted).
 */
export interface RigConfig {
  name: string;
  enabled: boolean;
  connection_type: 'rigctld' | 'hamlib';
  // rigctld settings
  host: string;
  port: number;
  managed: boolean;
  rigctld_cmd?: string;
  // hamlib direct settings
  model_id?: number;
  device?: string;
  baud?: number;
  serial_opts?: string;
  extra_args?: string;
  // frequency control
  allow_out_of_band: boolean;
  band_presets: BandPreset[];
  // sync behavior
  follow_main: boolean;
  poll_interval_ms: number;
  // UI
  color: string;
  inverted: boolean;
}

/**
 * Real-time rig status (from WebSocket).
 */
export interface RigStatus {
  index: number;
  name: string;
  enabled: boolean;
  connected: boolean;
  frequency_hz: number | null;
  frequency_a_hz?: number | null;
  frequency_b_hz?: number | null;
  mode: string | null;
  vfo: string | null;
  passband?: number;
  ptt: boolean;
  error: string | null;
  last_error: string | null;
  model_id: number | null;
  caps?: RigCaps;
  modes?: string[];
  caps_detected: boolean;
  color: string;
  inverted: boolean;
  follow_main: boolean;
  allow_out_of_band: boolean;
  band_presets: BandPreset[];
  connection_type: 'rigctld' | 'hamlib';
  host?: string;
  port?: number;
  device?: string;
  baud?: number;
}

/**
 * Rig capabilities detected from hamlib.
 */
export interface RigCaps {
  freq_set: boolean;
  freq_get: boolean;
  mode_set: boolean;
  mode_get: boolean;
  vfo_set: boolean;
  vfo_get: boolean;
  ptt_set: boolean;
  ptt_get: boolean;
}

/**
 * Rig model from rig_models.json.
 */
export interface RigModel {
  id: number;
  manufacturer: string;
  model: string;
  label: string;
  caps?: RigCaps;
  modes?: string[];
}

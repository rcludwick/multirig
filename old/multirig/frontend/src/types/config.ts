import type { RigConfig } from './rig';

/**
 * Full application configuration (persisted to YAML).
 */
export interface AppConfig {
  rigs: RigConfig[];
  rigctl_listen_host: string;
  rigctl_listen_port: number;
  rigctl_to_main_enabled: boolean;
  poll_interval_ms: number;
  sync_enabled: boolean;
  sync_source_index: number;
}

/**
 * Server status broadcast via WebSocket.
 */
export interface ServerStatus {
  rigs: import('./rig').RigStatus[];
  sync_enabled: boolean;
  sync_source_index: number;
  rigctl_to_main_enabled: boolean;
  all_rigs_enabled: boolean;
  active_profile: string;
  rigctl_host: string;
  rigctl_port: number;
}

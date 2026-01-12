/**
 * Standard API response wrapper.
 */
export interface ApiResponse<T = void> {
  status: 'ok' | 'error';
  data?: T;
  error?: string;
}

/**
 * Profile list response.
 */
export interface ProfileListResponse {
  profiles: string[];
}

/**
 * Server meta info response.
 */
export interface ServerMetaResponse {
  host: string;
  port: number;
}

/**
 * Debug log entry.
 */
export interface DebugLogEntry {
  timestamp: number;
  direction: 'TX' | 'RX';
  data: string;
  source?: string;
}

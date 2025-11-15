/**
 * LabLink Mobile - Configuration
 */

// API Configuration
export const API_CONFIG = {
  // Default to localhost for development
  // Users can change this in Settings
  DEFAULT_BASE_URL: 'http://localhost:8000',
  DEFAULT_WS_URL: 'ws://localhost:8000/ws',

  // API Timeouts
  TIMEOUT: 30000, // 30 seconds
  UPLOAD_TIMEOUT: 120000, // 2 minutes

  // Token refresh
  TOKEN_REFRESH_THRESHOLD: 300, // Refresh 5 minutes before expiry
};

// WebSocket Configuration
export const WS_CONFIG = {
  // Reconnection strategy
  MAX_RECONNECT_ATTEMPTS: 10,
  BASE_RECONNECT_DELAY: 2000, // 2 seconds
  MAX_RECONNECT_DELAY: 60000, // 1 minute

  // Heartbeat
  HEARTBEAT_INTERVAL: 30000, // 30 seconds
  HEARTBEAT_TIMEOUT: 10000, // 10 seconds
};

// Storage Keys
export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'access_token',
  REFRESH_TOKEN: 'refresh_token',
  USER: 'user',
  SERVER_URL: 'server_url',
  WS_URL: 'ws_url',
  THEME: 'theme',
  NOTIFICATIONS_CONFIG: 'notifications_config',
  BIOMETRIC_ENABLED: 'biometric_enabled',
};

// App Configuration
export const APP_CONFIG = {
  NAME: 'LabLink',
  VERSION: '1.1.0',
  BUILD: '1',
  BUNDLE_ID: 'com.lablink.app',
  DEEP_LINK_SCHEME: 'lablink',
};

// UI Configuration
export const UI_CONFIG = {
  // Refresh intervals
  EQUIPMENT_REFRESH_INTERVAL: 5000, // 5 seconds
  ALARM_REFRESH_INTERVAL: 3000, // 3 seconds

  // Pagination
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
};

/**
 * LabLink Mobile - API Types
 * Auto-generated types based on LabLink API v1.0.0
 */

// Authentication
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  requires_mfa?: boolean;
}

export interface MFALoginRequest {
  username: string;
  totp_code: string;
}

export interface OAuth2Provider {
  name: string;
  enabled: boolean;
  client_id?: string;
}

export interface User {
  id: string;
  username: string;
  email?: string;
  full_name?: string;
  role: string;
  is_active: boolean;
  created_at: string;
  mfa_enabled: boolean;
}

// Equipment
export interface Equipment {
  equipment_id: string;
  equipment_type: string;
  manufacturer: string;
  model: string;
  resource_string: string;
  status: 'connected' | 'disconnected' | 'error';
  connection_time?: string;
  last_command?: string;
  error_message?: string;
}

export interface EquipmentStatus {
  equipment_id: string;
  status: string;
  connected: boolean;
  timestamp: string;
}

export interface EquipmentCommand {
  command: string;
  parameters?: Record<string, any>;
}

// Alarms
export enum AlarmSeverity {
  INFO = 'info',
  WARNING = 'warning',
  ERROR = 'error',
  CRITICAL = 'critical',
}

export enum AlarmType {
  THRESHOLD = 'threshold',
  DEVIATION = 'deviation',
  RATE_OF_CHANGE = 'rate_of_change',
  EQUIPMENT_ERROR = 'equipment_error',
  COMMUNICATION_ERROR = 'communication_error',
  SYSTEM_ERROR = 'system_error',
  CUSTOM = 'custom',
}

export interface Alarm {
  id: string;
  name: string;
  alarm_type: AlarmType;
  severity: AlarmSeverity;
  active: boolean;
  acknowledged: boolean;
  equipment_id?: string;
  value?: number;
  threshold?: number;
  message: string;
  triggered_at?: string;
  acknowledged_at?: string;
  acknowledged_by?: string;
}

export interface AlarmListResponse {
  alarms: Alarm[];
  total: number;
  active_count: number;
  unacknowledged_count: number;
}

// WebSocket Messages
export enum WebSocketMessageType {
  EQUIPMENT_UPDATE = 'equipment_update',
  ALARM_TRIGGERED = 'alarm_triggered',
  ALARM_CLEARED = 'alarm_cleared',
  DATA_UPDATE = 'data_update',
  CONNECTION_STATUS = 'connection_status',
}

export interface WebSocketMessage {
  type: WebSocketMessageType;
  data: any;
  timestamp: string;
}

// API Response
export interface ApiResponse<T = any> {
  success?: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

// Notifications
export interface PushNotificationConfig {
  alarms_enabled: boolean;
  equipment_status_enabled: boolean;
  severity_filter: AlarmSeverity[];
}

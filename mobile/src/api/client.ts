/**
 * LabLink Mobile - API Client
 * HTTP client for communicating with LabLink server API
 */

import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { API_CONFIG, STORAGE_KEYS } from '../constants/config';
import type {
  LoginRequest,
  LoginResponse,
  MFALoginRequest,
  Equipment,
  Alarm,
  AlarmListResponse,
  User,
  ApiResponse,
} from '../types/api';

export class LabLinkAPIClient {
  private client: AxiosInstance;
  private baseUrl: string;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;

  constructor(baseUrl: string = API_CONFIG.DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl;
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: API_CONFIG.TIMEOUT,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
      },
    });

    // Request interceptor to add auth token
    this.client.interceptors.request.use(
      async (config) => {
        if (!this.accessToken) {
          this.accessToken = await SecureStore.getItemAsync(STORAGE_KEYS.ACCESS_TOKEN);
        }

        if (this.accessToken) {
          config.headers.Authorization = `Bearer ${this.accessToken}`;
        }

        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor for error handling and token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

        // If 401 and we haven't retried yet, try to refresh token
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;

          try {
            const newAccessToken = await this.refreshAccessToken();
            if (newAccessToken && originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
              return this.client(originalRequest);
            }
          } catch (refreshError) {
            // Token refresh failed, user needs to login again
            await this.clearTokens();
            throw refreshError;
          }
        }

        return Promise.reject(error);
      }
    );
  }

  /**
   * Update the base URL (when user changes server)
   */
  setBaseUrl(url: string) {
    this.baseUrl = url;
    this.client.defaults.baseURL = url;
  }

  /**
   * Set access token
   */
  setAccessToken(token: string) {
    this.accessToken = token;
  }

  /**
   * Set refresh token
   */
  setRefreshToken(token: string) {
    this.refreshToken = token;
  }

  /**
   * Clear stored tokens
   */
  async clearTokens() {
    this.accessToken = null;
    this.refreshToken = null;
    await SecureStore.deleteItemAsync(STORAGE_KEYS.ACCESS_TOKEN);
    await SecureStore.deleteItemAsync(STORAGE_KEYS.REFRESH_TOKEN);
  }

  /**
   * Refresh access token using refresh token
   */
  private async refreshAccessToken(): Promise<string | null> {
    if (!this.refreshToken) {
      this.refreshToken = await SecureStore.getItemAsync(STORAGE_KEYS.REFRESH_TOKEN);
    }

    if (!this.refreshToken) {
      throw new Error('No refresh token available');
    }

    try {
      const response = await axios.post<LoginResponse>(
        `${this.baseUrl}/api/security/refresh`,
        { refresh_token: this.refreshToken }
      );

      const { access_token, refresh_token } = response.data;

      this.accessToken = access_token;
      this.refreshToken = refresh_token;

      await SecureStore.setItemAsync(STORAGE_KEYS.ACCESS_TOKEN, access_token);
      await SecureStore.setItemAsync(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);

      return access_token;
    } catch (error) {
      console.error('Failed to refresh token:', error);
      return null;
    }
  }

  // ============================================
  // Authentication API
  // ============================================

  /**
   * Login with username and password
   */
  async login(username: string, password: string): Promise<LoginResponse> {
    const response = await this.client.post<LoginResponse>('/api/security/login', {
      username,
      password,
    });

    const { access_token, refresh_token, requires_mfa } = response.data;

    if (!requires_mfa) {
      this.accessToken = access_token;
      this.refreshToken = refresh_token;
      await SecureStore.setItemAsync(STORAGE_KEYS.ACCESS_TOKEN, access_token);
      await SecureStore.setItemAsync(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);
    }

    return response.data;
  }

  /**
   * Login with MFA code
   */
  async loginWithMFA(username: string, totpCode: string): Promise<LoginResponse> {
    const response = await this.client.post<LoginResponse>('/api/security/mfa/login', {
      username,
      totp_code: totpCode,
    });

    const { access_token, refresh_token } = response.data;

    this.accessToken = access_token;
    this.refreshToken = refresh_token;
    await SecureStore.setItemAsync(STORAGE_KEYS.ACCESS_TOKEN, access_token);
    await SecureStore.setItemAsync(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);

    return response.data;
  }

  /**
   * Logout
   */
  async logout(): Promise<void> {
    try {
      await this.client.post('/api/security/logout');
    } finally {
      await this.clearTokens();
    }
  }

  /**
   * Get current user profile
   */
  async getCurrentUser(): Promise<User> {
    const response = await this.client.get<User>('/api/security/user/me');
    return response.data;
  }

  /**
   * Get OAuth2 providers
   */
  async getOAuth2Providers(): Promise<any[]> {
    const response = await this.client.get('/api/security/oauth2/providers');
    return response.data;
  }

  // ============================================
  // Equipment API
  // ============================================

  /**
   * Get list of all equipment
   */
  async getEquipmentList(): Promise<Equipment[]> {
    const response = await this.client.get<Equipment[]>('/api/equipment/list');
    return response.data;
  }

  /**
   * Get equipment by ID
   */
  async getEquipment(equipmentId: string): Promise<Equipment> {
    const response = await this.client.get<Equipment>(`/api/equipment/${equipmentId}`);
    return response.data;
  }

  /**
   * Connect to equipment
   */
  async connectEquipment(equipmentId: string): Promise<ApiResponse> {
    const response = await this.client.post<ApiResponse>(`/api/equipment/${equipmentId}/connect`);
    return response.data;
  }

  /**
   * Disconnect from equipment
   */
  async disconnectEquipment(equipmentId: string): Promise<ApiResponse> {
    const response = await this.client.post<ApiResponse>(`/api/equipment/${equipmentId}/disconnect`);
    return response.data;
  }

  /**
   * Send command to equipment
   */
  async sendCommand(equipmentId: string, command: string): Promise<ApiResponse> {
    const response = await this.client.post<ApiResponse>(
      `/api/equipment/${equipmentId}/command`,
      { command }
    );
    return response.data;
  }

  /**
   * Query equipment (send and receive)
   */
  async queryEquipment(equipmentId: string, command: string): Promise<ApiResponse<string>> {
    const response = await this.client.post<ApiResponse<string>>(
      `/api/equipment/${equipmentId}/query`,
      { command }
    );
    return response.data;
  }

  // ============================================
  // Alarms API
  // ============================================

  /**
   * Get list of alarms
   */
  async getAlarms(params?: { limit?: number; offset?: number }): Promise<AlarmListResponse> {
    const response = await this.client.get<AlarmListResponse>('/api/alarms/list', { params });
    return response.data;
  }

  /**
   * Get active alarms
   */
  async getActiveAlarms(): Promise<Alarm[]> {
    const response = await this.client.get<Alarm[]>('/api/alarms/active');
    return response.data;
  }

  /**
   * Acknowledge alarm
   */
  async acknowledgeAlarm(alarmId: string): Promise<ApiResponse> {
    const response = await this.client.post<ApiResponse>(`/api/alarms/${alarmId}/acknowledge`);
    return response.data;
  }

  /**
   * Get alarm by ID
   */
  async getAlarm(alarmId: string): Promise<Alarm> {
    const response = await this.client.get<Alarm>(`/api/alarms/${alarmId}`);
    return response.data;
  }

  // ============================================
  // Health Check
  // ============================================

  /**
   * Check server health
   */
  async healthCheck(): Promise<ApiResponse> {
    const response = await this.client.get<ApiResponse>('/health');
    return response.data;
  }
}

// Export singleton instance
export const apiClient = new LabLinkAPIClient();

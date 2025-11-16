/**
 * LabLink Mobile - WebSocket Manager
 * Real-time data streaming with mobile-optimized reconnection
 */

import { AppState, AppStateStatus } from 'react-native';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';
import * as SecureStore from 'expo-secure-store';
import { WS_CONFIG, STORAGE_KEYS, API_CONFIG } from '../constants/config';
import { WebSocketMessage, WebSocketMessageType } from '../types/api';

type MessageHandler = (message: WebSocketMessage) => void;
type ConnectionStatusHandler = (connected: boolean) => void;

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private wsUrl: string;
  private reconnectAttempts = 0;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private isManuallyDisconnected = false;
  private appState: AppStateStatus = AppState.currentState;

  private messageHandlers: Map<WebSocketMessageType | 'all', Set<MessageHandler>> = new Map();
  private connectionStatusHandlers: Set<ConnectionStatusHandler> = new Set();

  constructor(wsUrl: string = API_CONFIG.DEFAULT_WS_URL) {
    this.wsUrl = wsUrl;

    // Listen to app state changes
    AppState.addEventListener('change', this.handleAppStateChange);

    // Listen to network changes
    NetInfo.addEventListener(this.handleNetworkChange);
  }

  /**
   * Update WebSocket URL
   */
  setUrl(url: string) {
    this.wsUrl = url;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.disconnect();
      this.connect();
    }
  }

  /**
   * Connect to WebSocket server
   */
  async connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return;
    }

    this.isManuallyDisconnected = false;

    try {
      // Get access token for authentication
      const token = await SecureStore.getItemAsync(STORAGE_KEYS.ACCESS_TOKEN);
      const url = token ? `${this.wsUrl}?token=${token}` : this.wsUrl;

      this.ws = new WebSocket(url);

      this.ws.onopen = this.handleOpen;
      this.ws.onmessage = this.handleMessage;
      this.ws.onerror = this.handleError;
      this.ws.onclose = this.handleClose;

      console.log('WebSocket connecting to:', this.wsUrl);
    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.isManuallyDisconnected = true;
    this.reconnectAttempts = 0;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.notifyConnectionStatus(false);
  }

  /**
   * Send message to server
   */
  send(message: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, cannot send message');
    }
  }

  /**
   * Subscribe to messages of a specific type
   */
  on(type: WebSocketMessageType | 'all', handler: MessageHandler): () => void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, new Set());
    }
    this.messageHandlers.get(type)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.messageHandlers.get(type)?.delete(handler);
    };
  }

  /**
   * Subscribe to connection status changes
   */
  onConnectionStatus(handler: ConnectionStatusHandler): () => void {
    this.connectionStatusHandlers.add(handler);

    // Return unsubscribe function
    return () => {
      this.connectionStatusHandlers.delete(handler);
    };
  }

  /**
   * Handle WebSocket open event
   */
  private handleOpen = (): void => {
    console.log('WebSocket connected');
    this.reconnectAttempts = 0;
    this.notifyConnectionStatus(true);
    this.startHeartbeat();
  };

  /**
   * Handle incoming WebSocket message
   */
  private handleMessage = (event: MessageEvent): void => {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);

      // Notify handlers for this specific message type
      this.messageHandlers.get(message.type)?.forEach((handler) => {
        handler(message);
      });

      // Notify handlers for all messages
      this.messageHandlers.get('all')?.forEach((handler) => {
        handler(message);
      });
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  };

  /**
   * Handle WebSocket error event
   */
  private handleError = (error: Event): void => {
    console.error('WebSocket error:', error);
  };

  /**
   * Handle WebSocket close event
   */
  private handleClose = (): void => {
    console.log('WebSocket disconnected');
    this.notifyConnectionStatus(false);

    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }

    // Only reconnect if not manually disconnected and app is active
    if (!this.isManuallyDisconnected && this.appState === 'active') {
      this.scheduleReconnect();
    }
  };

  /**
   * Schedule reconnection with exponential backoff
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
      console.log('Max reconnect attempts reached');
      return;
    }

    const delay = Math.min(
      WS_CONFIG.BASE_RECONNECT_DELAY * Math.pow(2, this.reconnectAttempts),
      WS_CONFIG.MAX_RECONNECT_DELAY
    );

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1})`);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  /**
   * Start heartbeat to keep connection alive
   */
  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping' });
      }
    }, WS_CONFIG.HEARTBEAT_INTERVAL);
  }

  /**
   * Handle app state changes (foreground/background)
   */
  private handleAppStateChange = (nextAppState: AppStateStatus): void => {
    if (this.appState.match(/inactive|background/) && nextAppState === 'active') {
      // App came to foreground, reconnect if needed
      console.log('App came to foreground, reconnecting WebSocket');
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        this.connect();
      }
    } else if (nextAppState === 'background') {
      // App went to background, clean disconnect
      console.log('App went to background, disconnecting WebSocket');
      this.disconnect();
    }

    this.appState = nextAppState;
  };

  /**
   * Handle network connectivity changes
   */
  private handleNetworkChange = (state: NetInfoState): void => {
    if (state.isConnected && !this.ws && !this.isManuallyDisconnected && this.appState === 'active') {
      console.log('Network restored, reconnecting WebSocket');
      this.connect();
    } else if (!state.isConnected && this.ws) {
      console.log('Network lost, disconnecting WebSocket');
      this.disconnect();
    }
  };

  /**
   * Notify connection status handlers
   */
  private notifyConnectionStatus(connected: boolean): void {
    this.connectionStatusHandlers.forEach((handler) => {
      handler(connected);
    });
  }

  /**
   * Cleanup
   */
  destroy(): void {
    this.disconnect();
    this.messageHandlers.clear();
    this.connectionStatusHandlers.clear();
  }
}

// Export singleton instance
export const wsManager = new WebSocketManager();

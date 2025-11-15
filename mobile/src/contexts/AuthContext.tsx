/**
 * LabLink Mobile - Authentication Context
 * Manages user authentication state and operations
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as SecureStore from 'expo-secure-store';
import * as LocalAuthentication from 'expo-local-authentication';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiClient } from '../api/client';
import { STORAGE_KEYS } from '../constants/config';
import type { User, LoginResponse } from '../types/api';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  biometricEnabled: boolean;
  biometricAvailable: boolean;
  login: (username: string, password: string) => Promise<LoginResponse>;
  loginWithMFA: (username: string, totpCode: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  enableBiometric: () => Promise<void>;
  disableBiometric: () => Promise<void>;
  authenticateWithBiometric: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [biometricEnabled, setBiometricEnabled] = useState(false);
  const [biometricAvailable, setBiometricAvailable] = useState(false);

  useEffect(() => {
    initializeAuth();
    checkBiometricAvailability();
  }, []);

  /**
   * Initialize authentication state
   */
  const initializeAuth = async () => {
    try {
      // Check if we have a stored access token
      const accessToken = await SecureStore.getItemAsync(STORAGE_KEYS.ACCESS_TOKEN);

      if (accessToken) {
        apiClient.setAccessToken(accessToken);

        // Try to get user profile
        const userData = await apiClient.getCurrentUser();
        setUser(userData);
      }

      // Check if biometric is enabled
      const biometricEnabledStr = await AsyncStorage.getItem(STORAGE_KEYS.BIOMETRIC_ENABLED);
      setBiometricEnabled(biometricEnabledStr === 'true');
    } catch (error) {
      console.error('Failed to initialize auth:', error);
      // Clear tokens if they're invalid
      await clearAuthData();
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Check if biometric authentication is available
   */
  const checkBiometricAvailability = async () => {
    try {
      const compatible = await LocalAuthentication.hasHardwareAsync();
      const enrolled = await LocalAuthentication.isEnrolledAsync();
      setBiometricAvailable(compatible && enrolled);
    } catch (error) {
      console.error('Failed to check biometric availability:', error);
      setBiometricAvailable(false);
    }
  };

  /**
   * Login with username and password
   */
  const login = async (username: string, password: string): Promise<LoginResponse> => {
    try {
      const response = await apiClient.login(username, password);

      if (!response.requires_mfa) {
        // Login successful, get user profile
        const userData = await apiClient.getCurrentUser();
        setUser(userData);
      }

      return response;
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };

  /**
   * Login with MFA code
   */
  const loginWithMFA = async (username: string, totpCode: string): Promise<LoginResponse> => {
    try {
      const response = await apiClient.loginWithMFA(username, totpCode);

      // Login successful, get user profile
      const userData = await apiClient.getCurrentUser();
      setUser(userData);

      return response;
    } catch (error) {
      console.error('MFA login failed:', error);
      throw error;
    }
  };

  /**
   * Logout
   */
  const logout = async (): Promise<void> => {
    try {
      await apiClient.logout();
    } catch (error) {
      console.error('Logout failed:', error);
    } finally {
      await clearAuthData();
      setUser(null);
    }
  };

  /**
   * Refresh user profile
   */
  const refreshUser = async (): Promise<void> => {
    try {
      const userData = await apiClient.getCurrentUser();
      setUser(userData);
    } catch (error) {
      console.error('Failed to refresh user:', error);
      throw error;
    }
  };

  /**
   * Enable biometric authentication
   */
  const enableBiometric = async (): Promise<void> => {
    if (!biometricAvailable) {
      throw new Error('Biometric authentication is not available on this device');
    }

    try {
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Enable biometric authentication',
        fallbackLabel: 'Use password',
      });

      if (result.success) {
        await AsyncStorage.setItem(STORAGE_KEYS.BIOMETRIC_ENABLED, 'true');
        setBiometricEnabled(true);
      } else {
        throw new Error('Biometric authentication failed');
      }
    } catch (error) {
      console.error('Failed to enable biometric:', error);
      throw error;
    }
  };

  /**
   * Disable biometric authentication
   */
  const disableBiometric = async (): Promise<void> => {
    await AsyncStorage.removeItem(STORAGE_KEYS.BIOMETRIC_ENABLED);
    setBiometricEnabled(false);
  };

  /**
   * Authenticate with biometric
   */
  const authenticateWithBiometric = async (): Promise<boolean> => {
    if (!biometricAvailable || !biometricEnabled) {
      return false;
    }

    try {
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Unlock LabLink',
        fallbackLabel: 'Use password',
      });

      return result.success;
    } catch (error) {
      console.error('Biometric authentication failed:', error);
      return false;
    }
  };

  /**
   * Clear all auth data
   */
  const clearAuthData = async (): Promise<void> => {
    await apiClient.clearTokens();
    await AsyncStorage.removeItem(STORAGE_KEYS.USER);
  };

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    biometricEnabled,
    biometricAvailable,
    login,
    loginWithMFA,
    logout,
    refreshUser,
    enableBiometric,
    disableBiometric,
    authenticateWithBiometric,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * Hook to use auth context
 */
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

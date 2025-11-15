/**
 * LabLink Mobile - Settings Screen
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Switch,
  Alert,
  TextInput,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useAuth } from '../contexts/AuthContext';
import { apiClient } from '../api/client';
import { wsManager } from '../api/websocket';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';
import { STORAGE_KEYS, API_CONFIG } from '../constants/config';

export const SettingsScreen: React.FC = () => {
  const { user, logout, biometricAvailable, biometricEnabled, enableBiometric, disableBiometric } = useAuth();

  const [serverUrl, setServerUrl] = useState(API_CONFIG.DEFAULT_BASE_URL);
  const [wsUrl, setWsUrl] = useState(API_CONFIG.DEFAULT_WS_URL);
  const [saving, setSaving] = useState(false);

  const handleBiometricToggle = async (value: boolean) => {
    try {
      if (value) {
        await enableBiometric();
        Alert.alert('Success', 'Biometric authentication enabled');
      } else {
        await disableBiometric();
        Alert.alert('Success', 'Biometric authentication disabled');
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to update biometric settings');
    }
  };

  const handleSaveServerSettings = async () => {
    setSaving(true);
    try {
      // Validate URLs
      if (!serverUrl.trim() || !wsUrl.trim()) {
        Alert.alert('Error', 'URLs cannot be empty');
        return;
      }

      // Save to storage
      await AsyncStorage.setItem(STORAGE_KEYS.SERVER_URL, serverUrl);
      await AsyncStorage.setItem(STORAGE_KEYS.WS_URL, wsUrl);

      // Update API client and WebSocket manager
      apiClient.setBaseUrl(serverUrl);
      wsManager.setUrl(wsUrl);

      Alert.alert('Success', 'Server settings updated');
    } catch (error) {
      Alert.alert('Error', 'Failed to save server settings');
    } finally {
      setSaving(false);
    }
  };

  const handleResetToDefaults = () => {
    setServerUrl(API_CONFIG.DEFAULT_BASE_URL);
    setWsUrl(API_CONFIG.DEFAULT_WS_URL);
  };

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Logout', style: 'destructive', onPress: logout },
      ]
    );
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* User Profile */}
      <Card>
        <Text style={styles.sectionTitle}>Profile</Text>
        <View style={styles.profileInfo}>
          <Text style={styles.profileLabel}>Username:</Text>
          <Text style={styles.profileValue}>{user?.username}</Text>
        </View>
        {user?.email && (
          <View style={styles.profileInfo}>
            <Text style={styles.profileLabel}>Email:</Text>
            <Text style={styles.profileValue}>{user.email}</Text>
          </View>
        )}
        <View style={styles.profileInfo}>
          <Text style={styles.profileLabel}>Role:</Text>
          <Text style={styles.profileValue}>{user?.role}</Text>
        </View>
        <View style={styles.profileInfo}>
          <Text style={styles.profileLabel}>MFA:</Text>
          <Text style={styles.profileValue}>
            {user?.mfa_enabled ? 'Enabled ✓' : 'Disabled'}
          </Text>
        </View>
      </Card>

      {/* Security */}
      {biometricAvailable && (
        <Card>
          <Text style={styles.sectionTitle}>Security</Text>
          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Text style={styles.settingLabel}>Biometric Authentication</Text>
              <Text style={styles.settingDescription}>
                Use Face ID or Touch ID to unlock the app
              </Text>
            </View>
            <Switch
              value={biometricEnabled}
              onValueChange={handleBiometricToggle}
              trackColor={{ false: Colors.light.border, true: Colors.primary }}
              thumbColor="#FFFFFF"
            />
          </View>
        </Card>
      )}

      {/* Server Settings */}
      <Card>
        <Text style={styles.sectionTitle}>Server Connection</Text>
        <Text style={styles.inputLabel}>Server URL</Text>
        <TextInput
          style={styles.input}
          value={serverUrl}
          onChangeText={setServerUrl}
          placeholder="http://localhost:8000"
          placeholderTextColor={Colors.light.textSecondary}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Text style={styles.inputLabel}>WebSocket URL</Text>
        <TextInput
          style={styles.input}
          value={wsUrl}
          onChangeText={setWsUrl}
          placeholder="ws://localhost:8000/ws"
          placeholderTextColor={Colors.light.textSecondary}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Button
          title="Save Settings"
          onPress={handleSaveServerSettings}
          loading={saving}
          style={styles.saveButton}
        />
        <Button
          title="Reset to Defaults"
          onPress={handleResetToDefaults}
          variant="outline"
        />
      </Card>

      {/* App Info */}
      <Card>
        <Text style={styles.sectionTitle}>About</Text>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>Version:</Text>
          <Text style={styles.infoValue}>1.1.0</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>Build:</Text>
          <Text style={styles.infoValue}>1</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>API Version:</Text>
          <Text style={styles.infoValue}>v1.0.0</Text>
        </View>
      </Card>

      {/* Logout */}
      <Button
        title="Logout"
        onPress={handleLogout}
        variant="danger"
        style={styles.logoutButton}
      />
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.light.background,
  },
  content: {
    padding: Spacing.md,
  },
  sectionTitle: {
    fontSize: Typography.fontSize.lg,
    fontWeight: Typography.fontWeight.semibold,
    color: Colors.light.text,
    marginBottom: Spacing.md,
  },
  profileInfo: {
    flexDirection: 'row',
    marginBottom: Spacing.sm,
  },
  profileLabel: {
    fontSize: Typography.fontSize.base,
    fontWeight: Typography.fontWeight.medium,
    color: Colors.light.textSecondary,
    width: 100,
  },
  profileValue: {
    flex: 1,
    fontSize: Typography.fontSize.base,
    color: Colors.light.text,
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  settingInfo: {
    flex: 1,
    marginRight: Spacing.md,
  },
  settingLabel: {
    fontSize: Typography.fontSize.base,
    fontWeight: Typography.fontWeight.medium,
    color: Colors.light.text,
    marginBottom: Spacing.xs,
  },
  settingDescription: {
    fontSize: Typography.fontSize.sm,
    color: Colors.light.textSecondary,
  },
  inputLabel: {
    fontSize: Typography.fontSize.sm,
    fontWeight: Typography.fontWeight.medium,
    color: Colors.light.text,
    marginBottom: Spacing.xs,
  },
  input: {
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    fontSize: Typography.fontSize.base,
    color: Colors.light.text,
    backgroundColor: '#FFFFFF',
    marginBottom: Spacing.md,
  },
  saveButton: {
    marginBottom: Spacing.sm,
  },
  infoRow: {
    flexDirection: 'row',
    marginBottom: Spacing.sm,
  },
  infoLabel: {
    fontSize: Typography.fontSize.base,
    color: Colors.light.textSecondary,
    width: 100,
  },
  infoValue: {
    flex: 1,
    fontSize: Typography.fontSize.base,
    color: Colors.light.text,
  },
  logoutButton: {
    marginTop: Spacing.md,
    marginBottom: Spacing.xl,
  },
});

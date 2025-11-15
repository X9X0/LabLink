/**
 * LabLink Mobile - Equipment Detail Screen
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Alert,
  TextInput,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { apiClient } from '../api/client';
import { wsManager } from '../api/websocket';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';
import type { Equipment, WebSocketMessage, WebSocketMessageType } from '../types/api';

type RouteParams = {
  EquipmentDetail: {
    equipmentId: string;
  };
};

export const EquipmentDetailScreen: React.FC = () => {
  const route = useRoute<RouteProp<RouteParams, 'EquipmentDetail'>>();
  const { equipmentId } = route.params;

  const [equipment, setEquipment] = useState<Equipment | null>(null);
  const [loading, setLoading] = useState(true);
  const [command, setCommand] = useState('');
  const [commandResponse, setCommandResponse] = useState('');
  const [sendingCommand, setSendingCommand] = useState(false);

  useEffect(() => {
    loadEquipment();
    setupWebSocket();
  }, [equipmentId]);

  const setupWebSocket = () => {
    const unsubscribe = wsManager.on('equipment_update' as WebSocketMessageType, (message: WebSocketMessage) => {
      if (message.data.equipment_id === equipmentId) {
        setEquipment((prev) => prev ? { ...prev, ...message.data } : null);
      }
    });

    return unsubscribe;
  };

  const loadEquipment = async () => {
    try {
      const data = await apiClient.getEquipment(equipmentId);
      setEquipment(data);
    } catch (error) {
      Alert.alert('Error', 'Failed to load equipment details');
      console.error('Failed to load equipment:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async () => {
    try {
      await apiClient.connectEquipment(equipmentId);
      Alert.alert('Success', 'Equipment connected');
      loadEquipment();
    } catch (error: any) {
      Alert.alert('Error', error?.response?.data?.detail || 'Failed to connect equipment');
    }
  };

  const handleDisconnect = async () => {
    try {
      await apiClient.disconnectEquipment(equipmentId);
      Alert.alert('Success', 'Equipment disconnected');
      loadEquipment();
    } catch (error: any) {
      Alert.alert('Error', error?.response?.data?.detail || 'Failed to disconnect equipment');
    }
  };

  const handleSendCommand = async () => {
    if (!command.trim()) {
      Alert.alert('Error', 'Please enter a command');
      return;
    }

    setSendingCommand(true);
    setCommandResponse('');

    try {
      const response = await apiClient.queryEquipment(equipmentId, command);
      setCommandResponse(response.data || 'Command sent successfully');
    } catch (error: any) {
      setCommandResponse(`Error: ${error?.response?.data?.detail || 'Failed to send command'}`);
    } finally {
      setSendingCommand(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.container}>
        <Text style={styles.loadingText}>Loading...</Text>
      </View>
    );
  }

  if (!equipment) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>Equipment not found</Text>
      </View>
    );
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'connected':
        return Colors.connected;
      case 'disconnected':
        return Colors.disconnected;
      case 'error':
        return Colors.equipmentError;
      default:
        return Colors.light.textSecondary;
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Equipment Info */}
        <Card>
          <View style={styles.header}>
            <Text style={styles.title}>{equipment.manufacturer} {equipment.model}</Text>
            <View style={[styles.statusBadge, { backgroundColor: getStatusColor(equipment.status) }]}>
              <Text style={styles.statusText}>{equipment.status}</Text>
            </View>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.label}>ID:</Text>
            <Text style={styles.value}>{equipment.equipment_id}</Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.label}>Type:</Text>
            <Text style={styles.value}>{equipment.equipment_type}</Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.label}>Resource:</Text>
            <Text style={styles.value}>{equipment.resource_string}</Text>
          </View>

          {equipment.connection_time && (
            <View style={styles.infoRow}>
              <Text style={styles.label}>Connected:</Text>
              <Text style={styles.value}>
                {new Date(equipment.connection_time).toLocaleString()}
              </Text>
            </View>
          )}

          {equipment.error_message && (
            <View style={styles.errorContainer}>
              <Text style={styles.errorText}>⚠️ {equipment.error_message}</Text>
            </View>
          )}
        </Card>

        {/* Connection Controls */}
        <Card>
          <Text style={styles.sectionTitle}>Connection</Text>
          <View style={styles.buttonRow}>
            <Button
              title="Connect"
              onPress={handleConnect}
              disabled={equipment.status === 'connected'}
              style={styles.buttonHalf}
            />
            <Button
              title="Disconnect"
              onPress={handleDisconnect}
              variant="outline"
              disabled={equipment.status !== 'connected'}
              style={styles.buttonHalf}
            />
          </View>
        </Card>

        {/* Command Interface */}
        <Card>
          <Text style={styles.sectionTitle}>Send Command (SCPI)</Text>
          <TextInput
            style={styles.commandInput}
            value={command}
            onChangeText={setCommand}
            placeholder="*IDN?"
            placeholderTextColor={Colors.light.textSecondary}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Button
            title="Send"
            onPress={handleSendCommand}
            loading={sendingCommand}
            disabled={equipment.status !== 'connected'}
          />
          {commandResponse && (
            <View style={styles.responseContainer}>
              <Text style={styles.responseLabel}>Response:</Text>
              <Text style={styles.responseText}>{commandResponse}</Text>
            </View>
          )}
        </Card>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.light.background,
  },
  scrollContent: {
    padding: Spacing.md,
  },
  loadingText: {
    textAlign: 'center',
    marginTop: Spacing.xl,
    fontSize: Typography.fontSize.lg,
    color: Colors.light.textSecondary,
  },
  errorText: {
    textAlign: 'center',
    marginTop: Spacing.xl,
    fontSize: Typography.fontSize.lg,
    color: Colors.error,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: Spacing.md,
  },
  title: {
    flex: 1,
    fontSize: Typography.fontSize.xl,
    fontWeight: Typography.fontWeight.bold,
    color: Colors.light.text,
  },
  statusBadge: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.sm,
  },
  statusText: {
    color: '#FFFFFF',
    fontSize: Typography.fontSize.xs,
    fontWeight: Typography.fontWeight.medium,
    textTransform: 'capitalize',
  },
  infoRow: {
    flexDirection: 'row',
    marginBottom: Spacing.sm,
  },
  label: {
    fontSize: Typography.fontSize.base,
    fontWeight: Typography.fontWeight.medium,
    color: Colors.light.textSecondary,
    width: 100,
  },
  value: {
    flex: 1,
    fontSize: Typography.fontSize.base,
    color: Colors.light.text,
  },
  errorContainer: {
    backgroundColor: '#FEE2E2',
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    marginTop: Spacing.sm,
  },
  sectionTitle: {
    fontSize: Typography.fontSize.lg,
    fontWeight: Typography.fontWeight.semibold,
    color: Colors.light.text,
    marginBottom: Spacing.md,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  buttonHalf: {
    flex: 1,
  },
  commandInput: {
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    fontSize: Typography.fontSize.base,
    color: Colors.light.text,
    backgroundColor: '#FFFFFF',
    marginBottom: Spacing.md,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  responseContainer: {
    marginTop: Spacing.md,
    padding: Spacing.md,
    backgroundColor: Colors.light.surface,
    borderRadius: BorderRadius.md,
  },
  responseLabel: {
    fontSize: Typography.fontSize.sm,
    fontWeight: Typography.fontWeight.medium,
    color: Colors.light.textSecondary,
    marginBottom: Spacing.xs,
  },
  responseText: {
    fontSize: Typography.fontSize.base,
    color: Colors.light.text,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
});

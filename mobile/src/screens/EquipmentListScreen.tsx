/**
 * LabLink Mobile - Equipment List Screen
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { apiClient } from '../api/client';
import { wsManager } from '../api/websocket';
import { Card } from '../components/Card';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';
import type { Equipment, WebSocketMessage, WebSocketMessageType } from '../types/api';

export const EquipmentListScreen: React.FC = () => {
  const navigation = useNavigation();
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);

  useEffect(() => {
    loadEquipment();
    setupWebSocket();

    return () => {
      // Cleanup WebSocket subscriptions
      wsManager.disconnect();
    };
  }, []);

  const setupWebSocket = () => {
    // Connect to WebSocket
    wsManager.connect();

    // Subscribe to connection status
    const unsubscribeStatus = wsManager.onConnectionStatus((connected) => {
      setWsConnected(connected);
    });

    // Subscribe to equipment updates
    const unsubscribeEquipment = wsManager.on('equipment_update' as WebSocketMessageType, (message: WebSocketMessage) => {
      handleEquipmentUpdate(message.data);
    });

    return () => {
      unsubscribeStatus();
      unsubscribeEquipment();
    };
  };

  const handleEquipmentUpdate = (data: any) => {
    setEquipment((prevEquipment) => {
      const index = prevEquipment.findIndex((eq) => eq.equipment_id === data.equipment_id);
      if (index !== -1) {
        const updated = [...prevEquipment];
        updated[index] = { ...updated[index], ...data };
        return updated;
      }
      return prevEquipment;
    });
  };

  const loadEquipment = async () => {
    try {
      const data = await apiClient.getEquipmentList();
      setEquipment(data);
    } catch (error) {
      Alert.alert('Error', 'Failed to load equipment');
      console.error('Failed to load equipment:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadEquipment();
  }, []);

  const handleEquipmentPress = (item: Equipment) => {
    navigation.navigate('EquipmentDetail' as never, { equipmentId: item.equipment_id } as never);
  };

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

  const renderEquipmentItem = ({ item }: { item: Equipment }) => (
    <TouchableOpacity onPress={() => handleEquipmentPress(item)}>
      <Card>
        <View style={styles.equipmentHeader}>
          <View style={styles.equipmentInfo}>
            <Text style={styles.equipmentName}>{item.manufacturer} {item.model}</Text>
            <Text style={styles.equipmentId}>{item.equipment_id}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: getStatusColor(item.status) }]}>
            <Text style={styles.statusText}>{item.status}</Text>
          </View>
        </View>

        {item.error_message && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorText}>⚠️ {item.error_message}</Text>
          </View>
        )}

        <View style={styles.equipmentDetails}>
          <Text style={styles.detailLabel}>Type:</Text>
          <Text style={styles.detailValue}>{item.equipment_type}</Text>
        </View>

        {item.connection_time && (
          <View style={styles.equipmentDetails}>
            <Text style={styles.detailLabel}>Connected:</Text>
            <Text style={styles.detailValue}>
              {new Date(item.connection_time).toLocaleTimeString()}
            </Text>
          </View>
        )}
      </Card>
    </TouchableOpacity>
  );

  const renderHeader = () => (
    <View style={styles.header}>
      <Text style={styles.headerTitle}>Equipment</Text>
      <View style={[styles.wsIndicator, { backgroundColor: wsConnected ? Colors.connected : Colors.disconnected }]}>
        <Text style={styles.wsIndicatorText}>
          {wsConnected ? '● Live' : '○ Offline'}
        </Text>
      </View>
    </View>
  );

  const renderEmpty = () => (
    <View style={styles.emptyContainer}>
      <Text style={styles.emptyText}>No equipment found</Text>
      <Text style={styles.emptySubtext}>
        Connect equipment from the server to see it here
      </Text>
    </View>
  );

  return (
    <View style={styles.container}>
      {renderHeader()}
      <FlatList
        data={equipment}
        renderItem={renderEquipmentItem}
        keyExtractor={(item) => item.equipment_id}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListEmptyComponent={!loading ? renderEmpty : null}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.light.background,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: Colors.light.border,
  },
  headerTitle: {
    fontSize: Typography.fontSize['2xl'],
    fontWeight: Typography.fontWeight.bold,
    color: Colors.light.text,
  },
  wsIndicator: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.full,
  },
  wsIndicatorText: {
    color: '#FFFFFF',
    fontSize: Typography.fontSize.xs,
    fontWeight: Typography.fontWeight.medium,
  },
  listContent: {
    padding: Spacing.md,
    flexGrow: 1,
  },
  equipmentHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: Spacing.sm,
  },
  equipmentInfo: {
    flex: 1,
  },
  equipmentName: {
    fontSize: Typography.fontSize.lg,
    fontWeight: Typography.fontWeight.semibold,
    color: Colors.light.text,
    marginBottom: Spacing.xs,
  },
  equipmentId: {
    fontSize: Typography.fontSize.sm,
    color: Colors.light.textSecondary,
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
  equipmentDetails: {
    flexDirection: 'row',
    marginTop: Spacing.xs,
  },
  detailLabel: {
    fontSize: Typography.fontSize.sm,
    color: Colors.light.textSecondary,
    marginRight: Spacing.xs,
  },
  detailValue: {
    fontSize: Typography.fontSize.sm,
    color: Colors.light.text,
  },
  errorContainer: {
    backgroundColor: '#FEE2E2',
    padding: Spacing.sm,
    borderRadius: BorderRadius.sm,
    marginTop: Spacing.sm,
  },
  errorText: {
    fontSize: Typography.fontSize.sm,
    color: Colors.error,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: Spacing['3xl'],
  },
  emptyText: {
    fontSize: Typography.fontSize.lg,
    fontWeight: Typography.fontWeight.semibold,
    color: Colors.light.textSecondary,
    marginBottom: Spacing.xs,
  },
  emptySubtext: {
    fontSize: Typography.fontSize.base,
    color: Colors.light.textSecondary,
    textAlign: 'center',
  },
});
